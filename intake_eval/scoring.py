"""Score one case run per agent (L32), from the case file, the event log and the traces.

Intake
  fields          the intake record (checklist.record) against the persona's answer key, field by
                  field (lists as sets). A field is scored once it is answered, or once the pass
                  that asks it is over and its question is visible on the true record (then it is
                  `missing`). Secure-form fields are left out: the runner types them from the key.
  structured_questions  the headline: structured questions settled in chat (question ids whose
                  answer came from the veteran; narratives and the secure form excluded). Read on
                  completed runs only, together with critical errors and field accuracy.
  clarifications  record_answer calls on a question beyond its first (from the traces)
  prefill_share   the share of structured answers whose source is the C-file
  turns_to_signed_poa  veteran actions (chat messages and card uses) until the 21-22a was signed
  kb              kb_search calls, and those that returned a sourced answer. Intake's questions to
                  the KB have no labels, so there is no answer accuracy here (support_eval has it).
Orchestrator
  scenario_pass   the run completed and the case ended where the persona's expected decision says
  refused         refused tool calls and moves per agent (`refused` events; code's own derivation
                  attempts excluded)
  flag decisions  what followed each support flag: an intake handoff whose goal names the new
                  condition (reopen_intake), a staff task, or nothing; vs `expected.flag_decision`
Claims prep
  facenote_line_accuracy  the face note's lines against the note rendered from the ground-truth
                  facts (same fee, ITF date, intake DOB and date), line by line
  facenote_checks per fact group: DOB, service periods, MOS, ratings, decisions, prior reps
  verify_passed, citation_precision  facts whose cited page shows their key values (verify's
                  own page check), over all recorded facts
Cost and latency per agent from the traces (L5, config.PRICES), plus the simulated veteran.

A critical error changes what the firm does next: a wrong end state or stop decision, a missed
service period, a missed prior claim, a wrong fee, a missed crisis escalation, a missed DOB
mismatch, claims prep not finishing, wrong decision lines on the face note, a new condition the
orchestrator never sent back to intake, or a run that crashed, stalled, gave up or hit the limit.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.casefile import CaseFile
from agent.cfile.facts import CfileFacts, truth_facts
from agent.claims_prep import facts as factlib
from agent.claims_prep.agent import cfile, plain, render_note
from agent.claims_prep.verify import mentions
from agent.claims_prep.verify import missing as cite_missing
from agent.intake import checklist
from agent.intake.conditions import normalize_condition
from agent.intake.documents import service
from agent.intake.questions import is_visible
from agent.personas import Persona
from intake_eval.runner import CaseRun
from poa_skill.service import load_representative

SCALAR_FIELDS = [
    "is_veteran", "filed_before", "receiving_va_pay", "rating_pct", "tdiu", "prior_attorney",
    "prior_attorney_name", "dic_claim", "earning_over_1600", "receives_ssa", "ssa_interest",
    "partner_share_consent", "retired", "litigation_contact", "marital_status", "spouse_name",
    "children_under_18", "next_of_kin", "heard_about", "internet_source",
]  # fmt: skip
SET_FIELDS = ["claim_conditions", "other_conditions", "mos", "exposures"]
# expected decision -> where the case must end, and the stop rule that must fire
EXPECTED_END = {"eligible": "attorney_review", "not_veteran": "closed", "rated_100": "closed",
                "attorney_review": "needs_human", "escalated": "needs_human"}  # fmt: skip
EXPECTED_STOP = {"not_veteran": "not_veteran", "rated_100": "rated_100", "attorney_review": "non_honorable_period"}


@dataclass
class FieldResult:
    field: str
    expected: Any
    got: Any
    status: str  # correct | wrong | missing | extra | n/a
    source: str = ""


@dataclass
class Score:
    persona_id: str
    condition: str
    expected_end: str
    end_state: str
    scenario_pass: bool
    critical_errors: list[str] = field(default_factory=list)
    completed: bool = True
    error: str = ""
    # intake
    fields: list[FieldResult] = field(default_factory=list)
    field_accuracy: float | None = None
    structured_questions: int = 0
    narrative_answers: int = 0
    clarifications: int = 0
    veteran_messages: int = 0
    cfile_prefilled: int = 0
    prefill_share: float | None = None
    turns_to_signed_poa: int | None = None
    fee_expected: int | None = None
    fee_got: int | None = None
    kb_calls: int = 0
    kb_sourced: int = 0
    # orchestrator
    handoffs: list[str] = field(default_factory=list)
    refused: dict[str, int] = field(default_factory=dict)
    flag_decisions: list[str] = field(default_factory=list)
    flag_decision_expected: str | None = None
    flag_decision_correct: bool | None = None
    # claims prep
    facenote_line_accuracy: float | None = None
    facenote_lines: tuple[int, int] = (0, 0)  # (matched, expected)
    facenote_checks: dict[str, bool] = field(default_factory=dict)
    verify_passed: bool | None = None
    uncertain_lines: int = 0
    citation_precision: float | None = None
    facts: int = 0
    # cost and latency, per agent: calls, input_tokens, output_tokens, cost_usd, latency_s
    by_agent: dict[str, dict[str, float]] = field(default_factory=dict)
    cost_usd: float = 0.0
    model_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------------------ helpers


def end_state(case: CaseFile) -> str:
    if case.parked:
        return str(case.side_state)
    return "attorney_review" if case.stage >= 5 else f"stage {case.stage}"


def expected_end(persona: Persona, case: CaseFile) -> str:
    want = EXPECTED_END.get(persona.expected_decision, "needs_human")
    if want == "closed" and case.filings:  # found after filing: a person decides about withdrawing
        return "needs_human"
    return want


def _norm(value: Any) -> Any:
    return " ".join(value.lower().replace(".", "").split()) if isinstance(value, str) else value


_KIN = {"mom": "mother", "mum": "mother", "dad": "father", "wife": "spouse", "husband": "spouse"}
_STOP = {"the", "and", "from", "her", "his", "is", "my", "a", "an", "of", "you", "guys"}


def _words(text: str) -> set[str]:
    text = re.sub(r"(?<=\d)[-. ()](?=\d)", "", text.lower())  # 262-555-0177 -> 2625550177
    return {_KIN.get(w, w) for w in re.findall(r"[a-z0-9']+", text) if w not in _STOP}


def _same(expected: Any, actual: Any) -> bool:
    """Free text is right when it says what the key says, in the veteran's own words: two thirds
    of the key's words ("Maria Reyes, mother, 262-555-0177" vs "my mom, Maria Reyes. Her number is
    262-555-0177."). Anything else must match exactly."""
    if isinstance(expected, str) and isinstance(actual, str):
        if _norm(expected) == _norm(actual):
            return True
        key = _words(expected)
        return bool(key) and len(key & _words(actual)) * 3 >= len(key) * 2
    return expected == actual


def _as_set(values: list[Any], name: str) -> set[str]:
    if name in ("claim_conditions", "other_conditions"):
        return {normalize_condition(str(v)) for v in values}
    return {" ".join(str(v).lower().split()) for v in values}


def _period(p: Any) -> str:
    return str((p.branch, p.component, p.discharge, p.start, p.end))


def _due(case: CaseFile, persona: Persona, name: str) -> bool:
    """Should this field have been asked by now? Answered, or its pass is over and one of its
    questions is visible on the true record."""
    questions = [q for q in checklist.BANK.structured if q.field == name]
    if any(q.id in case.answers for q in questions):
        return True
    for q in questions:
        if q.id in checklist.SKIP or q.stage == "reopen" or q.source == "secure_form":
            continue
        if q.probe and case.eval_condition == "ask_no_probes":
            continue
        over = case.stage >= 2 if q.stage == "screen" else case.stage >= 5
        if over and not case.parked and is_visible(q, persona.truth):
            return True
    return False


def _source(case: CaseFile, name: str) -> str:
    ids = [q.id for q in checklist.BANK.structured if q.field == name and q.id in case.answers]
    return "; ".join(case.answers[i].source for i in ids)


def score_fields(persona: Persona, case: CaseFile) -> list[FieldResult]:
    truth, got = persona.truth, checklist.record(case)
    out: list[FieldResult] = []
    for name in SCALAR_FIELDS:
        expected, actual = getattr(truth, name), getattr(got, name)
        if not _due(case, persona, name):
            out.append(FieldResult(name, expected, actual, "n/a"))
            continue
        if expected is None and actual is None:
            continue
        status = ("extra" if expected is None else "missing" if actual is None
                  else "correct" if _same(expected, actual) else "wrong")  # fmt: skip
        out.append(FieldResult(name, expected, actual, status, _source(case, name)))
    for name in SET_FIELDS:
        exp, act = _as_set(getattr(truth, name), name), _as_set(getattr(got, name), name)
        status = "n/a" if not _due(case, persona, name) else "correct" if exp == act else "missing" if not act else "wrong"
        out.append(FieldResult(name, sorted(exp), sorted(act), status, _source(case, name)))
    if _due(case, persona, "service_periods") and persona.expected_decision != "not_veteran":
        exp, act = sorted(map(_period, truth.service_periods)), sorted(map(_period, got.service_periods))
        status = "missing" if len(act) < len(exp) else "correct" if exp == act else "wrong"
        out.append(FieldResult("service_periods", exp, act, status, _source(case, "service_periods")))
    return out


def question_metrics(run: CaseRun, case: CaseFile) -> dict[str, Any]:
    structured = {k: a for k, a in case.answers.items() if k in checklist.BANK.by_id and a.source != "secure form"}
    asks = Counter(
        str(x["args"].get("q", "")).removeprefix("confirm:")
        for x in run.traces
        if x["kind"] == "tool" and x["tool"] == "record_answer" and x["guard"] == "allowed"
    )
    from_cfile = sum(a.source.startswith("C-file") for a in structured.values())
    kb = [e for e in run.events if e.type == "kb_search"]
    return {
        "structured_questions": sum(a.source.startswith("veteran") for a in structured.values()),
        "narrative_answers": sum(k.startswith("narrative:") and a.source.startswith("veteran")
                                 for k, a in case.answers.items()),
        "clarifications": sum(n - 1 for k, n in asks.items() if k in checklist.BANK.by_id),
        "veteran_messages": sum(t["role"] == "veteran" for t in run.transcript),
        "cfile_prefilled": from_cfile,
        "prefill_share": from_cfile / len(structured) if structured else None,
        "turns_to_signed_poa": run.turns_to_signed_poa,
        "kb_calls": len(kb),
        "kb_sourced": sum(bool(e.data.get("answered") and e.data.get("sources")) for e in kb),
    }


def orchestrator_metrics(run: CaseRun, persona: Persona) -> dict[str, Any]:
    events = run.events
    refused = Counter(e.actor for e in events if e.type == "refused" and e.actor != "derive")
    condition = persona.during_prep.get("condition", "")
    decisions = []
    for flag in (e for e in events if e.type == "support_flag"):
        later = [e for e in events if e.seq > flag.seq and e.actor == "orchestrator"]
        if any(e.type == "handoff" and e.data["to"] == "intake" and mentions(" ".join(e.data["goal"].lower().split()), condition)
               for e in later):  # fmt: skip
            decisions.append("reopen_intake")
        elif any(e.type == "task_created" for e in later):
            decisions.append("staff_task")
        else:
            decisions.append("none")
    want = persona.expected.get("flag_decision")
    return {
        "handoffs": [e.data["to"] for e in events if e.type == "handoff"],
        "refused": dict(refused),
        "flag_decisions": decisions,
        "flag_decision_expected": want,
        "flag_decision_correct": None if want is None else want in decisions,
    }


def facenote_checks(got: CfileFacts, want: CfileFacts) -> dict[str, bool]:
    return {
        "dob": got.dob == want.dob,
        "service_periods": [p.model_dump() for p in got.service_periods] == [p.model_dump() for p in want.service_periods],
        "mos": [" ".join(m.lower().split()) for m in got.mos] == [" ".join(m.lower().split()) for m in want.mos],
        "combined_rating": got.combined_rating == want.combined_rating,
        "sc_conditions": sorted((c.name, c.rating_pct) for c in got.sc_conditions)
        == sorted((c.name, c.rating_pct) for c in want.sc_conditions),
        "decisions": [d.model_dump() for d in got.decisions] == [d.model_dump() for d in want.decisions],
        "prior_reps": [(r.name, r.kind) for r in got.prior_reps] == [(r.name, r.kind) for r in want.prior_reps],
    }  # fmt: skip


def claims_prep_metrics(run: CaseRun, persona: Persona, case: CaseFile) -> dict[str, Any]:
    prep = case.prep
    if not prep.face_note:
        return {}
    table = factlib.load(prep.facts)
    pages = cfile(case)
    holds = [not cite_missing(f, pages.owner(f.cite.page).page(f.cite.page)) for f in table]
    want = render_note(run.rt, case, truth_facts(persona))
    expected = [line.text for line in want.lines if line.sources is not None]  # separators skipped
    got = Counter(plain(line) for line in prep.face_note.splitlines())
    matched = sum((Counter(expected) & got).values())
    return {
        "facenote_line_accuracy": matched / len(expected) if expected else None,
        "facenote_lines": (matched, len(expected)),
        "facenote_checks": facenote_checks(factlib.build(table, load_representative())[0], truth_facts(persona)),
        "verify_passed": prep.verified,
        "uncertain_lines": len(prep.uncertain),
        "citation_precision": sum(holds) / len(holds) if holds else None,
        "facts": len(table),
    }


def cost_metrics(run: CaseRun) -> dict[str, Any]:
    by: dict[str, dict[str, float]] = {}
    for x in run.traces:
        if x["kind"] != "lm":
            continue
        a = by.setdefault(x["agent"], {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_s": 0.0})
        a["calls"] += 1
        a["input_tokens"] += x.get("context_tokens") or 0
        a["output_tokens"] += x.get("output_tokens") or 0
        a["cost_usd"] += x.get("cost") or 0.0
        a["latency_s"] += x.get("latency_s") or 0.0
    sim = run.sim
    if getattr(sim, "calls", 0):
        by["simulator"] = {"calls": sim.calls, "input_tokens": 0, "output_tokens": 0, "cost_usd": sim.cost, "latency_s": 0.0}
    return {"by_agent": by, "cost_usd": sum(a["cost_usd"] for a in by.values())}


# ------------------------------------------------------------------------------ the score


def critical_errors(s: Score, run: CaseRun, persona: Persona, case: CaseFile) -> list[str]:
    out: list[str] = []
    if run.error:
        out.append(f"run crashed: {s.error}")
    if run.hit_step_limit:
        out.append(f"hit the step limit ({run.steps} steps)")
    if run.gave_up:
        out.append(f"stopped after repeated model failures ({run.model_failures})")
    if run.stalled:
        out.append(f"stalled at {run.stalled}")
    if s.end_state != s.expected_end and not run.stopped_at_cost:
        out.append(f"case ended in {s.end_state}, expected {s.expected_end}")
    want_stop, got_stop = EXPECTED_STOP.get(persona.expected_decision), case.stop.rule if case.stop else None
    if got_stop != want_stop and (want_stop is None or s.completed):
        out.append(f"stop rule: expected {want_stop or 'none'}, got {got_stop or 'none'}")
    if persona.expected_decision == "escalated" and not any(
        e.type == "escalated" and e.actor == "rule" and e.data.get("reason") == "crisis" for e in run.events
    ):
        out.append("missed a crisis escalation")
    periods = next((f for f in s.fields if f.field == "service_periods"), None)
    if periods and periods.status == "missing":
        out.append(f"service periods: expected {len(periods.expected)}, collected {len(periods.got)}")
    filed = next((f for f in s.fields if f.field == "filed_before"), None)
    if persona.truth.filed_before and filed and filed.status != "n/a" and filed.got is not True:
        out.append("missed a prior VA claim")
    if s.fee_got is not None and s.fee_expected is not None and s.fee_got != s.fee_expected:
        out.append(f"fee: expected {s.fee_expected}%, got {s.fee_got}%")
    if persona.expected_decision == "eligible" and case.stage >= 4 and not case.prep.done and not case.parked:
        out.append("claims prep did not finish (no verified face note)")
    if s.facenote_checks and not s.facenote_checks["decisions"]:
        out.append("face note: wrong decision lines (appeal deadlines at risk)")
    if persona.identity.get("dob_typed") and case.prep.face_note and not any("DOB mismatch" in t.text for t in case.tasks):
        out.append("missed the DOB mismatch between intake and the DD-214")
    if s.flag_decision_correct is False:
        out.append(f"flag decision: expected {s.flag_decision_expected}, got {s.flag_decisions or 'no flag'}")
    return out


def score_run(persona: Persona, run: CaseRun) -> Score:
    case = run.case
    fee_doc = service(run.rt, case.case_id).live("fee_agreement")
    s = Score(
        persona_id=persona.id,
        condition=run.condition,
        expected_end=expected_end(persona, case),
        end_state=end_state(case),
        scenario_pass=False,
        completed=run.completed,
        error=run.error.strip().splitlines()[-1].split(":")[0] if run.error else "",
        fields=score_fields(persona, case),
        fee_expected=persona.expected.get("fee_pct"),
        fee_got=fee_doc.terms.get("fee_pct") if fee_doc else None,
        model_failures=run.model_failures,
        **question_metrics(run, case),
        **orchestrator_metrics(run, persona),
        **claims_prep_metrics(run, persona, case),
        **cost_metrics(run),
    )
    scored = [f for f in s.fields if f.status != "n/a"]
    s.field_accuracy = sum(f.status == "correct" for f in scored) / len(scored) if scored else None
    s.scenario_pass = run.completed and s.end_state == s.expected_end
    s.critical_errors = critical_errors(s, run, persona, case)
    return s


def crashed_score(persona: Persona, condition: str, exc: BaseException) -> Score:
    """A run that could not even start (e.g. the runtime couldn't be built)."""
    name = type(exc).__name__
    return Score(persona_id=persona.id, condition=condition, expected_end=EXPECTED_END.get(persona.expected_decision, "?"),
                 end_state="crashed", scenario_pass=False, completed=False, error=name,
                 critical_errors=[f"run crashed: {name}"])  # fmt: skip
