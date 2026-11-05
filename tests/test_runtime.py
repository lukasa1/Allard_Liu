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


@pytest.mark.parametrize("owner", ["intake", "support"])
def test_crisis_language_codes_check_misses_is_caught_by_the_agent(rt, lm, owner):
    """A wording code's check misses reaches the model; crisis_to_person does the rule's hand-off
    (the Crisis Line from code, an urgent task, needs_human) and the turn's own reply is held."""
    text = "Some nights I sit in the garage with my pistol and think about it."
    if owner == "intake":
        cid = opened(rt, lm)
    else:
        cid = rt.store.create_case(CaseFile(case_id="c5", stage=5, prep=PREP_DONE, filings=FILED)).case_id
    lm.turn(owner, call("crisis_to_person", reason="sits in the garage with a pistol thinking about it"),
            final(reply="Thank you. Next: how does it affect your work?"))  # fmt: skip
    lm.turn("orchestrator", final())  # the escalated wake
    if owner == "intake":
        lm.turn("orchestrator", final())  # intake's result (it ended on a parked case)
    rt.message(cid, text)
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE)  # the turn's next question was held
    assert any(e.data.get("text", "").startswith("Thank you. Next") for e in events(rt, cid, "reply_held"))
    case = rt.store.get_case(cid)
    assert case.side_state == "needs_human" and [t.kind for t in case.tasks][:1] == ["urgent"]
    esc = [e for e in events(rt, cid, "escalated") if e.data["reason"] == "crisis"]
    assert [e.actor for e in esc] == [owner]


@pytest.mark.parametrize(("kind", "reply"), [("withdraw", WITHDRAW_MESSAGE), ("wants_human", HANDOFF_MESSAGE)])
def test_a_request_codes_check_misses_is_handed_over_by_intake(rt, lm, kind, reply):
    """"I've changed my mind, forget the whole thing" misses wants_withdraw; intake's to_person
    does the rule's hand-off (its reply from code, a staff task, needs_human) and its own reply is held."""
    from agent.ingest import wants_human, wants_withdraw

    text = {"withdraw": "I've changed my mind, let's forget the whole thing.",
            "wants_human": "Honestly I'd feel better hearing a human voice about this."}[kind]
    assert not wants_withdraw(text) and not wants_human(text)  # else code catches it and this tests nothing
    cid = opened(rt, lm)
    lm.turn("intake", call("to_person", kind=kind, reason=text), final(reply="Okay. Next: which branch?"))
    lm.turn("orchestrator", final())  # the escalated wake
    lm.turn("orchestrator", final())  # intake's result (it ended on a parked case)
    rt.message(cid, text)
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("rule", reply)
    case = rt.store.get_case(cid)
    assert case.side_state == "needs_human" and case.tasks[0].kind == "staff"
    assert [(e.actor, e.data["reason"]) for e in events(rt, cid, "escalated")] == [("intake", kind)]


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
    """The veteran is waiting and intake sent nothing: the run must not stall."""
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


def test_a_retried_turns_repeated_card_shows_once_where_it_last_came():
    from agent.runtime import _last_of_each

    sign, preview = {"type": "sign_button", "document_id": "d", "version": 1}, {"type": "document_preview", "v": 2}
    assert _last_of_each([sign, preview, sign]) == [preview, sign]  # the Sign card stays the newest
    assert _last_of_each([preview, preview]) == [preview]


def test_the_pinned_clock_stands_still_and_hands_back_the_live_one():
    from datetime import UTC, datetime

    import pytest

    from agent import clock
    from poa_skill import documents as poa_documents

    with clock.pinned("a"):
        first = (clock.now_iso(), clock.now_iso(), poa_documents.now_iso(), clock.token_hex(6))
        with pytest.raises(RuntimeError), clock.pinned("b"):  # one case at a time
            pass
    with clock.pinned("a"):
        again = (clock.now_iso(), clock.now_iso(), poa_documents.now_iso(), clock.token_hex(6))
    assert first == again and first[0] == first[1] == clock.PINNED_START.isoformat()
    assert not clock.is_pinned() and abs((clock.now() - datetime.now(UTC)).total_seconds()) < 5
    assert poa_documents.CLOCK == poa_documents.LIVE_CLOCK and clock.token_hex(6) != first[3]


def test_nothing_reads_the_wall_clock_or_random_ids_past_agent_clock():
    """Every timestamp, date and random id in a prompt must come from agent/clock.py (or poa_skill's
    CLOCK), or an eval rerun stops matching the cache. The DOB range check is the one exception."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    allowed = {"agent/clock.py", "poa_skill/documents.py"}
    pattern = re.compile(r"date\.today\(\)|datetime\.now\(|datetime\.utcnow\(|uuid\.uuid4|secrets\.(token_|choice)|random\.")
    found = []
    for path in [*root.glob("agent/**/*.py"), *root.glob("poa_skill/**/*.py"), *root.glob("intake_eval/**/*.py")]:
        rel = path.relative_to(root).as_posix()
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if rel not in allowed and pattern.search(line):
                found.append(f"{rel}:{n}: {line.strip()}")
    exceptions = ("run_name = run_name or", "<= d <= date.today()")  # the results folder name; the DOB check
    assert [f for f in found if not any(e in f for e in exceptions)] == []


def test_a_reply_held_by_a_crisis_holds_the_turns_cards_too(rt, lm):
    """The rule's crisis message stays the last word: a secure-form card the interrupted turn made
    is not shown after it."""
    from conftest import VETERAN
    from intake_fixtures import SCREEN_STEPS

    cid = opened(rt, lm)
    gate = threading.Event()
    lm.turn("intake", *SCREEN_STEPS, call("request_secure_info", fields=list(VETERAN), purpose="For the 21-22a."),
            pause(gate), final(reply="Please fill in the secure form."))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, "Yes, Army 2004 to 2010, honorable. Never filed. No lawyer.")
    # the turn has run the secure-form tool and waits at the gate (its 1 + 6 + 1 + 1st prompt)
    until(lambda: len(lm.prompts("intake")) == 1 + len(SCREEN_STEPS) + 2)
    rt.message(cid, "Honestly I just want to kill myself.")
    gate.set()
    rt.wait_until_idle()
    out = rt.updates(cid)
    assert (out[-1].kind, out[-1].payload["text"]) == ("message", CRISIS_MESSAGE)
    assert not [o for o in out if o.kind == "card"]
    assert [[c["type"] for c in e.data["cards"]] for e in events(rt, cid, "cards_held")] == [["secure_form"]]


@pytest.mark.parametrize("ending", ["no reply", "unusable output", "crash"])
def test_a_silent_failed_or_crashed_turn_after_a_crisis_holds_its_cards(rt, lm, monkeypatch, ending):
    """Held by the same rule as a reply, however the turn ended."""
    from conftest import VETERAN
    from intake_fixtures import SCREEN_STEPS

    cid = opened(rt, lm)
    gate = threading.Event()
    last = {"no reply": [final(reply="")], "unusable output": [bad(), bad()], "crash": [final(reply="Hi")]}[ending]
    lm.turn("intake", *SCREEN_STEPS, call("request_secure_info", fields=list(VETERAN), purpose="For the 21-22a."),
            pause(gate), *last)  # fmt: skip
    lm.turn("orchestrator", final())
    if ending == "crash":
        run = rt.harness.run

        def crashing(spec, turn):
            out = run(spec, turn)
            if turn.cards:
                raise RuntimeError("boom")
            return out

        monkeypatch.setattr(rt.harness, "run", crashing)
    rt.message(cid, "Yes, Army 2004 to 2010, honorable. Never filed. No lawyer.")
    until(lambda: len(lm.prompts("intake")) == 1 + len(SCREEN_STEPS) + 2)
    rt.message(cid, "Honestly I just want to kill myself.")
    gate.set()
    if ending == "crash":
        with pytest.raises(RuntimeError):
            rt.wait_until_idle()
    rt.wait_until_idle()
    out = rt.updates(cid)
    assert CRISIS_MESSAGE in [o.payload.get("text") for o in out] and not [o for o in out if o.kind == "card"]
    assert [[c["type"] for c in e.data["cards"]] for e in events(rt, cid, "cards_held")] == [["secure_form"]]


def test_crisis_backstop_works_after_the_turn_lost_the_case(rt, lm):
    """A non-veteran's case closes on the stop rule mid-turn; intake's crisis_to_person in the same
    turn still sends the Crisis Line and opens an urgent task (the lost-ownership guard lets it)."""
    from agent.ingest import detect_crisis

    text = "No, I never served, it was my dad. Some nights I sit in the garage with his pistol and think about it."
    assert not detect_crisis(text)
    cid = opened(rt, lm)
    lm.turn("intake", call("record_answer", q="is_veteran", a="No, I never served", value=False),
            call("crisis_to_person", reason="sits in the garage with a pistol thinking about it"),
            final(reply="I'm sorry, we can only help veterans."))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, text)
    rt.wait_until_idle()
    assert messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE)  # intake's own reply is held back
    assert any(t.kind == "urgent" for t in rt.store.get_case(cid).tasks)
