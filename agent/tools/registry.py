"""Tool registry and guard hook (L2).

A tool is a name, a description, a Pydantic argument schema and its code. Every call goes:
validate the arguments (`invalid_args: <field>: <why>` on failure) -> guard hook (`refused:
<reason>` on refusal, logged through `on_refused`) -> run. Whatever happens comes back to the
model as a string observation, so it can correct itself (L4). Tool code that raises returns
`error: ...` the same way.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import dspy
from dspy.adapters.types.tool import _resolve_json_schema_reference
from pydantic import BaseModel, ValidationError

Guard = Callable[[str, BaseModel], str | None]  # (tool name, validated args) -> refusal reason


class NoArgs(BaseModel):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[BaseModel], Any]


class _RegistryTool(dspy.Tool):
    """A dspy.Tool whose arguments the registry validates (not dspy's own JSON-schema check)."""

    def _validate_and_parse_args(self, **kwargs):
        return kwargs


def _invalid(err: ValidationError) -> str:
    parts = [f"{'.'.join(str(x) for x in e['loc']) or '(args)'}: {e['msg']}" for e in err.errors()]
    return "invalid_args: " + "; ".join(parts)


def _observation(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value, default=str)


class Registry:
    def __init__(self, tools: list[ToolSpec], guard: Guard | None = None,
                 on_refused: Callable[[str, dict, str], None] | None = None) -> None:  # fmt: skip
        self.tools = {t.name: t for t in tools}
        self.guard = guard
        self.on_refused = on_refused

    def run(self, name: str, raw: dict[str, Any]) -> str:
        spec = self.tools.get(name)
        if spec is None:
            return f"invalid_args: no tool named {name!r}"
        try:
            args = spec.args.model_validate(raw)
        except ValidationError as err:
            return _invalid(err)
        if self.guard and (reason := self.guard(name, args)):
            if self.on_refused:
                self.on_refused(name, args.model_dump(mode="json"), reason)
            return f"refused: {reason}"
        try:
            return _observation(spec.fn(args))
        except Exception as err:  # noqa: BLE001 - tool errors are observations, not crashes (L4)
            return f"error: {type(err).__name__}: {err}"

    def dspy_tools(self) -> list[dspy.Tool]:
        out = []
        for spec in self.tools.values():
            args = _resolve_json_schema_reference(spec.args.model_json_schema()).get("properties", {})
            out.append(_RegistryTool(self._bound(spec.name), name=spec.name, desc=spec.description,
                                     args=args, arg_types={}))  # fmt: skip
        return out

    def _bound(self, name: str) -> Callable[..., str]:
        def call(**kwargs: Any) -> str:
            return self.run(name, kwargs)

        return call
