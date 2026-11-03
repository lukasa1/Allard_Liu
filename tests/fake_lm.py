"""A scripted fake LM that drives dspy.ReAct through the real harness, tools and adapters.

A test scripts, per agent, the turns that agent will take. Each turn is a list of steps:

    lm = ScriptedLM()
    lm.turn("orchestrator", call("run_intake", goal="screen the veteran"), final(reply="Hi!"))
    lm.turn("intake", call("record_answer", question_id="served", value="yes"), final(reply="Next?"))

`call(tool, **args)` answers one ReAct step with that tool call; `final(reply, result)` answers
the step that picks `finish` and then ReAct's extract call with the outputs; `bad(text)` answers
one call with unparseable text (to exercise the adapter fallback and the harness retry);
`pause(gate)` holds the agent's next model call until a threading.Event is set.

The agent is read from the "Agent: <name>" line the harness puts in every system prompt. A new
turn starts when a ReAct call arrives and the agent's current turn is used up, so retries of a
failed turn keep consuming the same turn's steps. Tests never touch a real model or the network.
"""

from __future__ import annotations

import copy
import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from dspy.clients.engines.dummy_engine import AsyncDummyEngine, DummyEngine
from dspy.lm15 import Message, Response, TextPart, Usage
from dspy.utils.dummies import DummyLM


@dataclass(frozen=True)
class Call:
    tool: str
    args: dict[str, Any]
    thought: str = ""


@dataclass(frozen=True)
class Final:
    reply: str = ""
    result: dict[str, Any] | None = None


@dataclass(frozen=True)
class Raw:
    text: str


@dataclass(frozen=True)
class Pause:
    gate: Any  # a threading.Event the test sets to let the turn go on


def call(tool: str, **args: Any) -> Call:
    return Call(tool, args, thought=f"call {tool}")


def final(reply: str = "", result: dict[str, Any] | None = None) -> Final:
    return Final(reply, result)


def bad(text: str = "I am not following the output format.") -> Raw:
    return Raw(text)


def pause(gate) -> Pause:
    """Block this agent's next model call until `gate` is set (to hold a background turn)."""
    return Pause(gate)


@dataclass
class Seen:
    agent: str
    kind: str  # react | extract
    system: str
    user: str


@dataclass
class _Turn:
    steps: deque = field(default_factory=deque)


class _Engine(DummyEngine):
    def _complete_messages(self, messages):
        text = self.owner.respond(messages)
        tokens_in = sum(len(m.get("content") or "") for m in messages) // 4
        return Response(id=None, model="scripted", message=Message.assistant([TextPart(text)]), finish_reason="stop",
                        usage=Usage(input_tokens=tokens_in, output_tokens=len(text) // 4,
                                    total_tokens=tokens_in + len(text) // 4))  # fmt: skip


class ScriptedLM(DummyLM):
    def __init__(self, model: str = "openrouter/anthropic/claude-haiku-5.5") -> None:
        super().__init__([])
        self.model = model
        self._engine_spec = _Engine(self)
        self._async_engine_spec = AsyncDummyEngine(self._engine_spec)
        self.turns: dict[str, deque[_Turn]] = {}
        self.current: dict[str, _Turn] = {}
        self.seen: list[Seen] = []

    def copy(self, **kwargs):
        clone = copy.copy(self)  # shares the script; its own history, as dspy.LM.copy does
        clone.history = []
        return clone

    # ------------------------------------------------------------------ scripting

    def turn(self, agent: str, *steps: Call | Final | Raw | Pause) -> ScriptedLM:
        self.turns.setdefault(agent, deque()).append(_Turn(deque(steps)))
        return self

    def unused(self) -> dict[str, int]:
        """Scripted steps not consumed yet, per agent (should be {} at the end of a test)."""
        out = {a: sum(len(t.steps) for t in ts) for a, ts in self.turns.items()}
        out = {a: n + len(self.current[a].steps) if a in self.current else n for a, n in out.items()}
        return {a: n for a, n in out.items() if n}

    def prompts(self, agent: str, kind: str = "react") -> list[str]:
        return [s.user for s in self.seen if s.agent == agent and s.kind == kind]

    # ------------------------------------------------------------------ answering

    def respond(self, messages: list[dict]) -> str:
        system, user = messages[0]["content"], messages[-1]["content"]
        agent = re.search(r"Agent: (\w+)", system).group(1)
        outputs = re.findall(r"`(\w+)`", system.split("Your output fields are:")[1].split("All interactions")[0])
        kind = "react" if "next_tool_name" in outputs else "extract"
        self.seen.append(Seen(agent, kind, system, user))
        turn = self.current.get(agent)
        if kind == "react" and (turn is None or not turn.steps):
            queue = self.turns.get(agent)
            if not queue:
                raise AssertionError(f"no scripted turn left for {agent}; incoming:\n{user[-600:]}")
            turn = self.current[agent] = queue.popleft()
        if turn is None or not turn.steps:
            raise AssertionError(f"{agent}'s scripted turn is used up ({kind} call)")
        step = turn.steps[0]
        if isinstance(step, Pause):
            turn.steps.popleft()
            if not step.gate.wait(10):
                raise AssertionError(f"{agent}: pause gate never opened")
            step = turn.steps[0]
        if isinstance(step, Raw):
            turn.steps.popleft()
            return step.text
        if kind == "react":
            if isinstance(step, Final):
                answer = {"next_thought": "done", "next_tool_name": "finish", "next_tool_args": {}}
            else:
                turn.steps.popleft()
                answer = {"next_thought": step.thought, "next_tool_name": step.tool, "next_tool_args": step.args}
        else:
            if not isinstance(step, Final):
                raise AssertionError(f"{agent}: extract call, but the next scripted step is {step}")
            turn.steps.popleft()
            answer = {"reasoning": "per the script", "reply": step.reply}
            if "result" in outputs:
                answer["result"] = step.result
        if "[[ ## completed ## ]]" not in system:  # the JSONAdapter fallback asks for JSON
            return json.dumps(answer)
        return self._format_answer_fields(answer)

