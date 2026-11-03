"""The orchestrator agent (L10-L13): owns the case end to end, answers no questions itself.

It wakes on case_opened, subagent_result, support_flag, escalated and staff events nobody owns
(agent/runtime.py). Each wake rebuilds its context from scratch: the skill index, the memory
block (the case file and the last 10 events verbatim, never a transcript or the C-file) and the
waking event. It makes at most one handoff per wake; the sub-agent's first turn runs after the
wake ends (D9).

Tools: read_skill (from the harness), run_intake(goal), run_prep(goal), move_stage(to, reason)
for moves back, needs_human and closed (D11), and staff_task(text) for a flag that goes to a
person (L12). Its `reply` is the short update to the veteran at a handoff.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from agent import stages
from agent.casefile import CaseFile, Task
from agent.harness import AgentSpec, Turn
from agent.runtime import CHAT_EVENT_TYPES, Job
from agent.tools.registry import ToolSpec

MEMORY_EVENTS = 10
INSTRUCTIONS = """You are the orchestrator for one veteran's case at a law firm that represents \
veterans before VA. You keep the case moving between the sub-agents; you never answer the veteran's \
questions (intake or support do). Each wake: read the waking event and the memory block, decide, and \
act with at most ONE handoff (run_intake or run_prep). Code moves the stage forward when the exit \
criteria hold; your guard refuses anything else, and a refusal tells you why. For a support flag, read \
the `flags` skill and decide: reopen intake, or a staff task. When you hand off, you may send the \
veteran one short update in `reply`; otherwise leave `reply` empty."""


class GoalArgs(BaseModel):
    goal: str = Field(min_length=3, description="what the sub-agent should get done, in one or two sentences")


class MoveArgs(BaseModel):
    to: Literal["1", "2", "3", "4", "5", "needs_human", "closed"] = Field(
        description="an earlier stage number, or needs_human / closed"
    )
    reason: str = Field(min_length=3)


class TaskArgs(BaseModel):
    text: str = Field(min_length=3, description="what the staff member must do")


def _handoff(turn: Turn, agent: str, goal: str) -> str:
    rt, refusal = turn.rt, []

    def apply(case: CaseFile) -> list[dict]:
        # Re-checked under the case's lock: the guard ran on a snapshot.
        if reason := stages.check_handoff(case, agent, rt.running(turn.case_id) - {"orchestrator"}):
            refusal.append(reason)
            return [{"type": "refused", "data": {"tool": f"run_{_short(agent)}", "reason": reason}}]
        events = []
        if agent == "claims_prep":
            events.append(stages.move(case, 4, "handoff", goal))
            case.prep.continuations = 0
        case.owner, case.goal, case.awaiting_veteran = agent, goal, False
        return events + [{"type": "handoff", "data": {"to": agent, "goal": goal}}]

    rt.patch(turn.case_id, apply, actor="orchestrator")
    if refusal:
        return f"refused: {refusal[0]}"
    turn.handoff = agent
    turn.deferred.append(Job(agent, f"[handoff] Goal: {goal}", "start"))
    return f"Handed the case to {agent}; its first turn runs after this wake. Finish now."


def _short(agent: str) -> str:
    return "prep" if agent == "claims_prep" else agent


def _move(turn: Turn, args: MoveArgs) -> str:
    to: int | str = int(args.to) if args.to.isdigit() else args.to
    event = turn.rt.move(turn.case_id, to, "orchestrator", args.reason)
    if event["type"] == "refused":
        return f"refused: {event['data']['reason']}"
    return f"moved: {json.dumps(event['data'])}"


def _staff_task(turn: Turn, args: TaskArgs) -> str:
    turn.rt.patch(turn.case_id, lambda c: c.tasks.append(Task(kind="staff", text=args.text)), actor="orchestrator")
    turn.rt.store.append_event(turn.case_id, "task_created", {"text": args.text}, actor="orchestrator")
    return "staff task created"


def tools(turn: Turn) -> list[ToolSpec]:
    return [
        ToolSpec("run_intake", "Hand the case to intake (pass 1 at stage 1; pass 2 at stage 4 once claims "
                 "prep has returned) with a goal. One handoff per wake.", GoalArgs,
                 lambda a: _handoff(turn, "intake", a.goal)),
        ToolSpec("run_prep", "Hand the case to claims prep at stage 3 (21-22a and ITF filed): pull and read "
                 "the C-file, prefill, write the face note. One handoff per wake.", GoalArgs,
                 lambda a: _handoff(turn, "claims_prep", a.goal)),
        ToolSpec("move_stage", "Move the case back to an earlier stage, or to needs_human or closed, with a "
                 "reason. Forward moves happen in code.", MoveArgs, lambda a: _move(turn, a)),
        ToolSpec("staff_task", "Create a task for a staff member (for example a flag a person should "
                 "decide). Does not change the stage.", TaskArgs, lambda a: _staff_task(turn, a)),
    ]  # fmt: skip


def guard(turn: Turn, name: str, args: BaseModel) -> str | None:
    if turn.handoff:
        return f"this wake already handed the case to {turn.handoff}; finish now"
    case = turn.case
    if name in ("run_intake", "run_prep"):
        agent = "intake" if name == "run_intake" else "claims_prep"
        return stages.check_handoff(case, agent, turn.rt.running(turn.case_id) - {"orchestrator"})
    if name == "move_stage":
        to = int(args.to) if args.to.isdigit() else args.to
        if isinstance(to, int):
            if to >= case.stage:
                return "move_stage only moves back; forward moves happen in code or by a handoff"
            return stages.check_stage(case, to, "orchestrator", args.reason)
        return stages.check_side(case, to, "orchestrator", args.reason)
    return None


def context(turn: Turn) -> str:
    case = turn.case
    events = turn.rt.store.events(turn.case_id, exclude=CHAT_EVENT_TYPES, last=MEMORY_EVENTS)
    open_flags = [case.flags[i].model_dump() for i in case.flags_to_decide()]
    return (
        f"## Case file\n{json.dumps(case.memory(), indent=1)}\n\n"
        f"## Flags to decide this wake\n{json.dumps(open_flags) if open_flags else 'none'}\n\n"
        f"## Last {MEMORY_EVENTS} events (oldest first)\n" + "\n".join(e.line() for e in events)
    )


def spec() -> AgentSpec:
    return AgentSpec(
        name="orchestrator", instructions=INSTRUCTIONS, tools=tools, context=context, guard=guard,
        max_iters=6, timeout_s=90, on_limit="needs_human",
    )  # fmt: skip
