"""The shared harness (L1, L4, L5) on dspy.ReAct, driven by the scripted fake LM."""

import time

from pydantic import BaseModel

from agent.casefile import CaseFile
from agent.harness import CANNED_REPLY, AgentSpec, Turn, conversation
from agent.scripted.lm import bad, call, final
from agent.tools.registry import ToolSpec

SSN = "123-45-6789"


class EchoArgs(BaseModel):
    text: str


def _spec(stop=None, **kw) -> AgentSpec:
    def tools(turn):
        def echo(a):
            if a.text == "slow":
                time.sleep(0.2)
            return f"echo {a.text}"

        return [ToolSpec("echo", "Echo text.", EchoArgs, echo)]

    defaults = {"name": "support", "instructions": "Test agent.", "tools": tools,
                "context": lambda t: "the context", "max_iters": 3, "timeout_s": 30, "stop": stop}  # fmt: skip
    return AgentSpec(**{**defaults, **kw})


def _turn(rt, agent="support") -> Turn:
    if not rt.store.exists("c1"):
        rt.store.create_case(CaseFile(case_id="c1"))
    return Turn(rt, "c1", agent, "hello", 1)


def test_one_turn_runs_tools_and_returns_the_reply(rt, lm):
    lm.turn("support", call("echo", text="hi"), final(reply="Done."))
    out = rt.harness.run(_spec(), _turn(rt))
    assert (out.reply, out.status, out.result) == ("Done.", "ok", None)
    traj = lm.prompts("support", "extract")[0]
    assert "echo hi" in traj and "the context" in traj


def test_the_prompt_has_the_skill_index_and_the_tools(rt, lm):
    lm.turn("support", final(reply="ok"))
    rt.harness.run(_spec(), _turn(rt))
    system = lm.seen[0].system
    assert "case-status" in system and "read_skill" in system and "echo" in system


def test_read_skill_loads_the_agents_own_skill(rt, lm):
    lm.turn("support", call("read_skill", name="case-status"), final())
    rt.harness.run(_spec(), _turn(rt))
    assert "# " in lm.prompts("support", "extract")[0].split("observation_0")[1]


def test_result_is_kept_only_for_agents_with_a_stop_rule(rt, lm):
    result = {"finished": "pass 1", "wrote": [], "needs": [], "flags": []}
    lm.turn("intake", final(reply="bye", result=result))
    out = rt.harness.run(_spec(name="intake", stop=lambda c: True), _turn(rt, "intake"))
    assert out.result.finished == "pass 1" and out.result.agent == "intake"
    lm.turn("support", final(reply="hi"))
    rt.harness.run(_spec(), _turn(rt))
    assert "result" not in lm.seen[-1].system.split("Your output fields are:")[1].split("All interactions")[0]


def test_max_iters_ends_a_chat_turn_with_the_canned_reply(rt, lm):
    lm.turn("support", call("echo", text="1"), call("echo", text="2"), call("echo", text="3"), final(reply="late"))
    out = rt.harness.run(_spec(), _turn(rt))
    assert (out.status, out.reply) == ("limit", CANNED_REPLY)
    assert [t["kind"] for t in rt.harness.traces.read("c1")][-1] == "turn_limit"


def test_timeout_stops_the_turn_at_the_next_tool_call(rt, lm):
    lm.turn("support", call("echo", text="slow"), call("echo", text="never"))
    out = rt.harness.run(_spec(timeout_s=0.1), _turn(rt))
    assert out.status == "limit" and out.detail == "timeout"
    (never,) = [t for t in rt.harness.traces.read("c1") if t.get("args") == {"text": "never"}]
    assert "TurnTimeout" in never["error"] and never["result"] == ""


def test_malformed_output_is_parsed_by_the_json_fallback(rt, lm):
    lm.turn("support", bad(), call("echo", text="x"), final(reply="fine"))
    out = rt.harness.run(_spec(), _turn(rt))
    assert (out.status, out.reply) == ("ok", "fine")
    assert not [t for t in rt.harness.traces.read("c1") if t["kind"] == "turn_error"]


def test_malformed_output_falls_back_to_json_then_retries_the_turn(rt, lm):
    # ChatAdapter fails, the JSONAdapter fallback fails too: the harness retries the turn once.
    lm.turn("support", bad(), bad(), call("echo", text="x"), final(reply="recovered"))
    out = rt.harness.run(_spec(), _turn(rt))
    assert (out.status, out.reply) == ("ok", "recovered")
    errors = [t for t in rt.harness.traces.read("c1") if t["kind"] == "turn_error"]
    assert len(errors) == 1


def test_two_failed_attempts_end_the_turn_without_another_policy(rt, lm):
    lm.turn("support", bad(), bad(), bad(), bad())
    out = rt.harness.run(_spec(), _turn(rt))
    assert (out.status, out.reply) == ("failed", CANNED_REPLY)
    lm.turn("orchestrator", bad(), bad(), bad(), bad())
    out = rt.harness.run(_spec(name="orchestrator", on_limit="needs_human"), _turn(rt, "orchestrator"))
    assert (out.status, out.reply) == ("failed", "")


def test_guard_refusals_reach_the_model_and_the_event_log(rt, lm):
    lm.turn("support", call("echo", text="no"), final())
    spec = _spec(guard=lambda turn, name, a: "not allowed" if a.text == "no" else None)
    rt.harness.run(spec, _turn(rt))
    assert "refused: not allowed" in lm.prompts("support", "extract")[0]
    (event,) = rt.store.events("c1", types=("refused",))
    assert event.actor == "support" and event.data["reason"] == "not allowed"


def test_an_owner_that_lost_the_case_is_refused(rt, lm):
    rt.store.create_case(CaseFile(case_id="c1", owner="intake"))
    turn = _turn(rt, "intake")
    turn.owner_at_start = True
    rt.store.update_case("c1", lambda c: setattr(c, "owner", None))
    lm.turn("intake", call("echo", text="x"), final())
    rt.harness.run(_spec(name="intake", stop=lambda c: False), turn)
    assert "refused: you no longer own the case" in lm.prompts("intake", "extract")[0]


def test_traces_have_one_line_per_lm_call_and_per_tool_call_with_cost(rt, lm):
    lm.turn("support", call("echo", text="a"), call("echo", text="b"), final(reply="ok"))
    rt.harness.run(_spec(max_iters=5), _turn(rt))
    lines = rt.harness.traces.read("c1")
    lms, tools = [x for x in lines if x["kind"] == "lm"], [x for x in lines if x["kind"] == "tool"]
    assert len(lms) == 4 and len(tools) == 2  # 3 ReAct steps + extract; finish isn't a tool line
    assert all(x["agent"] == "support" and x["turn"] == 1 and x["cost"] > 0 for x in lms)
    assert lms[0]["context_tokens"] > 0 and tools[0]["guard"] == "allowed"
    assert rt.harness.traces.cost_by_agent("c1")["support"] > 0


def test_ssns_never_reach_the_trace(rt, lm):
    lm.turn("support", call("echo", text=f"my ssn is {SSN}"), final(reply=f"got {SSN}"))
    rt.harness.run(_spec(), _turn(rt))
    text = rt.harness.traces.path.read_text()
    assert SSN not in text and "123456789" not in text


def test_trace_metadata_is_not_scrubbed(rt, lm):
    rt.store.create_case(CaseFile(case_id="7b320679912e"))  # a digit run that looks like an ID
    lm.turn("support", final())
    rt.harness.run(_spec(), Turn(rt, "7b320679912e", "support", "hi", 1))
    assert rt.harness.traces.read("7b320679912e")


def test_history_is_the_agents_own_last_n_messages(rt):
    turn = _turn(rt, "intake")
    for i in range(5):
        rt.store.append_event("c1", "message", {"from": "veteran", "to": "intake", "text": f"v{i}"})
        rt.store.append_event("c1", "message", {"from": "intake", "to": "veteran", "text": f"i{i}"})
    rt.store.append_event("c1", "message", {"from": "veteran", "to": "support", "text": "elsewhere"})
    lines = conversation(turn, 3).splitlines()
    assert lines[0].startswith("<untrusted ") and lines[-1] == "</untrusted>"
    assert lines[1:-1] == ["intake: i3", "veteran: v4", "intake: i4"]
