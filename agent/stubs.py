"""TEMPORARY stand-ins for intake, claims prep and support (build step 2).

They have the real interface (an AgentSpec run by the harness, one ReAct turn per message or
event) and just enough tools to move the case file the way the real agents will, so the
orchestrator, the stage table and the runtime can be tested end to end with the scripted fake
LM. Steps 3a-5 replace each with the real agent.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from agent.casefile import Answer, CaseFile, Filing, StopRule
from agent.harness import AgentSpec, Turn, conversation
from agent.tools.registry import NoArgs, ToolSpec

CHECKLIST = {"screen": ("served", "discharge", "rating"), "pass2": ("conditions",)}


def _memory(turn: Turn, history: int) -> str:
    case = turn.case
    return (
        f"## Case file\n{json.dumps(case.memory(), indent=1)}\n\n"
        f"## Goal\n{case.goal}\n\n## Last {history} messages\n{conversation(turn, history)}"
    )


# ------------------------------------------------------------------------------ intake


class AnswerArgs(BaseModel):
    question_id: str
    value: str


class SubmitArgs(BaseModel):
    form: Literal["21-22a", "itf"]


class StopArgs(BaseModel):
    rule: str
    reason: str


def _record(turn: Turn, a: AnswerArgs) -> str:
    def apply(case: CaseFile) -> None:
        case.answers[a.question_id] = Answer(value=a.value, source="veteran, chat")
        for part, fields in CHECKLIST.items():
            case.checklist[part] = [q for q in fields if q not in case.answers]

    case = turn.rt.patch(turn.case_id, apply, actor="intake")
    return f"recorded; stage {case.stage}; missing {case.checklist}"


def _submit(turn: Turn, a: SubmitArgs) -> str:
    conf = f"VA-{uuid.uuid4().hex[:8].upper()}"
    case = turn.rt.patch(turn.case_id, lambda c: c.filings.__setitem__(a.form, Filing(confirmation=conf)), "intake")
    return f"filed {a.form}: {conf}; stage {case.stage}"


def _efax(turn: Turn) -> str:
    conf = f"FAX-{uuid.uuid4().hex[:8].upper()}"
    turn.rt.patch(turn.case_id, lambda c: c.filings.__setitem__("fee_agreement", Filing(confirmation=conf)), "intake")
    return f"faxed the fee agreement to OGC: {conf}"


def _stop(turn: Turn, a: StopArgs) -> str:
    case = turn.rt.patch(turn.case_id, lambda c: setattr(c, "stop", StopRule(rule=a.rule, reason=a.reason)), "intake")
    return f"stop rule recorded; the case is {case.side_state}"


def _intake_guard(turn: Turn, name: str, args: BaseModel) -> str | None:
    case = turn.case
    if name == "submit_va" and not (case.documents.get("21-22a") and case.documents["21-22a"].countersigned_at):
        return "the 21-22a must be countersigned by the attorney first"
    if name == "efax_ogc":
        doc = case.documents.get("fee_agreement")
        if not (doc and doc.signed_at and doc.countersigned_at):
            return "the fee agreement must be signed and countersigned first"
    return None


def intake_spec() -> AgentSpec:
    def tools(turn: Turn) -> list[ToolSpec]:
        return [
            ToolSpec("record_answer", "Save the veteran's answer.", AnswerArgs, lambda a: _record(turn, a)),
            ToolSpec("submit_va", "File the 21-22a or the intent to file (simulated).", SubmitArgs,
                     lambda a: _submit(turn, a)),
            ToolSpec("efax_ogc", "Fax the fee agreement to VA OGC (simulated).", NoArgs, lambda a: _efax(turn)),
            ToolSpec("fire_stop_rule", "Record a firm stop rule.", StopArgs, lambda a: _stop(turn, a)),
        ]  # fmt: skip

    return AgentSpec(
        name="intake", instructions="You are intake (a stub).", tools=tools,
        context=lambda t: _memory(t, 12), guard=_intake_guard,
        stop=lambda c: c.stage in (3, 5) or c.parked, max_iters=8, timeout_s=120,
    )  # fmt: skip


# ------------------------------------------------------------------------------ claims prep


class PrepArgs(BaseModel):
    uncertain: list[str] = Field(default_factory=list)


def _finish_prep(turn: Turn, a: PrepArgs) -> str:
    def apply(case: CaseFile) -> None:
        case.prep.face_note = "(stub face note)"
        case.prep.verified = not a.uncertain
        case.prep.uncertain = a.uncertain
        case.prep.prefill_done = True

    turn.rt.patch(turn.case_id, apply, actor="claims_prep")
    return "face note rendered, verified, prefill done"


def prep_spec() -> AgentSpec:
    return AgentSpec(
        name="claims_prep", instructions="You are claims prep (a stub).",
        tools=lambda t: [ToolSpec("finish_prep", "Write the face note.", PrepArgs, lambda a: _finish_prep(t, a))],
        context=lambda t: json.dumps(t.case.memory()), stop=lambda c: c.prep.done or c.parked,
        max_iters=40, timeout_s=600, on_limit="continue",
    )  # fmt: skip


# ------------------------------------------------------------------------------ support


class FlagArgs(BaseModel):
    kind: str
    text: str


class EscalateArgs(BaseModel):
    reason: str


def support_spec() -> AgentSpec:
    def tools(turn: Turn) -> list[ToolSpec]:
        return [
            ToolSpec("flag_orchestrator", "Pass something that would change the case to the orchestrator.",
                     FlagArgs, lambda a: turn.rt.flag(turn.case_id, a.kind, a.text, turn)),
            ToolSpec("escalate", "Hand the conversation to a staff member.", EscalateArgs,
                     lambda a: _escalate(turn, a)),
        ]  # fmt: skip

    return AgentSpec(
        name="support", instructions="You are customer support (a stub).", tools=tools,
        context=lambda t: _memory(t, 8), stop=lambda c: True, max_iters=5, timeout_s=60,
    )  # fmt: skip


def _escalate(turn: Turn, a: EscalateArgs) -> str:
    event = turn.rt.escalate(turn.case_id, a.reason, actor="support")
    turn.deferred.append(turn.rt.wake_job(event))
    return "handed to staff"


def specs() -> dict[str, AgentSpec]:
    return {"intake": intake_spec(), "claims_prep": prep_spec(), "support": support_spec()}
