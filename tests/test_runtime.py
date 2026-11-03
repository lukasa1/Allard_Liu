"""The runtime protocol (agent/runtime.py): routing and queued jobs, the rules that hand a case to a
person before any model (crisis, a person, withdraw), and turns that fail or crash."""

import dataclasses
import threading

import pytest
from helpers import FILED, PREP_DONE, events, incoming, messages, opened, until

from agent import stages
from agent.casefile import CaseFile
from agent.harness import CANNED_REPLY
from agent.ingest import CRISIS_MESSAGE, HANDOFF_MESSAGE, WITHDRAW_MESSAGE
from agent.runtime import Job, route
from agent.scripted.lm import bad, call, final, pause


def _boom(turn):
    raise RuntimeError("tools broke")


# ------------------------------------------------------------------------------ routing and queued jobs


def test_messages_route_to_the_owner_or_support():
    assert route(CaseFile(case_id="c", owner="intake", side_state="waiting_on_attorney")) == "intake"
    assert route(CaseFile(case_id="c", owner="claims_prep")) == "support"
    assert route(CaseFile(case_id="c")) == "support"
    parked = CaseFile(case_id="c", owner="intake")
    stages.move(parked, "needs_human", "rule", "crisis")  # parking clears the owner
    assert route(parked) == "support"


def test_a_handoff_runs_the_sub_agents_first_turn_after_the_wake(rt, lm):
    opened(rt, lm)
    agents = [s.agent for s in lm.seen]
    first_intake = agents.index("intake")
    assert set(agents[:first_intake]) == {"orchestrator"} and "orchestrator" not in agents[first_intake:]


def test_a_message_queued_while_the_owner_hands_back_goes_to_support(rt, lm):
    cid = opened(rt, lm)
    gate = threading.Event()
    lm.turn("intake", pause(gate), call("record_answer", q="is_veteran", a="false"), final(reply="We can't take it."))
    lm.turn("support", final(reply="A person on the team will follow up."))
    lm.turn("orchestrator", final())
    rt.message(cid, "I never served, I'm asking for my dad.")
    until(lambda: len(lm.prompts("intake")) == 2)
    rt.message(cid, "Is there anything else I can do?")  # queued for intake, which then hands back
    gate.set()
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("support", "A person on the team will follow up.")
    assert "Is there anything else" in incoming(lm.prompts("support")[0])
    assert not events(rt, cid, "turn_skipped")
    (logged,) = [e for e in events(rt, cid, "message") if "Is there anything else" in e.data["text"]]  # logged once
    assert (logged.data["rerouted_from"], logged.data["to"]) == ("intake", "support")


def test_a_message_before_the_case_opened_wake_ends_goes_to_intake(rt, lm):
    gate = threading.Event()
    lm.turn("orchestrator", pause(gate), call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Did you serve in the military?"))
    lm.turn("intake", final(reply="Thanks, which branch?"))
    cid = rt.open_case().case_id
    until(lambda: lm.prompts("orchestrator"))
    rt.message(cid, "Hi, I served in the Army.")  # nobody owns the case yet
    gate.set()
    rt.wait_until_idle()
    assert not lm.prompts("support")
    first, second = lm.prompts("intake")[0], lm.prompts("intake")[-1]
    assert "[handoff]" in incoming(first) and "I served in the Army" in incoming(second)  # its first turn first
    assert [a for a, _ in messages(rt, cid)] == ["orchestrator", "intake", "intake"]


def test_an_event_queued_for_intake_after_it_handed_back_wakes_the_orchestrator(rt, lm):
    cid = opened(rt, lm)
    gate = threading.Event()
    lm.turn("intake", pause(gate), call("record_answer", q="is_veteran", a="false"), final(reply="We can't take it."))
    lm.turn("orchestrator", final())
    lm.turn("orchestrator", final())
    rt.message(cid, "I never served.")
    until(lambda: len(lm.prompts("intake")) == 2)
    rt.event(cid, "staff_note", {"note": "called the veteran"}, actor="staff")
    gate.set()
    rt.wait_until_idle()
    assert any("staff_note" in incoming(p) for p in lm.prompts("orchestrator"))
    assert not events(rt, cid, "turn_skipped")


def test_an_event_queued_for_the_orchestrator_goes_to_intake_once_intake_owns_the_case(rt, lm):
    gate = threading.Event()
    lm.turn("orchestrator", pause(gate), call("run_intake", goal="Pass 1."), final())
    lm.turn("intake", final(reply="Did you serve?"))
    lm.turn("intake", final())
    cid = rt.open_case().case_id
    until(lambda: lm.prompts("orchestrator"))
    rt.event(cid, "staff_note", {}, actor="staff")  # nobody owns the case yet
    assert rt.busy(cid)
    gate.set()
    rt.wait_until_idle()
    assert not rt.busy(cid)
    assert not any("staff_note" in incoming(p) for p in lm.prompts("orchestrator"))
    assert "[event]" in incoming(lm.prompts("intake")[-1]) and "staff_note" in incoming(lm.prompts("intake")[-1])


# ------------------------------------------------------------------------------ to a person, by rule


def test_crisis_language_is_handled_in_code_before_any_model(rt, lm):
    cid = opened(rt, lm)
    intake_calls = len(lm.prompts("intake"))
    lm.turn("orchestrator", final())
    rt.message(cid, "Honestly I just want to kill myself.")
    rt.wait_until_idle()
    assert len(lm.prompts("intake")) == intake_calls
    assert messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE) and "988" in CRISIS_MESSAGE
    case = rt.store.get_case(cid)
    assert (case.side_state, case.owner, case.tasks[0].kind) == ("needs_human", None, "urgent")
    assert "escalated" in incoming(lm.prompts("orchestrator")[-1])


def test_crisis_language_on_a_case_routed_to_support_never_reaches_the_model(rt, lm):
    """Stage 5, no owner: the message would go to support; the crisis check runs first."""
    cid = rt.store.create_case(CaseFile(case_id="c5", stage=5, prep=PREP_DONE, filings=FILED)).case_id
    lm.turn("orchestrator", final())
    rt.message(cid, "I don't want to be here anymore.")
    rt.wait_until_idle()
    assert lm.prompts("support") == [] and messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE)
    assert rt.store.get_case(cid).side_state == "needs_human"


def test_a_message_queued_before_a_crisis_gets_no_model_reply(rt, lm):
    cid = opened(rt, lm)
    gate = threading.Event()
    lm.turn("intake", pause(gate), final(reply="Which branch?"))
    lm.turn("support", final(reply="It takes a few months."))
    lm.turn("orchestrator", final(reply="We are on it."))  # escalated: the case is parked by rule
    lm.turn("orchestrator", final())
    rt.message(cid, "Yes I served.")
    until(lambda: len(lm.prompts("intake")) == 2)
    rt.message(cid, "How long does this take?")
    rt.message(cid, "Honestly I just want to kill myself.")
    gate.set()
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE)
    assert ("intake", "Which branch?") not in messages(rt, cid)
    held = {e.data["agent"]: e.data["reason"] for e in events(rt, cid, "reply_held")}
    assert set(held) == {"intake", "support", "orchestrator"} and "by rule" in held["intake"]
    case = rt.store.get_case(cid)
    assert (case.side_state, case.owner) == ("needs_human", None)


def test_a_request_for_a_person_or_to_withdraw_goes_to_a_person_by_rule(rt, lm):
    cid = opened(rt, lm)
    lm.turn("orchestrator", final())
    rt.message(cid, "Can I talk to a real person?")
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("rule", HANDOFF_MESSAGE)
    assert rt.store.get_case(cid).side_state == "needs_human"
    lm.turn("orchestrator", final())
    rt.message(cid, "I want to cancel my representation.")  # parked: still a person, by rule
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("rule", WITHDRAW_MESSAGE)
    assert len(rt.store.get_case(cid).tasks) == 2 and not lm.prompts("support")

    owned = rt.store.create_case(CaseFile(case_id="c1", owner="intake")).case_id
    lm.turn("orchestrator", final())
    rt.message(owned, "I want to cancel my representation.")
    rt.wait_until_idle()
    assert messages(rt, owned)[-1] == ("rule", WITHDRAW_MESSAGE)


# ------------------------------------------------------------------------------ failed and crashed turns


def test_a_failed_orchestrator_wake_puts_the_case_with_a_person(rt, lm):
    lm.turn("orchestrator", bad(), bad(), bad(), bad())
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert case.side_state == "needs_human" and "failed" in case.side_reason


def test_a_failed_intake_turn_sends_the_canned_reply(rt, lm):
    cid = opened(rt, lm)
    lm.turn("intake", bad(), bad(), bad(), bad())
    rt.message(cid, "Army.")
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("intake", CANNED_REPLY)


def test_a_crashed_turn_puts_the_case_with_a_person_and_errors_stay_per_case(rt, lm):
    rt.agents["intake"] = dataclasses.replace(rt.agents["intake"], tools=_boom)
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final())
    other = rt.store.create_case(CaseFile(case_id="other")).case_id
    cid = rt.open_case().case_id
    rt.wait_until_idle(other)  # another case's crash isn't this case's
    with pytest.raises(RuntimeError, match="crashed"):
        rt.wait_until_idle(cid)
    case = rt.store.get_case(cid)
    assert case.side_state == "needs_human" and "crashed" in case.side_reason


def test_a_support_crash_replies_canned_and_does_not_park_the_case(rt):
    rt.agents["support"] = dataclasses.replace(rt.agents["support"], tools=_boom)
    cid = rt.store.create_case(CaseFile(case_id="c", stage=3, filings=FILED)).case_id
    rt.message(cid, "When will I hear back?")
    try:
        rt.wait_until_idle(cid)
    except RuntimeError:
        pass
    case = rt.store.get_case(cid)
    assert not case.parked and case.tasks and messages(rt, cid)[-1] == ("support", CANNED_REPLY)


def test_a_support_crash_after_a_crisis_holds_the_canned_reply(rt, lm):
    gate = threading.Event()

    def boom(turn):
        gate.wait(5)
        raise RuntimeError("tools broke")

    rt.agents["support"] = dataclasses.replace(rt.agents["support"], tools=boom)
    cid = rt.store.create_case(CaseFile(case_id="c", stage=3, filings=FILED)).case_id
    lm.turn("orchestrator", final())  # the crisis's escalated wake
    rt.message(cid, "When will I hear back?")
    until(lambda: "support" in rt.running(cid))
    rt.message(cid, "I want to kill myself")
    gate.set()
    try:
        rt.wait_until_idle(cid)
    except RuntimeError:
        pass
    assert messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE)
    assert [e.data["text"] for e in events(rt, cid, "reply_held")] == [CANNED_REPLY]


def test_a_crash_on_a_parked_case_still_leaves_a_staff_task(rt):
    rt.agents["orchestrator"] = dataclasses.replace(rt.agents["orchestrator"], tools=_boom)
    cid = rt.store.create_case(CaseFile(case_id="c", stage=3, filings=FILED, side_state="needs_human")).case_id
    rt._enqueue(cid, Job("orchestrator", "[wake] staff_note", "wake"))
    try:
        rt.wait_until_idle(cid)
    except RuntimeError:
        pass
    assert any("orchestrator turn crashed" in t.text for t in rt.store.get_case(cid).tasks)


def test_a_repeated_failure_on_a_parked_case_leaves_one_staff_task(rt):
    """The same "<agent> turn <status>" while its task is open adds no task."""
    cid = rt.store.create_case(CaseFile(case_id="c", stage=3, filings=FILED, side_state="needs_human")).case_id
    rt.to_staff(cid, "orchestrator turn error: timed out")
    rt.to_staff(cid, "orchestrator turn error: model said no")
    rt.to_staff(cid, "claims_prep turn limit: 40 steps")
    assert [t.text for t in rt.store.get_case(cid).tasks] == ["orchestrator turn error: timed out",
                                                             "claims_prep turn limit: 40 steps"]  # fmt: skip


def test_an_owner_turn_with_no_reply_is_nudged_once_then_canned(rt, lm):
    """D28 (live run 1 stalled): the veteran is waiting and intake sent nothing."""
    cid = opened(rt, lm)
    lm.turn("intake", final(reply=""))
    lm.turn("intake", final(reply="Sorry, which branch were you in?"))
    rt.message(cid, "Yes, Army.")
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("intake", "Sorry, which branch were you in?")
    nudge = incoming(lm.prompts("intake")[-1])
    assert "[nudge]" in nudge and "Yes, Army." in nudge and "<untrusted" in nudge
    lm.turn("intake", final(reply=""))
    lm.turn("intake", final(reply=""))
    rt.message(cid, "Army, 2004 to 2010.")
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("intake", CANNED_REPLY)
