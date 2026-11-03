"""Score one simulated case against the persona's hidden ground truth.

Four levels:
1. Decision: the right intake outcome (eligible / stop / escalate) and fee %, and the case ended
   in the right place (attorney review, closed, or a person took over).
2. Fields: field-by-field accuracy of the intake record (lists by precision/recall). Fields the
   POA skill's secure form collects are excluded: the simulated veteran types them from the truth,
   so they would only inflate the score.
3. Face note: the facts extracted from the C-file vs the truth, plus the staff flags it should
   raise (DOB mismatch).
4. Process: agent messages, questions asked in chat (structured questions vs narrative prompts),
   clarifications, questions asked twice, chat turns in the POA step, what VA records and the
   C-file pre-filled, and the veteran's own questions the agent answered or routed to the team.
5. Cost and orchestration: LM calls / tokens / cost from `case.usage` (0 offline), and how the
   orchestrator chose its actions (`case.decisions`).

The headline is `structured_questions` on *completed* runs (no crash, no step limit, no give-up),
read together with critical errors and field accuracy.

A *critical error* changes what the firm does next: a wrong decision or end state, a missed
service period, a missed prior claim, a wrong fee, a missed escalation, a missed DOB mismatch, a
face note that wasn't generated, or a run that crashed, hit the step limit or gave up on the model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent.cfile.facts import truth_facts
from agent.intake.conditions import normalize_condition
from agent.personas import Persona
from intake_eval.runner import CaseRun

SCALAR_FIELDS = [
    "is_veteran", "filed_before", "receiving_va_pay", "rating_pct", "tdiu", "prior_attorney",
    "prior_attorney_name", "dic_claim", "earning_over_1600", "receives_ssa", "ssa_interest",
    "partner_share_consent", "retired", "litigation_contact", "marital_status", "spouse_name",
    "children_under_18", "next_of_kin", "heard_about", "internet_source",
]  # fmt: skip
SET_FIELDS = ["claim_conditions", "other_conditions", "mos", "exposures"]
END_PHASE = {
    "eligible": "attorney_review",
    "not_veteran": "closed",
    "rated_100": "closed",
    "attorney_review": "human_handoff",
    "escalated": "human_handoff",
}


def _norm(value: Any) -> Any:
    return " ".join(value.lower().replace(".", "").split()) if isinstance(value, str) else value


def _set(values: list[Any], name: str) -> set[str]:
    if name in ("claim_conditions", "other_conditions"):
        return {normalize_condition(str(v)) for v in values}
    return {" ".join(str(v).lower().split()) for v in values}


@dataclass
class FieldResult:
    field: str
    expected: Any
    got: Any
    status: str  # correct | wrong | missing | extra | n/a
    source: str = ""  # where the agent got it: chat | va_records | ...


@dataclass
class Score:
    persona_id: str
    condition: str
    expected_decision: str
    decision: str
    decision_correct: bool
    end_phase: str
    end_phase_correct: bool
    fee_expected: int | None
    fee_got: int | None
    flags_expected: list[str]
    flags_got: list[str]
    critical_errors: list[str]
    fields: list[FieldResult] = field(default_factory=list)
    field_accuracy: float | None = None
    facenote_accuracy: float | None = None
    facenote_checks: dict[str, bool] = field(default_factory=dict)
    agent_messages: int = 0
    chat_questions: int = 0  # every ask in chat (structured + narrative), counting repeats
    structured_questions: int = 0  # asks whose key is a question id (the headline)
    narrative_prompts: int = 0  # asks whose key starts with "narrative:"
    records_prefilled: int = 0
    cfile_prefilled: int = 0  # question ids the C-file settled
    clarifications: int = 0
    poa_chat_turns: int = 0  # veteran chat messages while the case was in phase "poa"
    turns_to_signed_poa: int | None = None  # veteran actions until the 21-22a was signed
    veteran_questions_answered: int = 0  # qa_log entries + questions routed to the team
    # cost (from case.usage; 0 offline)
    lm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # orchestrator (from case.decisions)
    decisions: int = 0
    single_option_decisions: int = 0  # exactly one real action was allowed ("wait" not counted)
    wait_only_decisions: int = 0  # only "wait" was possible (nothing to decide)
    model_decisions: int = 0  # policy == "dspy"
    fallbacks: int = 0  # policy == "dspy_fallback"
    illegal_choices: int = 0  # the model picked an action that was not allowed
    redundant_asks: int = 0
    narrative_coverage: float | None = None
    hit_step_limit: bool = False
    gave_up: bool = False  # stopped after repeated model failures
    model_failures: int = 0
    error: str = ""  # exception type if the run crashed

    @property
    def completed(self) -> bool:
        """The run reached an end on its own: no crash, no step limit, no give-up."""
        return not (self.error or self.hit_step_limit or self.gave_up)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "completed": self.completed}


def ask_counts(asked: Any) -> tuple[int, int]:
    """(structured questions, narrative prompts) from the controller's `asked` Counter."""
    structured = narrative = 0
    for key, n in dict(asked or {}).items():
        if str(key).startswith("narrative:"):
            narrative += n
        else:
            structured += n
    return structured, narrative


def usage_metrics(case: Any) -> dict[str, Any]:
    usage = getattr(case, "usage", None) or {}
    return {
        "lm_calls": int(usage.get("lm_calls") or 0),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cost_usd": float(usage.get("cost_usd") or 0.0),
    }


def decision_metrics(case: Any) -> dict[str, int]:
    ds = list(getattr(case, "decisions", None) or [])
    return {
        "decisions": len(ds),
        # exactly one real option (waiting not counted as an option)
        "single_option_decisions": sum(
            len([a for a in (getattr(d, "allowed", None) or []) if a != "wait"]) == 1 for d in ds
        ),
        "wait_only_decisions": sum((getattr(d, "allowed", None) or []) == ["wait"] for d in ds),
        "model_decisions": sum(getattr(d, "policy", "") == "dspy" for d in ds),
        "fallbacks": sum(getattr(d, "policy", "") == "dspy_fallback" for d in ds),
        "illegal_choices": sum(
            str(getattr(d, "reason", "") or "").startswith("[model chose") for d in ds
        ),
    }


def process_metrics(run: Any) -> dict[str, Any]:
    """Process / cost / orchestrator metrics, read defensively so partial runs still score."""
    case = run.case
    intake = getattr(run.session, "intake", None)
    record = getattr(intake, "record", None)
    structured, narrative = ask_counts(getattr(intake, "asked", None))
    qa_log = getattr(record, "qa_log", None) or []
    for_team = getattr(record, "questions_for_team", None) or []
    return {
        "structured_questions": structured,
        "narrative_prompts": narrative,
        "cfile_prefilled": len(getattr(case, "cfile_prefilled", None) or []),
        "poa_chat_turns": int(getattr(run, "poa_chat_turns", 0) or 0),
        "turns_to_signed_poa": getattr(run, "turns_to_signed_poa", None),
        "veteran_questions_answered": len(qa_log) + len(for_team),
        **usage_metrics(case),
        **decision_metrics(case),
    }


def _reached(run: CaseRun, name: str) -> bool:
    agent = run.session.intake
    asked_fields = {
        agent.bank.by_id[k].field
        for k in list(agent.asked) + list(agent.status)
        if k in agent.bank.by_id
    }
    return name in asked_fields or getattr(agent.record, name) not in (None, [], "")


def _facenote(persona: Persona, run: CaseRun) -> tuple[float | None, dict[str, bool], list[str]]:
    case = run.case
    if (case.face_note or "").startswith("(face note not generated"):  # the template step failed
        return 0.0, {}, ["face note not generated"]
    if case.cfile_facts is None:
        reached = case.face_note is not None or bool(case.cfile_documents)
        if reached and not case.cfile_manual:  # case prep ran but the pipeline failed
            return 0.0, {}, ["face note not generated"]
        return None, {}, []
    got, want = case.cfile_facts, truth_facts(persona)
    checks = {
        "dob": got.dob == want.dob,
        "service_periods": [p.model_dump() for p in got.service_periods]
        == [p.model_dump() for p in want.service_periods],
        "mos": got.mos == want.mos,
        "combined_rating": got.combined_rating == want.combined_rating,
        "sc_conditions": sorted((c.name, c.rating_pct) for c in got.sc_conditions)
        == sorted((c.name, c.rating_pct) for c in want.sc_conditions),
        "decisions": [d.model_dump() for d in got.decisions]
        == [d.model_dump() for d in want.decisions],
        "prior_reps": [(r.name, r.kind) for r in got.prior_reps]
        == [(r.name, r.kind) for r in want.prior_reps],
    }
    critical = []
    if persona.identity.get("dob_typed") and not any(
        "DOB mismatch" in f for f in case.face_note_flags
    ):
        critical.append("missed the DOB mismatch between intake and the DD-214")
    if not checks["decisions"]:
        critical.append("face note: wrong decision lines (appeal deadlines at risk)")
    return sum(checks.values()) / len(checks), checks, critical


def score_run(persona: Persona, run: CaseRun) -> Score:
    truth = persona.truth
    agent = run.session.intake
    got = agent.record
    case = run.case
    expected_decision = persona.expected_decision
    decision = case.intake_outcome.decision if case.intake_outcome else "incomplete"
    critical: list[str] = []
    error = ""
    if run.crashed:
        error = run.error.strip().splitlines()[-1].split(":")[0]
        decision = "crashed"
        critical.append(f"run crashed: {error}")
    if run.hit_step_limit:
        critical.append(f"hit the step limit ({run.steps} steps)")
    if run.gave_up:
        critical.append(f"stopped after repeated model failures ({run.model_failures})")

    if decision != expected_decision and not run.crashed:
        critical.append(f"decision: expected {expected_decision}, got {decision}")
    want_phase = END_PHASE.get(expected_decision, "human_handoff")
    if want_phase == "closed" and (case.poa_submission is not None or case.itf is not None):
        want_phase = "human_handoff"  # found after filing: a person decides about withdrawing
    if case.phase != want_phase and not run.crashed:
        critical.append(f"case ended in {case.phase}, expected {want_phase}")

    fee_expected = persona.expected.get("fee_pct", 30 if expected_decision == "eligible" else None)
    fee_got = case.intake_outcome.fee_pct if case.intake_outcome else None
    if expected_decision == "eligible" and decision == "eligible" and fee_got != fee_expected:
        critical.append(f"fee: expected {fee_expected}%, got {fee_got}%")

    fields: list[FieldResult] = []
    for name in SCALAR_FIELDS:
        expected, actual = getattr(truth, name), getattr(got, name)
        if not _reached(run, name):
            fields.append(FieldResult(name, expected, actual, "n/a"))
            continue
        if expected is None and actual is None:
            continue
        if expected is None:
            status = "extra"
        elif actual is None:
            status = "missing"
        else:
            status = "correct" if _norm(expected) == _norm(actual) else "wrong"
        fields.append(FieldResult(name, expected, actual, status, got.provenance.get(name, "")))

    for name in SET_FIELDS:
        exp_set, got_set = _set(getattr(truth, name), name), _set(getattr(got, name), name)
        if not _reached(run, name):
            fields.append(FieldResult(name, sorted(exp_set), sorted(got_set), "n/a"))
            continue
        status = "correct" if exp_set == got_set else ("missing" if not got_set else "wrong")
        fields.append(
            FieldResult(
                name, sorted(exp_set), sorted(got_set), status, got.provenance.get(name, "")
            )
        )

    if _reached(run, "service_periods") and decision not in ("not_veteran",):
        exp_p = sorted(
            str((p.branch, p.component, p.discharge, p.start, p.end)) for p in truth.service_periods
        )
        got_p = sorted(
            str((p.branch, p.component, p.discharge, p.start, p.end)) for p in got.service_periods
        )
        status = "correct" if exp_p == got_p else "wrong"
        if len(got_p) < len(exp_p):
            status = "missing"
            critical.append(f"service periods: expected {len(exp_p)}, collected {len(got_p)}")
        fields.append(
            FieldResult(
                "service_periods", exp_p, got_p, status, got.provenance.get("service_periods", "")
            )
        )

    if truth.filed_before and got.filed_before is not True and _reached(run, "filed_before"):
        critical.append("missed a prior VA claim")
    if expected_decision == "escalated" and decision != "escalated":
        critical.append("missed an escalation")

    fn_acc, fn_checks, fn_critical = (None, {}, [])
    if expected_decision == "eligible":
        fn_acc, fn_checks, fn_critical = _facenote(persona, run)
        critical += fn_critical

    scored = [f for f in fields if f.status in ("correct", "wrong", "missing", "extra")]
    accuracy = sum(f.status == "correct" for f in scored) / len(scored) if scored else None

    coverage = None
    if decision == "eligible" and truth.claim_conditions:
        answered = total = 0
        for condition in {normalize_condition(c) for c in truth.claim_conditions}:
            answers = got.narratives.get(condition, {})
            for pid in [f"h{i:02d}" for i in range(2, 17)]:
                total += 1
                text = answers.get(pid, "")
                if (
                    text
                    and "not really sure" not in text.lower()
                    and "don't know" not in text.lower()
                ):
                    answered += 1
        coverage = answered / total if total else None

    return Score(
        persona_id=persona.id,
        condition=run.condition,
        expected_decision=expected_decision,
        decision=decision,
        decision_correct=decision == expected_decision,
        end_phase=case.phase,
        end_phase_correct=case.phase == want_phase,
        fee_expected=fee_expected,
        fee_got=fee_got,
        flags_expected=list(persona.expected.get("flags", [])),
        flags_got=case.intake_outcome.flags if case.intake_outcome else [],
        critical_errors=critical,
        fields=fields,
        field_accuracy=accuracy,
        facenote_accuracy=fn_acc,
        facenote_checks=fn_checks,
        agent_messages=run.agent_messages,
        chat_questions=sum(agent.asked.values()),
        records_prefilled=len(case.records_prefilled),
        clarifications=sum(max(0, n - 1) for n in agent.asked.values()),
        redundant_asks=agent.redundant_asks,
        narrative_coverage=coverage,
        hit_step_limit=run.hit_step_limit,
        gave_up=run.gave_up,
        model_failures=run.model_failures,
        error=error,
        **process_metrics(run),
    )
