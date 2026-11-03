"""The tool registry (L2): validate, guard, run; every outcome is an observation."""

from pydantic import BaseModel, Field

from agent.tools.registry import Registry, ToolSpec


class FillArgs(BaseModel):
    form: str
    fields: dict[str, str] = Field(default_factory=dict)


def _registry(guard=None, refused=None):
    def fill(a: FillArgs):
        if a.form == "boom":
            raise RuntimeError("disk full")
        return {"filled": a.form, "n": len(a.fields)}

    return Registry([ToolSpec("fill_pdf", "Fill a form.", FillArgs, fill)], guard=guard, on_refused=refused)


def test_valid_call_runs_and_returns_json():
    assert _registry().run("fill_pdf", {"form": "21-22a"}) == '{"filled": "21-22a", "n": 0}'


def test_bad_arguments_name_the_field():
    out = _registry().run("fill_pdf", {"fields": {}})
    assert out.startswith("invalid_args: ") and "form" in out
    assert _registry().run("nope", {}).startswith("invalid_args: no tool named")


def test_guard_refusal_is_an_observation_and_logged():
    logged = []
    reg = _registry(guard=lambda name, a: "not countersigned" if a.form == "21-22a" else None,
                    refused=lambda *x: logged.append(x))  # fmt: skip
    assert reg.run("fill_pdf", {"form": "21-22a"}) == "refused: not countersigned"
    assert logged == [("fill_pdf", {"form": "21-22a", "fields": {}}, "not countersigned")]
    assert reg.run("fill_pdf", {"form": "fee"}).startswith("{")


def test_tool_errors_come_back_as_observations():
    assert _registry().run("fill_pdf", {"form": "boom"}) == "error: RuntimeError: disk full"


def test_dspy_tools_carry_the_schema_and_route_through_the_registry():
    (tool,) = _registry().dspy_tools()
    assert tool.name == "fill_pdf" and set(tool.args) == {"form", "fields"}
    assert tool(fields={}).startswith("invalid_args: ")  # our validation, not dspy's
    assert tool(form="x") == '{"filled": "x", "n": 0}'
