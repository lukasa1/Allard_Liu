"""Intake's memory in code (L15, L16, L18, A1): the typed checklist, answer parsing, stop rules.

The checklist is rebuilt from the case file's answers on every turn and after every answer:

  screen  pass 1: the `screen` questions of questions.yaml whose visibility holds, except the
          ones the secure form collects (they are the 21-22a's job in stage 2)
  pass2   pass 2: every visible question of the firm's form not yet settled (pass-1 questions
          that became relevant included, secure-form ones too), one `confirm:<question>` per open
          C-file conflict, then the narrative prompts for each claimed condition

In the eval condition `ask_no_probes` the verification probes are left out (casefile.EvalCondition).
A field is settled when it has an answer or is marked unknown. Answers are keyed by question id;
narratives by `narrative:<condition>:<prompt id>`. The firm's stop rules run on the same record.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agent.casefile import CaseFile, StopRule
from agent.intake import rules
from agent.intake.parsing import coerce
from agent.intake.questions import QuestionBank, is_visible
from agent.intake.schema import NON_HONORABLE, IntakeRecord

BANK = QuestionBank.load()
# Not asked as questions: C-file conflicts are `confirm:` items, and a new condition is added by
# recording the full claim_conditions list again.
SKIP = {"cfile_discrepancy_check", "add_condition"}
FREE_TEXT = ("str", "narrative")
# Secure-form questions -> the vault field that answers them.
VAULT_FIELD = {
    "first_name": "first_name", "last_name": "last_name", "street": "address.line1",
    "city": "address.city", "state": "address.state", "zip": "address.zip",
    "cell_phone": "phone", "email": "email",
}  # fmt: skip


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
        return _questions(case, "screen")
    return _questions(case, "pass2") + _conflicts(case) + _narratives(case)


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
        case.stop = stop_rule(record(case))


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


def parse(key: str, text: str) -> Any:
    """Parse an answer in code (L16): simple fields (yes/no, dates, branch, discharge, lists) are
    read by parsing.coerce; free text is kept as given. Raises ValueError when it can't be read."""
    qtype, options = question_type(key)
    value = coerce(qtype, text, options)
    return [v.model_dump() if isinstance(v, BaseModel) else v for v in value] if isinstance(value, list) else value
