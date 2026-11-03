"""TEMPORARY stand-ins for claims prep and support (build step 2; intake is real since step 3).

They have the real interface (an AgentSpec run by the harness, one ReAct turn per message or
event) and just enough tools to move the case file the way the real agents will, so the
orchestrator, the stage table and the runtime can be tested end to end with the scripted fake
LM. Steps 4-5 replace each with the real agent.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from agent.casefile import CaseFile
from agent.harness import AgentSpec, Turn, conversation
from agent.tools.registry import ToolSpec


def _memory(turn: Turn, history: int) -> str:
    case = turn.case
    return (
        f"## Case file\n{json.dumps(case.memory(), indent=1)}\n\n"
        f"## Goal\n{case.goal}\n\n## Last {history} messages\n{conversation(turn, history)}"
    )


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
    return {"claims_prep": prep_spec(), "support": support_spec()}
