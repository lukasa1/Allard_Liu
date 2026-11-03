"""Intake's memory in code (L15, L16, L18, A1): the typed checklist, answer parsing, stop rules.

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

from agent.casefile import CaseFile, StopRule
from agent.intake import rules
from agent.intake.parsing import DISCHARGES, HEDGE, coerce
from agent.intake.questions import QuestionBank, is_visible
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


# Stop-rule fields (A1, D22): the model passes the structured value it understood (`value`), and
# the veteran's words stay the raw answer. Free text alone counts only when it is plain ("yes",
# "no", "70%", "honorable", "OTH"); a hedge ("I think", "probably") is unsure: ask again.
STRICT = {"is_veteran", "service_periods", "other_service_periods", "receiving_va_pay", "rating_pct", "prior_attorney"}
_HINT = {"bool": "true or false", "int": "an integer 0-100",
         "service_periods": f"a list of periods, each discharge one of {', '.join(DISCHARGES)} or null"}  # fmt: skip
# Screening fields the firm's stop rules (A1) can't do without: unknown sends the case to a person.
UNRESOLVED = {"is_veteran": "whether the person served", "service_periods": "the service periods",
              "receiving_va_pay": "whether they get VA disability pay", "rating_pct": "their VA rating"}  # fmt: skip
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
    """The answers as an IntakeRecord (what visibility, the stop rules and the fee read)."""
    data: dict[str, Any] = {}
    for q in BANK.structured:
        ans = case.answers.get(q.id)
        if ans is None or ans.unknown or ans.value is None:
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
    firm's stop rule (A1) must be decidable before anything is signed."""
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


def stop_rule(rec: IntakeRecord) -> StopRule | None:
    """The firm's stop rules (A1), in code: the model never makes these calls."""
    if rec.is_veteran is False:
        return StopRule(rule="not_veteran", reason=rules.RULES["not_veteran"].text)
    if rec.rating_pct == 100:
        return StopRule(rule="rated_100", reason=rules.RULES["rated_100"].text)
    if any(p.discharge in NON_HONORABLE for p in rec.service_periods):
        return StopRule(rule="non_honorable_period", reason=rules.RULES["non_honorable_period"].text,
                        to="needs_human")  # fmt: skip
    return None


def refresh(case: CaseFile) -> None:
    """Rebuild the checklist of the current pass and run the stop rules. Mutates `case`."""
    case.checklist["screen"] = [i.id for i in missing(case, "screen")]
    if case.stage >= 4:
        case.checklist["pass2"] = [i.id for i in missing(case, "pass2")]
    if case.stop is None:
        case.stop = stop_rule(record(case)) or _unresolved(case)


def _unresolved(case: CaseFile) -> StopRule | None:
    """Pass 1 (before anything is filed): is_veteran or service_periods marked unknown means the
    stop rules can't be decided, so a person on the team follows up."""
    gaps = [label for qid, label in UNRESOLVED.items() if (a := case.answers.get(qid)) and a.unknown]
    if not gaps or case.stage > 2:
        return None
    return StopRule(rule="screen_unresolved", reason=f"{rules.RULES['screen_unresolved'].text} Unknown: "
                    f"{', '.join(gaps)}.", to="needs_human")  # fmt: skip


def fee_pct(case: CaseFile) -> int | None:
    """The fee % for the fee agreement (rules.fee_pct, a firm-policy placeholder), or None while
    prior representation is unknown."""
    return rules.fee_pct(record(case)) if "prior_attorney" in case.answers else None


def question_type(key: str) -> tuple[str, tuple[str, ...]]:
    """(type, options) of a question id or narrative key; KeyError if there is none."""
    if key.startswith("narrative:"):
        pid = key.split(":", 2)[-1]
        if pid not in {p.id for p in BANK.narrative}:
            raise KeyError(key)
        return "narrative", ()
    q = BANK.by_id[key]
    return q.type, q.options


def parse(key: str, text: str, value: Any = None) -> Any:
    """Parse an answer in code (L16): simple fields (yes/no, dates, branch, discharge, lists) are
    read by parsing.coerce; free text is kept as given. `value` is the structured value the model
    understood (used instead of `text` when given). Raises ValueError when it can't be read;
    StrictError for a stop-rule field (STRICT) whose answer is hedged or not plain."""
    qtype, options = question_type(key)
    if key in STRICT:
        value = _strict(key, qtype, text, value)
    else:
        value = coerce(qtype, text if value is None else value, options)
    return [v.model_dump() if isinstance(v, BaseModel) else v for v in value] if isinstance(value, list) else value


def _strict(key: str, qtype: str, text: str, value: Any) -> Any:
    if hedge := HEDGE.search(text):
        raise StrictError(f"the veteran sounds unsure ({hedge.group(0)!r}), and {key} decides whether the "
                          "firm can take the case: ask again to confirm. Mark it unknown only if they say "
                          "they don't know.")  # fmt: skip
    if key == "prior_attorney" and value is None and _VSO.search(text) and not _LAWYER.search(text):
        return False  # "A VSO from the DAV": a VSO doesn't count (the question says so)
    try:
        out = coerce(qtype, text if value is None else value, (), strict=True)
        if value is not None and qtype == "bool" and (said := _plain_or_none(qtype, text)) is not None and said != out:
            raise ValueError(f"the veteran said {text.strip()!r} but value is {value!r}")
        return out
    except ValueError as err:
        raise StrictError(f"could not read {key}: {err}. {key} is a stop-rule field, so code reads only "
                          "plain answers. Pass the structured value you understood in `value` "
                          f"({_HINT[qtype.removesuffix('_append')]}) and keep the veteran's words in `a`. "
                          "If their answer is really unclear, ask again; don't mark it unknown unless "
                          "they say they don't know.") from err  # fmt: skip


def _plain_or_none(qtype: str, text: str) -> Any:
    try:
        return coerce(qtype, text, (), strict=True)
    except ValueError:
        return None
