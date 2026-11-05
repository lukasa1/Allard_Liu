"""Intake's memory in code: the typed checklist, answer parsing, stop rules.

The checklist is rebuilt from the case file's answers on every turn and after every answer:

  screen  pass 1: the `screen` questions of questions.yaml whose visibility holds, except the
          ones the secure form collects (they are the 21-22a's job in stage 2)
  pass2   pass 2: every visible question of the firm's form not yet settled (pass-1 questions
          that became relevant included, secure-form ones too), one `confirm:<question>` per open
          C-file conflict, then the narrative prompts for each claimed condition; after the
          orchestrator moved the case back to pass 2, `claim_conditions` again (the reopen item)
          until it is re-recorded

In the eval condition `ask_no_probes` the verification probes are left out (casefile.EvalCondition).
A field is settled when it has an answer or is marked unknown. Answers are keyed by question id;
narratives by `narrative:<condition>:<prompt id>`. The firm's stop rules run on the same record.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from agent.casefile import CaseFile, StopRule, Task
from agent.intake import rules
from agent.intake.parsing import (
    DISCHARGE_WORDS,
    DISCHARGES,
    HEDGE,
    _scan_discharges,
    coerce,
    named_discharges,
    parse_service_periods,
)
from agent.intake.questions import QuestionBank, is_visible, parse_show_if
from agent.intake.schema import NON_HONORABLE, IntakeRecord

BANK = QuestionBank.load()
# Not asked as questions: C-file conflicts are `confirm:` items, and a new condition is added by
# recording the full claim_conditions list again.
SKIP = {"cfile_discrepancy_check", "add_condition"}
# Secure-form questions -> the vault field that answers them.
VAULT_FIELD = {
    "first_name": "first_name", "last_name": "last_name", "street": "address.line1",
    "city": "address.city", "state": "address.state", "zip": "address.zip",
    "cell_phone": "phone", "email": "email",
}  # fmt: skip


# Stop-rule fields: the model passes the structured value it understood (`value`), and
# the veteran's words stay the raw answer. Free text alone counts only when it is plain ("yes",
# "no", "70%", "honorable", "OTH"); a hedge ("I think", "probably") is unsure: ask again.
STRICT = {"is_veteran", "service_periods", "other_service_periods", "receiving_va_pay", "rating_pct", "prior_attorney"}
_HINT = {"bool": "true or false", "int": "an integer 0-100",
         "service_periods": f"a list of periods, each discharge one of {', '.join(DISCHARGES)} or null"}  # fmt: skip
# Screening fields the firm's stop rules and the fee can't do without: unknown in pass 1 sends
# the case to a person.
UNRESOLVED = {"is_veteran": "whether the person served", "service_periods": "the service periods",
              "receiving_va_pay": "whether they get VA disability pay", "rating_pct": "their VA rating",
              "prior_attorney": "whether a lawyer helped before (the fee depends on it)"}  # fmt: skip
_VSO = re.compile(r"\b(vso|dav|vfw|american legion|amvets|service officer|veterans service)\b", re.IGNORECASE)
_LAWYER = re.compile(r"\b(attorney|lawyer|law firm|accredited agent|claims agent)\b", re.IGNORECASE)


class StrictError(ValueError):
    """A stop-rule field's answer code won't read: the message tells the model what to do."""


class ChecklistItem(BaseModel):
    """One missing field, as the model sees it in its context."""

    id: str
    type: str
    ask: str
    how: str  # chat | secure_form (request_secure_info) | confirm (a C-file conflict)
    options: list[str] = []


def record(case: CaseFile) -> IntakeRecord:
    """The answers as an IntakeRecord (what visibility, the stop rules and the fee read). An answer
    whose question a later answer hid (rating_pct after receiving_va_pay became false) is dropped."""
    hidden: set[str] = set()
    while True:
        rec = _record(case, hidden)
        stale = {q.id for q in BANK.structured if q.id in case.answers and q.id not in hidden and _hidden(q, rec)}
        if not stale:
            return rec
        hidden |= stale


def _hidden(q, rec: IntakeRecord) -> bool:
    """Not visible, and every field its show_if reads is answered (an unanswered gate, e.g. a
    C-file prefill before screening asked it, hides nothing). A probe that writes its own gate
    (prior_claim_probe sets filed_before) never hides itself."""
    gates = [f for f, _, _ in parse_show_if(q.show_if)] if q.show_if else []
    return (q.field not in gates and not is_visible(q, rec)
            and all(getattr(rec, f) not in (None, [], "") for f in gates))  # fmt: skip


def _record(case: CaseFile, hidden: set[str]) -> IntakeRecord:
    data: dict[str, Any] = {}
    for q in BANK.structured:
        ans = case.answers.get(q.id)
        if q.id in hidden or ans is None or ans.unknown or ans.value is None:
            continue
        if q.type == "service_periods_append":
            data[q.field] = [*data.get(q.field, []), *ans.value]
        else:
            data[q.field] = ans.value
    data["cfile_discrepancies"] = [c.question for c in case.conflicts if not c.resolved_at]
    return IntakeRecord.model_validate(data)


def _questions(case: CaseFile, part: str) -> list[ChecklistItem]:
    rec, items = record(case), []
    for q in BANK.structured:
        if q.id in SKIP or q.id in case.answers or q.stage == "reopen" or not is_visible(q, rec):
            continue
        if q.probe and case.eval_condition == "ask_no_probes":
            continue
        if part == "screen" and (q.stage != "screen" or q.source == "secure_form"):
            continue
        how = "secure_form" if q.source == "secure_form" else "chat"
        items.append(ChecklistItem(id=q.id, type=q.type, ask=q.ask, how=how, options=list(q.options)))
    return items


def _discharges(case: CaseFile) -> list[ChecklistItem]:
    """A service period on file without a character of discharge keeps its question open: the
    firm's stop rule must be decidable before anything is signed."""
    items = []
    for qid in ("service_periods", "other_service_periods"):
        ans = case.answers.get(qid)
        open_ = [p for p in (ans.value or []) if isinstance(p, dict) and not p.get("discharge")] if ans else []
        if open_:
            which = "; ".join(f"{p.get('branch')} {p.get('start')} to {p.get('end')}" for p in open_)
            items.append(ChecklistItem(id=qid, type=BANK.by_id[qid].type, how="chat",
                                       ask=f"The character of discharge is missing for: {which}. Ask what it was "
                                           f"(honorable, general, other than honorable, ...) and record_answer {qid} "
                                           "again with the full list as `value`, discharge included."))  # fmt: skip
    return items


def _conflicts(case: CaseFile) -> list[ChecklistItem]:
    return [
        ChecklistItem(
            id=f"confirm:{c.question}",
            type=BANK.by_id[c.question].type,
            how="confirm",
            ask=(f"The C-file ({c.cite}) says {c.cfile!r}; the answer on file is {c.on_file!r}. "
                 f"Ask which is right and record_answer {c.question!r} with it."),
        )
        for c in case.conflicts
        if not c.resolved_at
    ]


def _reopened(case: CaseFile) -> list[ChecklistItem]:
    """The reopen item: after a move back to pass 2, claim_conditions is asked again (with the
    orchestrator's reason) until it is recorded after the move."""
    ans, reopen = case.answers.get("claim_conditions"), case.reopen
    if reopen is None or not reopen.pending(ans):
        return []  # not reopened, re-recorded since, or unanswered (then it is a question anyway)
    q = BANK.by_id["add_condition"]
    return [ChecklistItem(id="claim_conditions", type=q.type, how="chat",
                          ask=f"The case was reopened: {reopen.reason}. {q.ask} Then record_answer "
                              "claim_conditions with the full list (the new condition included).")]  # fmt: skip


def _narratives(case: CaseFile) -> list[ChecklistItem]:
    items = []
    for condition in record(case).claim_conditions:
        for p in BANK.narrative:
            key = f"narrative:{condition}:{p.id}"
            if not p.auto and key not in case.answers:  # h01 is the condition itself
                items.append(ChecklistItem(id=key, type="narrative", ask=p.ask.format(condition=condition), how="chat"))
    return items


def missing(case: CaseFile, part: str) -> list[ChecklistItem]:
    if part == "screen":
        return _questions(case, "screen") + _discharges(case)
    return _questions(case, "pass2") + _discharges(case) + _conflicts(case) + _reopened(case) + _narratives(case)


def stop_rule(rec: IntakeRecord, service_known: bool = True) -> StopRule | None:
    """The firm's stop rules, in code: the model never makes these calls. `service_known`:
    both service questions are answered, so "every period is non-honorable" can be decided."""
    if rec.is_veteran is False:
        return StopRule(rule="not_veteran", reason=rules.RULES["not_veteran"].text)
    if rec.rating_pct == 100:
        return StopRule(rule="rated_100", reason=rules.RULES["rated_100"].text)
    periods = rec.service_periods
    if service_known and periods and all(p.discharge in NON_HONORABLE for p in periods):
        return StopRule(rule="non_honorable_period", reason=rules.RULES["non_honorable_period"].text,
                        to="needs_human")  # fmt: skip
    return None


NON_HONORABLE_TASK = "an attorney reviews this period (VA decides the character of discharge, 38 CFR 3.12)"


def mark_non_honorable(case: CaseFile, rec: IntakeRecord) -> None:
    """When only some periods are non-honorable, the case goes on and a staff task names each such
    period for the attorney (VA decides the character of discharge per period, 38 CFR 3.12)."""
    periods = rec.service_periods
    if not periods or all(p.discharge in NON_HONORABLE for p in periods):
        return
    for p in periods:
        if p.discharge in NON_HONORABLE:
            text = (f"Service period {p.start} to {p.end} ({p.branch}) ended {p.discharge}: "
                    f"{NON_HONORABLE_TASK}; intake goes on for the other period(s).")  # fmt: skip
            # one task per period: the same period with its months filled in later (prefill) is not new
            if not any(_same_period_task(t.text, p) for t in case.tasks):
                case.tasks.append(Task(kind="staff", text=text))


_PERIOD_TASK = re.compile(r"^Service period (\S+) to (\S+) \(([^)]*)\) ended (\S+?):")


def _same_period_task(text: str, p: Any) -> bool:
    """`text` is this period's task: the same start and end years, branch and discharge (the months may differ)."""
    from agent.intake.parsing import canonical_branch

    m = _PERIOD_TASK.match(text)
    if not m or NON_HONORABLE_TASK not in text:
        return False
    start, end, branch, discharge = m.groups()
    return (start[:4], end[:4], canonical_branch(branch), discharge) == (
        str(p.start)[:4], str(p.end)[:4], canonical_branch(str(p.branch)), str(p.discharge))


def refresh(case: CaseFile) -> None:
    """Rebuild the checklist of the current pass and run the stop rules. Mutates `case`."""
    case.checklist["screen"] = [i.id for i in missing(case, "screen")]
    if case.stage >= 4:
        case.checklist["pass2"] = [i.id for i in missing(case, "pass2")]
    if case.stop is None:
        rec = record(case)
        # without the probes (an eval condition) nobody asks about other periods: decide on the first
        others = "other_service_periods" in case.answers or case.eval_condition == "ask_no_probes"
        known = "service_periods" in case.answers and others
        case.stop = stop_rule(rec, known) or _unresolved(case)
        if case.stop is None:
            mark_non_honorable(case, rec)


def _unresolved(case: CaseFile) -> StopRule | None:
    """Pass 1 (before anything is filed): an UNRESOLVED field marked unknown means the stop rules
    or the fee can't be decided, so a person on the team follows up."""
    gaps = [label for qid, label in UNRESOLVED.items() if (a := case.answers.get(qid)) and a.unknown]
    if not gaps or case.stage > 2:
        return None
    return StopRule(rule="screen_unresolved", reason=f"{rules.RULES['screen_unresolved'].text} Unknown: "
                    f"{', '.join(gaps)}.", to="needs_human")  # fmt: skip


def fee_pct(case: CaseFile) -> int | None:
    """The fee % for the fee agreement (rules.fee_pct, a firm-policy placeholder), or None while
    prior representation is unanswered or unknown (then a person decides: UNRESOLVED)."""
    ans = case.answers.get("prior_attorney")
    return rules.fee_pct(record(case)) if ans and not ans.unknown else None


def question_type(key: str) -> tuple[str, tuple[str, ...]]:
    """(type, options) of a question id or narrative key; KeyError if there is none."""
    if key.startswith("narrative:"):
        pid = key.split(":", 2)[-1]
        if pid not in {p.id for p in BANK.narrative}:
            raise KeyError(key)
        return "narrative", ()
    q = BANK.by_id[key]
    return q.type, q.options


def parse(key: str, text: str, value: Any = None, known_periods: list | None = None) -> Any:
    """Parse an answer in code: simple fields (yes/no, dates, branch, discharge, lists) are
    read by parsing.coerce; free text is kept as given. `value` is the structured value the model
    understood (used instead of `text` when given). Raises ValueError when it can't be read;
    StrictError for a stop-rule field (STRICT) whose answer is hedged or not plain.
    `known_periods`: the service periods already on file. For other_service_periods, a period the
    veteran only restates ("No, just the Army, 2004 to 2010") is not another one."""
    qtype, options = question_type(key)
    text = text.replace("\u2019", "'")  # a curly apostrophe ("don’t", "there’s") reads as a plain one
    if key in STRICT:
        value = _strict(key, qtype, text, value, known_periods or [])
    else:
        value = coerce(qtype, text if value is None else value, options)
    return [v.model_dump() if isinstance(v, BaseModel) else v for v in value] if isinstance(value, list) else value


def _strict(key: str, qtype: str, text: str, value: Any, known: list) -> Any:
    periods = qtype.startswith("service_periods")
    if periods:
        text = _drop_date_hedges(text)
    if hedge := _answer_hedge(text):
        about = ("Approximate dates (a year alone) are fine; only an unsure discharge "
                 "is asked again" if periods else "Ask again to confirm")  # fmt: skip
        raise StrictError(f"the veteran sounds unsure ({hedge!r}), and {key} decides whether the "
                          f"firm can take the case. {about}. Mark it unknown only if they say "
                          "they don't know.")  # fmt: skip
    if key == "prior_attorney" and value is None and _VSO.search(text) and not _LAWYER.search(text):
        return False  # "A VSO from the DAV": a VSO doesn't count (the question says so)
    try:
        out = coerce(qtype, text if value is None else value, (), strict=True)
        if qtype == "service_periods_append":  # never the same enlistment twice
            restated = [p for p in out if _restated(p, known)]
            if not [p for p in out if not _restated(p, known)]:  # nothing new: a discharge here is the first one's
                _first_period_discharge(text, restated, known)
            out = [p for p in out if not _restated(p, known)]
        if value is not None and qtype.startswith("service_periods"):
            out = _no_invented_months(text, out, known)
        if value is not None:
            _cross_check(qtype, text, value, out, known)
    except ValueError as err:
        raise StrictError(f"could not read {key}: {err}. {key} is a stop-rule field, so code reads only "
                          "plain answers. Pass the structured value you understood in `value` "
                          f"({_HINT[qtype.removesuffix('_append')]}) and keep the veteran's words in `a`. "
                          "If their answer is really unclear, ask again; don't mark it unknown unless "
                          "they say they don't know.") from err  # fmt: skip
    if key == "service_periods" and not out:
        raise StrictError("service_periods needs at least one period: someone who served has one (a short "
                          "stint, even one ended in basic training, is a period, often 'uncharacterized'). "
                          "If they never served, record_answer is_veteran false again; if they can't say, "
                          "mark service_periods unknown (a person on the team follows up).")  # fmt: skip
    return out


def _no_invented_months(text: str, periods: list, on_file: list) -> list:
    """A month the veteran didn't say isn't recorded: "2001 to 2005" stays 2001-2005 even if the
    model's value says 2001-01 to 2005-12. The DD-214 fills the months later. A month
    already on file (given in an earlier message) is kept."""
    from agent.cfile.facts import same_period
    from agent.intake.parsing import canonical_branch
    from agent.intake.schema import ServicePeriod

    said = parse_service_periods(text) or []
    for p in periods:  # the period said with the same component and start year first, then any match
        exact = [s for s in said if s.component == p.component and (s.start or "")[:4] == (p.start or "")[:4]]
        match = next((s for s in exact + said if same_period(s, p)), None)
        for end in ("start", "end"):
            told, got = getattr(match, end, None) if match else None, getattr(p, end)
            kept = any(getattr(k, end) == got for k in (ServicePeriod.model_validate(x) for x in on_file)
                       if _restated(p, [k]) or (canonical_branch(k.branch) == canonical_branch(p.branch)
                                                and (k.component or "active") == (p.component or "active")))  # fmt: skip
            if not said and got and len(got) > 4 and _year_alone(text, got[:4]):
                told = got[:4]  # "2004 to 2008, honorable": no branch word, so read the years alone
            if told and got and len(told) == 4 and got.startswith(f"{told}-") and not kept:
                setattr(p, end, told)
    return periods


_MONTH_WORD = (r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sept?(ember)?|oct(ober)?"
               r"|nov(ember)?|dec(ember)?)\b\.?")


def _year_alone(text: str, year: str) -> bool:
    """`year` is in `text` and no month is said with it ("2004", not "March 2004" or "3/2004")."""
    low = text.lower()
    if not re.search(rf"(?<!\d){year}(?!\d)", low):
        return False
    return not re.search(rf"({_MONTH_WORD}\s*,?\s*(of\s+)?{year}|\b\d{{1,2}}\s*[/.-]\s*(\d{{1,2}}\s*[/.-]\s*)?{year}"
                         rf"|{year}\s*[/-]\s*\d{{1,2}}\b)", low)


def _restated(period: Any, known: list) -> bool:
    """`period` is one already on file, said again: same branch and component, the same start and
    end years, and no different discharge. Stricter than prefill's same_period (an enlistment
    within a year), so a real second period in the same branch (washed out, then re-enlisted; a
    short active stint, then the Guard) is never taken for the first. No dates: never a repeat."""
    from agent.intake.parsing import canonical_branch
    from agent.intake.schema import ServicePeriod

    p = ServicePeriod.model_validate(period)

    def same(k: ServicePeriod) -> bool:
        years = (p.start or "")[:4], (p.end or "")[:4], (k.start or "")[:4], (k.end or "")[:4]
        return (all(years) and years[:2] == years[2:]
                and canonical_branch(p.branch) == canonical_branch(k.branch)
                and (p.component or "active") == (k.component or "active")
                and (not p.discharge or not k.discharge or p.discharge == k.discharge))  # fmt: skip

    return any(same(ServicePeriod.model_validate(k)) for k in known)


def _first_period_discharge(text: str, said: list, known: list) -> None:
    """An answer about other periods that gives the first period's discharge ("No, just the one.
    It was OTH") must not lose it: if it names a discharge the periods on file don't have, the
    first period's answer is recorded again with it (a non-honorable one is a stop rule)."""
    from agent.intake.schema import ServicePeriod

    if not known:
        return
    on_file = {ServicePeriod.model_validate(k).discharge for k in known}
    found, _ = _scan_discharges(text)  # None when negated ("never OTH"): nothing to hold on to
    named = (found or set()) | {ServicePeriod.model_validate(p).discharge for p in said
                                                  if ServicePeriod.model_validate(p).discharge and _restated(p, known)}  # fmt: skip
    if new := named - on_file:
        raise ValueError(f"the veteran gave the discharge {', '.join(sorted(new))} for the period on file "
                         f"(it has {sorted(d for d in on_file if d) or 'none'}): record_answer service_periods "
                         "again with that discharge, then other_service_periods")  # fmt: skip


def _cross_check(qtype: str, text: str, value: Any, out: Any, known: list) -> None:
    """When the veteran's words are plain, the model's value must say the same (a yes/no, the
    rating, the discharges named): "OTH" in `a` with value honorable is refused."""
    if qtype in ("bool", "int"):
        said = _plain_or_none(qtype, text)
        if said is not None and said != out:
            raise ValueError(f"the veteran said {text.strip()!r} but value is {value!r}")
    elif not out and qtype == "service_periods_append":
        said = parse_service_periods(text) or []
        mentioned = [p for p in said if not _restated(p, known)]
        if not mentioned and not _MORE.search(text) and (_no_other_period(text) or said):
            return  # "Nope, just the one, honorable" / "No, just the Army, 2004 to 2010": the first period
        found, _ = _scan_discharges(text)
        if found is None or found or mentioned:  # "No, but Navy too, OTH"
            raise ValueError(f"the veteran said {text.strip()!r}, which mentions another period or "
                             "discharge, but value is empty")  # fmt: skip
    elif (said := named_discharges(text)) and said != {p.discharge for p in out if p.discharge}:
        raise ValueError(f"the veteran said {text.strip()!r} (discharge {', '.join(sorted(said))}) but value has "
                         f"{[p.discharge for p in out]}")  # fmt: skip


# A clause that hedges only on when: it names a date or month and no discharge ("not sure of the
# exact months", "2004 to 2010 I believe"). Approximate dates are fine for a service period.
_CLAUSE = re.compile(r"[^.!?;,\n]+[.!?;,\n]*")
_WHEN = re.compile(r"\b((19|20)\d{2}|months?|years?|dates?|when|summer|winter|spring|fall|in may|jan\w*|feb\w*|"
                   r"mar\w*|apr\w*|june?|july?|aug\w*|sept?\w*|oct\w*|nov\w*|dec\w*)\b", re.IGNORECASE)  # fmt: skip


_KEEP = re.compile(r"\b(upgrad|downgrad|chang|kick|boot|court[- ]martial|discharg|separat)", re.IGNORECASE)


def _drop_date_hedges(text: str) -> str:
    """`text` with the hedge words removed from clauses that hedge only on when (a date or month,
    nothing about the discharge or how service ended). Nothing else is removed."""
    out, stripped = [], False
    for clause in _CLAUSE.findall(text):
        if stripped:  # "not sure of the months, but Army ... OTH": the "but" only turned from the hedge
            clause = re.sub(r"^\s*but\b", "", clause, flags=re.IGNORECASE)
        stripped = bool(HEDGE.search(clause) and _WHEN.search(clause)
                        and not DISCHARGE_WORDS.search(clause.lower()) and not _KEEP.search(clause))  # fmt: skip
        if stripped:
            clause = HEDGE.sub("", clause)
        out.append(clause)
    return "".join(out)


def _no_other_period(text: str) -> bool:
    """ "No, just the one, honorable": a no that names no further period and doesn't turn."""
    return parse_service_periods(text) == [] and not _MORE.search(text)


_MORE = re.compile(r"\b(but|though|although|except|actually|also|too|again|another|went back|re-?enlist\w*)\b",
                   re.IGNORECASE)  # fmt: skip
_SENTENCE = re.compile(r"[.!?;\n]+")
# A later sentence is about the answer when it is only a hedge ("Probably.") or names service.
_TOPIC = re.compile(r"\d|\b(army|navy|marines?|air force|coast guard|space force|guard|reserves?|served|service|"
                    r"discharg\w*|honou?r\w*|dishonou?r\w*|general|oth|conduct|rating|percent|lawyer|attorney|"
                    r"agent|firm|vso|dav|vfw)\b", re.IGNORECASE)  # fmt: skip
_BARE = re.compile(r"\b(so|yes|yeah|no|it|that|though|i|was|is|um|well|but|not)\b|\W", re.IGNORECASE)


def _answer_hedge(text: str) -> str | None:
    """A hedge on the answer itself: in the first sentence, in a later bare hedge ("Probably."), or
    in a later sentence about service. "Yes. My knees probably got wrecked there." is a plain yes."""
    for i, sentence in enumerate(s for s in _SENTENCE.split(text) if s.strip()):
        about_it = i == 0 or _TOPIC.search(sentence) or not _BARE.sub("", HEDGE.sub("", sentence)).strip()
        if about_it and (hedge := HEDGE.search(sentence)):
            return hedge.group(0)
    return None


def _plain_or_none(qtype: str, text: str) -> Any:
    try:
        return coerce(qtype, text, (), strict=True)
    except ValueError:
        return None
