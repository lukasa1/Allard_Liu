"""Trace log (L5): one JSON line per model call and per tool call, written by DSPy callbacks.

Each line carries the case, agent and turn (from a context variable the harness sets around a
turn), the latency, the token counts and cost (from config.PRICES), and for tools the arguments,
the guard's decision and the result. kb_search's own model call is an `lm` line of the agent
that searched (agent/kb.py). Lines pass through SSN, ID-number and date-of-birth redaction
before they are written.
"""

from __future__ import annotations

import contextvars
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dspy.utils.callback import BaseCallback

from agent.casefile import now
from agent.cfile.extract import strip_ssns
from agent.config import PRICES
from agent.ingest import redact_chat


@dataclass(frozen=True)
class TurnInfo:
    case_id: str
    agent: str
    turn: int


CURRENT: contextvars.ContextVar[TurnInfo | None] = contextvars.ContextVar("trace_turn", default=None)


def scrub(value: Any) -> Any:
    """Hide SSNs, ID numbers and a typed date of birth in every string inside `value` (numbers
    stay numbers)."""
    if isinstance(value, str):
        return redact_chat(strip_ssns(value))[0]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return scrub(str(value))


def cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    rates = PRICES.get(model)
    if rates is None:
        return None
    return round((input_tokens * rates[0] + output_tokens * rates[1]) / 1e6, 8)


def guard_decision(observation: str) -> str:
    if observation.startswith("refused:"):
        return "refused"
    if observation.startswith("invalid_args:"):
        return "invalid_args"
    return "allowed"


class TraceLog:
    """Append-only JSON lines in one file, readable per case."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, kind: str, **fields: Any) -> None:
        info = CURRENT.get()
        # Only the content is scrubbed: a case id may contain a digit run that looks like an ID.
        line = {"at": now(), "kind": kind, **(info.__dict__ if info else {}), **scrub(fields)}
        text = json.dumps(line)
        with self._lock, self.path.open("a") as f:
            f.write(text + "\n")

    def read(self, case_id: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        lines = [json.loads(x) for x in self.path.read_text().splitlines() if x]
        return [x for x in lines if case_id is None or x.get("case_id") == case_id]

    def cost_by_agent(self, case_id: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for x in self.read(case_id):
            if x["kind"] == "lm" and x.get("cost") is not None:
                out[x["agent"]] = round(out.get(x["agent"], 0.0) + x["cost"], 8)
        return out


class TraceCallback(BaseCallback):
    """DSPy callback: an `lm` line per model call, a `tool` line per tool call."""

    def __init__(self, log: TraceLog) -> None:
        self.log = log
        self._lms: dict[str, tuple[Any, float]] = {}
        self._tools: dict[str, tuple[str, dict, float]] = {}

    def on_lm_start(self, call_id, instance, inputs):
        self._lms[call_id] = (instance, time.monotonic())

    def on_lm_end(self, call_id, outputs, exception):
        lm, started = self._lms.pop(call_id, (None, time.monotonic()))
        # Each turn runs on its own copy of the LM, so the last history entry is this call.
        entry = lm.history[-1] if lm is not None and lm.history else {}
        usage = entry.get("usage") or {}
        tokens_in, tokens_out = usage.get("prompt_tokens", 0) or 0, usage.get("completion_tokens", 0) or 0
        model = getattr(lm, "model", "")
        self.log.write(
            "lm", model=model, context_tokens=tokens_in, output_tokens=tokens_out,
            cost=cost(model, tokens_in, tokens_out), latency_s=round(time.monotonic() - started, 3), output=outputs,
            error=repr(exception) if exception else None,
        )  # fmt: skip

    def on_tool_start(self, call_id, instance, inputs):
        self._tools[call_id] = (instance.name, inputs.get("kwargs", {}), time.monotonic())

    def on_tool_end(self, call_id, outputs, exception):
        name, args, started = self._tools.pop(call_id, ("?", {}, time.monotonic()))
        if name == "finish":
            return
        result = "" if outputs is None else str(outputs)
        self.log.write(
            "tool", tool=name, args=args, guard=guard_decision(result), result=result,
            latency_s=round(time.monotonic() - started, 3), error=repr(exception) if exception else None,
        )  # fmt: skip
