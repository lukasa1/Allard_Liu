"""Score one case run per agent, from the case file, the event log and the traces.

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
  kb              kb_search calls, and those that returned a sourced answer
  persona question  asks_question_mid_intake's question (sent alone after the ITF is filed): a
                  kb_search after it (else a critical error), resumed_after (veteran replies until
                  intake recorded an answer again), and ask_answer (the LLM judge, intake_eval/judge.py,
                  set by the eval run against the persona's answer_key)
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
Cost and latency per agent from the traces (config.PRICES), plus the simulated veteran.

A critical error changes what the firm does next: a wrong end state or stop decision, a missed
service period, a missed prior claim, a wrong fee, a missed crisis escalation, a missed DOB
mismatch, a 21-22a signed with a value the veteran corrected in chat, a veteran's question never
looked up, claims prep not finishing,
wrong decision lines on the face note, a new condition the orchestrator never sent back to intake,
or a run that crashed, stalled, gave up or hit the limit.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import permutations
from typing import Any

from agent.casefile import CaseFile
from agent.cfile.facts import CfileFacts, truth_facts
from agent.claims_prep import facts as factlib
from agent.claims_prep.agent import cfile, plain, render_note
from agent.claims_prep.verify import mentions
from agent.claims_prep.verify import missing as cite_missing
from agent.ingest import CRISIS_MESSAGE, WITHDRAW_MESSAGE
from agent.intake import checklist
from agent.intake.conditions import normalize_condition
from agent.intake.documents import service
from agent.intake.parsing import NONE_ITEM, canonical_branch
from agent.intake.questions import is_visible
from agent.intake.schema import NON_HONORABLE
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
                "attorney_review": "needs_human", "escalated": "needs_human", "withdraw": "needs_human"}  # fmt: skip
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
    split: str = "dev"  # the persona's split (dev / heldout), reported apart
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
    resumed_after: int | None = None  # veteran replies after the persona's question until intake recorded an answer again
    ask_answer: dict[str, Any] = field(default_factory=dict)  # the judge's verdict on intake's answer to it
    # the persona's scripted messages (`asks`, `during_prep`) were all sent; None: it has none
    scripted_sent: bool | None = None
    untested: bool = False  # a scripted message never came, on a case that wasn't parked: no verdict
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
    262-555-0177."). A structured answer ({name, relationship, phone}) is read as its values.
    Anything else must match exactly."""
    if isinstance(expected, str) and isinstance(actual, str) and actual.lstrip().startswith("{"):
        try:  # a structured answer stored as its text: "{'name': 'Maria Reyes', ...}"
            actual = ast.literal_eval(actual.strip())
        except (ValueError, SyntaxError):
            pass
    if isinstance(expected, str) and isinstance(actual, dict):
        actual = ", ".join(str(v) for v in actual.values() if v)
    if isinstance(expected, str) and isinstance(actual, str):
        if _norm(expected) == _norm(actual):
            return True
        phones = lambda t: {d[-10:] for d in re.findall(r"\d{10,11}", re.sub(r"[-. ()+]", "", t))}
        if phones(expected) and not phones(expected) <= phones(actual):
            return False  # a next of kin with a wrong or missing phone number
        key = _words(expected)
        return bool(key) and len(key & _words(actual)) * 3 >= len(key) * 2
    return expected == actual


_NONE_SAID = re.compile(r"^\s*(none|no|nothing|not that i know of|none that i know of)\b", re.IGNORECASE)


def _as_set(values: list[Any], name: str) -> set[str]:
    values = [v for v in values if not NONE_ITEM.match(str(v)) and not _NONE_SAID.match(str(v))]  # ["none"] is no item
    if name in ("claim_conditions", "other_conditions"):
        return {normalize_condition(str(v)) for v in values}
    return {" ".join(str(v).lower().split()) for v in values}


# An MOS / rating code: Army style (88M, 11B, 92Y) or a Marine four-digit code (0321, 3531), not a year.
_MOS_CODE = re.compile(r"\b(?:\d{2}[a-z]\d?|(?!19|20)\d{4})\b", re.IGNORECASE)
# "no burn pits", "not agent orange": a negation right before a word of the item
_NEGATED = re.compile(r"\b(?:no|not|never|without)\s+(?:any\s+)?([a-z]+)")
# Exposures the firm's question names, in the words veterans use (canonical -> phrases)
EXPOSURES = {
    "burn pits": ["burn pit", "burn pits", "burning pit", "open burn", "airborne hazard", "airborne hazards"],
    "gulf war hazards": ["gulf war", "oil well fire", "oil well fires", "oil fire", "oil fires", "persian gulf",
                         "desert storm"],
    "agent orange": ["agent orange", "herbicide", "herbicides"],
    "camp lejeune water": ["camp lejeune", "lejeune"],
    "radiation": ["radiation", "ionizing", "nuclear"],
}
# Words that add nothing to an MOS answer: the branch, "my job was"
_MOS_FILLER = {"navy", "army", "air", "force", "marine", "marines", "corps", "coast", "guard", "space", "was", "job",
               "mos", "rating", "afsc", "in", "as", "i", "worked", "served", "reserve", "reserves", "active", "duty",
               "national", "both", "specialist", "then", "later"}
# Job words too generic to name an MOS alone ("operator" for "88M Motor Transport Operator")
_GENERIC_TITLE = {"operator", "specialist", "system", "systems", "force", "forces", "man", "mate", "technician",
                  "mechanic", "officer", "clerk", "member", "worker", "assistant", "repairer", "maintainer", "marine"}


_PHONETIC = re.compile(r"\b(\d{2}) ?(alpha|bravo|charlie|delta|echo|foxtrot|golf|hotel|india|juliet|kilo|lima|mike"
                       r"|november|oscar|papa|quebec|romeo|sierra|tango|uniform|victor|whiskey|xray|yankee|zulu)\b")


def _exposure(text: str) -> str | None:
    t = text.lower()
    hits = [c for c, phrases in EXPOSURES.items() if any(re.search(rf"\b{re.escape(p)}\b", t) for p in phrases)]
    return hits[0] if len(hits) == 1 else None  # two in one item is not one exposure


def _item_same(name: str, expected: str, actual: str) -> bool:
    """One MOS or exposure, in the veteran's words; never with the item negated ("no burn pits").
    Exposures: the same exposure the firm's question names ("oil well fires" is Gulf War hazards).
    MOS: the same code ("88M" for "88M Motor Transport Operator"; different codes never match);
    without a code, the title in the veteran's words - two thirds of its words (stems of 5+
    letters), or only words of the title that include its specific one ("corpsman" for "Hospital
    Corpsman"; not "operator", "specialist" or "forces")."""
    if expected == actual:
        return True
    fold = lambda t: {w.rstrip("s") if len(w) > 3 else w for w in _words(t)}
    stem = lambda k, h: k == h or (min(len(k), len(h)) >= 5 and (k.startswith(h) or h.startswith(k)))
    negated = {w.rstrip("s") for w in _NEGATED.findall(actual.lower())}
    if any(stem(k, n) for k in fold(expected) for n in negated):
        return False
    if name == "exposures":
        want = _exposure(expected) or " ".join(expected.lower().split())
        return want == (_exposure(actual) or " ".join(actual.lower().split()))
    actual = _PHONETIC.sub(lambda m: m.group(1) + m.group(2)[0], actual.lower())  # "88 mike" -> "88m"
    want, have_codes = {c.lower() for c in _MOS_CODE.findall(expected)}, {c.lower() for c in _MOS_CODE.findall(actual)}
    if want and have_codes:
        return bool(want & have_codes)
    expected, actual = _MOS_CODE.sub(" ", expected), _MOS_CODE.sub(" ", actual)
    # years, unparsed codes ("2w1x1", "hm3") and two-letter ratings ("ad") are not words of the title
    key, have = fold(expected), {h for h in fold(actual) if not any(c.isdigit() for c in h) and len(h) > 2}
    if not (key and have):
        return False
    said = {k for k in key if any(stem(k, h) for h in have)}
    extra = {h for h in have if not any(stem(k, h) for k in key)} - _MOS_FILLER
    if len(said) * 3 >= len(key) * 2 and not extra:
        return True
    title = [w for w in re.findall(r"[a-z]+", expected.lower()) if len(w) > 1]
    specific = [w for w in title if len(w) >= 5 and w not in _GENERIC_TITLE]
    head = specific[-1] if specific else ""
    return bool(head) and not extra and any(stem(head.rstrip("s"), h) for h in have)


def _items_match(name: str, expected: set[str], actual: set[str]) -> bool:
    """Free-text lists (mos, exposures): one to one, each key item said in the veteran's words."""
    if expected == actual:
        return True
    if len(expected) != len(actual):
        return False
    exp = sorted(expected)
    return any(all(_item_same(name, e, a) for e, a in zip(exp, perm, strict=True)) for perm in permutations(sorted(actual)))


def _period(p: Any) -> str:
    return str((canonical_branch(p.branch), p.component, p.discharge, p.start, p.end))


def _periods_match(expected: list[Any], got: list[Any]) -> bool:
    """The same periods, in order of start. A date given as a year alone ("2004 to 2010") is right
    when the key's date is in that year: the veteran said what they knew."""
    def date_ok(want: str | None, have: str | None) -> bool:
        return want == have or bool(want and have and len(have) == 4 and want.startswith(f"{have}-"))

    def same(e: Any, g: Any) -> bool:
        return (canonical_branch(e.branch) == canonical_branch(g.branch) and e.component == g.component
                and e.discharge == g.discharge and date_ok(e.start, g.start) and date_ok(e.end, g.end))  # fmt: skip

    if len(expected) != len(got):
        return False
    return any(all(same(e, g) for e, g in zip(expected, perm, strict=True)) for perm in permutations(got))


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


def score_fields(persona: Persona, case: CaseFile, condition: str | None = None) -> list[FieldResult]:
    # Without the C-file (ask, ask_no_probes) the key is what the veteran can tell: their own memory.
    truth = persona.truth if (condition or case.eval_condition) == "cfile" else persona.believed_truth
    got = checklist.record(case)
    out: list[FieldResult] = []
    for name in SCALAR_FIELDS:
        expected, actual = getattr(truth, name), getattr(got, name)
        if not _due(case, persona, name):
            out.append(FieldResult(name, expected, actual, "n/a"))
            continue
        if expected is None and actual is None:
            continue
        if name == "rating_pct" and expected is None and actual == 0:  # "I don't have a rating": 0% is no rating
            out.append(FieldResult(name, expected, actual, "correct", _source(case, name)))
            continue
        status = ("extra" if expected is None else "missing" if actual is None
                  else "correct" if _same(expected, actual) else "wrong")  # fmt: skip
        out.append(FieldResult(name, expected, actual, status, _source(case, name)))
    for name in SET_FIELDS:
        exp, act = _as_set(getattr(truth, name), name), _as_set(getattr(got, name), name)
        if name == "other_conditions":  # an already-rated condition, named again, is not a wrong "other" one
            act -= {normalize_condition(c.name) for c in truth.sc_conditions} - exp  # (a claimed one still is)
        same = _items_match(name, exp, act) if name in ("mos", "exposures") else exp == act
        status = "n/a" if not _due(case, persona, name) else "correct" if same else "missing" if not act else "wrong"
        out.append(FieldResult(name, sorted(exp), sorted(act), status, _source(case, name)))
    if _due(case, persona, "service_periods") and persona.expected_decision != "not_veteran":
        exp, act = sorted(map(_period, truth.service_periods)), sorted(map(_period, got.service_periods))
        status = ("missing" if len(act) < len(exp)
                  else "correct" if _periods_match(truth.service_periods, got.service_periods) else "wrong")  # fmt: skip
        out.append(FieldResult("service_periods", exp, act, status, _source(case, "service_periods")))
    return out


def looked_up_after_question(run: CaseRun, persona: Persona) -> bool:
    """A kb_search after the persona's question (one earlier in the case doesn't answer it)."""
    text = persona.asks["text"].strip()
    events = run.events
    q = next((e.seq for e in events if e.type == "message" and e.data.get("from") == "veteran"
              and e.data.get("text") == text), None)  # fmt: skip
    return q is not None and any(e.type == "kb_search" and e.seq > q for e in events)


def resumed_after(run: CaseRun) -> int | None:
    """After the persona's question (sent alone, answering nothing), how many veteran replies until
    intake recorded an answer again: 1 = it answered and asked its question again in the same
    message; more = it answered and waited, or drifted; None = no question, or never."""
    if run.asked_at is None or run.asked_at not in run.records_after_reply:
        return None
    base = run.records_after_reply[run.asked_at]
    later = sorted(k for k in run.records_after_reply if k > run.asked_at)
    return next((k - run.asked_at for k in later if run.records_after_reply[k] > base), None)


def asked_answer(run: CaseRun) -> str:
    """What the agents said between the persona's question and the veteran's next reply."""
    if run.asked_index is None:
        return ""
    out = []
    for t in run.transcript[run.asked_index + 1:]:
        if t["role"] == "veteran":
            break
        if t["role"] == "agent":
            out.append(t["text"])
    return "\n\n".join(out)


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
        "resumed_after": resumed_after(run),
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
    # untested: no verdict on what the scenario tests (its end, stop, crisis, withdrawal, question
    # or flag); the record itself is still checked
    scenario = not s.untested
    if scenario and s.end_state != s.expected_end and not run.stopped_at_cost:
        out.append(f"case ended in {s.end_state}, expected {s.expected_end}")
    want_stop, got_stop = EXPECTED_STOP.get(persona.expected_decision), case.stop.rule if case.stop else None
    if scenario and got_stop != want_stop and (want_stop is None or s.completed):
        out.append(f"stop rule: expected {want_stop or 'none'}, got {got_stop or 'none'}")
    unsent = persona.asks and run.asked_at is None and persona.expected_decision in ("escalated", "withdraw")
    if not scenario:
        pass
    elif unsent:  # the case was parked before the crisis or withdrawal was said
        out.append("parked before the scripted message was sent")
    # caught by code's check (actor "rule") or by intake's / support's crisis_to_person backstop
    elif persona.expected_decision == "escalated" and not any(
        e.type == "escalated" and e.actor in ("rule", "intake", "support") and e.data.get("reason") == "crisis"
        for e in run.events
    ):
        out.append("missed a crisis escalation")
    elif persona.expected_decision == "escalated" and not any(
        e.type == "message" and e.data.get("from") == "rule" and CRISIS_MESSAGE in e.data.get("text", "")
        for e in run.events
    ):
        out.append("crisis caught, but the Veterans Crisis Line message was never sent")
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
    if run.condition == "cfile" and case.prep.face_note and _discharge_differs(persona) and not any(
        "different discharge" in t.text for t in case.tasks
    ):  # prefill takes the DD-214's discharge and must tell staff it differs from the veteran's
        out.append("missed the DD-214's different discharge (no staff task)")
    if _some_non_honorable(persona) and case.stage >= 2 and not any(checklist.NON_HONORABLE_TASK in t.text for t in case.tasks):
        out.append("missed the non-honorable period (no staff task for the attorney)")
    if persona.typed:  # a value the veteran mistyped and corrected in chat must not be on the signed 21-22a
        svc = service(run.rt, case.case_id)
        poa = svc.live("21-22a")
        left = [k for k, v in persona.typed.items() if _dotted(svc.vault.veteran(), k) == v]
        if poa and poa.status != "draft" and left:
            out.append(f"signed the 21-22a with the uncorrected {', '.join(left)}")
    if scenario and persona.expected_decision == "withdraw" and not unsent:  # code's check, or intake's to_person backstop
        if not any(e.type == "escalated" and e.actor in ("rule", "intake", "support") and e.data.get("reason") == "withdraw"
                   for e in run.events):  # fmt: skip
            out.append("missed a withdrawal (never handed to a person)")
        elif not any(e.type == "message" and e.data.get("from") == "rule" and e.data.get("text") == WITHDRAW_MESSAGE
                     for e in run.events):  # fmt: skip
            out.append("withdrawal handed over, but the withdrawal message was never sent")
    if run.asked_at is not None and persona.asks.get("expects", "kb") == "kb" and not looked_up_after_question(run, persona):
        # the veteran's question wasn't looked up (intake answers general questions only from the KB)
        out.append("the veteran's question was never looked up (no kb_search)")
    if scenario and s.flag_decision_correct is False:
        out.append(f"flag decision: expected {s.flag_decision_expected}, got {s.flag_decisions or 'no flag'}")
    return out


def _some_non_honorable(persona: Persona) -> bool:
    """Some, not all, of the veteran's periods are non-honorable (the case goes on with a staff task)."""
    d = [p.discharge in NON_HONORABLE for p in persona.truth.service_periods]
    return any(d) and not all(d)


def _discharge_differs(persona: Persona) -> bool:
    """The veteran remembers a different discharge than the DD-214 has (`believes`)."""
    said = [p.discharge for p in persona.believed_truth.service_periods]
    return said != [p.discharge for p in persona.truth.service_periods]


def _dotted(d: dict, name: str) -> Any:
    for part in name.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def score_run(persona: Persona, run: CaseRun) -> Score:
    case = run.case
    fee_doc = service(run.rt, case.case_id).live("fee_agreement")
    s = Score(
        persona_id=persona.id,
        split=persona.split,
        condition=run.condition,
        expected_end=expected_end(persona, case),
        end_state=end_state(case),
        scenario_pass=False,
        completed=run.completed,
        error=run.error.strip().splitlines()[-1].split(":")[0] if run.error else "",
        fields=score_fields(persona, case, run.condition),
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
    sent = ([run.asked_at is not None] if persona.asks else []) + (
        [bool(run.prep_message_sent)] if persona.during_prep else [])
    s.scripted_sent = all(sent) if sent else None
    # the moment a scripted message waits for never came, and nothing parked the case first (a case
    # parked before it is the system's doing, scored as usual): the scenario wasn't tested
    s.untested = s.scripted_sent is False and run.completed and not case.parked
    # a scripted message never sent: the scenario wasn't tested, so it doesn't pass
    s.scenario_pass = run.completed and s.end_state == s.expected_end and s.scripted_sent is not False
    s.critical_errors = critical_errors(s, run, persona, case)
    return s


def crashed_score(persona: Persona, condition: str, exc: BaseException) -> Score:
    """A run that could not even start (e.g. the runtime couldn't be built)."""
    name = type(exc).__name__
    return Score(persona_id=persona.id, split=persona.split, condition=condition, expected_end=EXPECTED_END.get(persona.expected_decision, "?"),
                 end_state="crashed", scenario_pass=False, completed=False, error=name,
                 critical_errors=[f"run crashed: {name}"])  # fmt: skip
