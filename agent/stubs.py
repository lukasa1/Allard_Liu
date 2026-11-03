"""TEMPORARY stand-in for support (build step 2; intake and claims prep are real since steps 3-4).

It has the real interface (an AgentSpec run by the harness, one ReAct turn per message) and just
enough tools to move the case file the way the real agent will, so the orchestrator, the stage
table and the runtime can be tested end to end with the scripted fake LM. Step 5 replaces it.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from agent.harness import AgentSpec, Turn, conversation
from agent.tools.registry import ToolSpec


def _memory(turn: Turn, history: int) -> str:
    case = turn.case
    return (
        f"## Case file\n{json.dumps(case.memory(), indent=1)}\n\n"
        f"## Goal\n{case.goal}\n\n## Last {history} messages\n{conversation(turn, history)}"
    )


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
