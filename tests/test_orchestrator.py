"""The orchestrator and the runtime protocol end to end (plan §2-§3, L10-L13), with the
sub-agent stubs and the scripted fake LM."""

import dataclasses
import threading
import time

from fake_lm import bad, call, final, pause

from agent.casefile import CaseFile, DocState, Filing, PrepState
from agent.harness import CANNED_REPLY
from agent.intake.controller import CRISIS_MESSAGE, HANDOFF_MESSAGE
from agent.runtime import WITHDRAW_MESSAGE, route

T = "2026-11-03T10:00:00+00:00"
FILED = {"21-22a": Filing(confirmation="A"), "itf": Filing(confirmation="B")}


def _until(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while not pred():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def _types(rt, cid, *types):
    return [e for e in rt.store.events(cid) if e.type in types]


def _messages(rt, cid):
    return [(o.agent, o.payload["text"]) for o in rt.updates(cid) if o.kind == "message"]


def _sign(case):
    case.documents = {f: DocState(signed_at=T) for f in ("21-22a", "fee_agreement")}


def _countersign(case):
    for d in case.documents.values():
        d.countersigned_at, d.countersigned_by = T, "Attorney A"


def _case_at(rt, **fields) -> str:
    return rt.store.create_case(CaseFile(case_id="c1", **fields)).case_id


def _opened_with_intake(rt, lm) -> str:
    lm.turn("orchestrator", call("run_intake", goal="Pass 1: screen, sign, file."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Did you serve in the military?"))
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    return cid


def test_the_demo_flow_reaches_ready_for_attorney_review(rt, lm):
    cid = _opened_with_intake(rt, lm)
    assert rt.store.get_case(cid).side_state == "waiting_on_veteran"

    lm.turn("intake", call("record_answer", question_id="served", value="yes"),
            call("record_answer", question_id="discharge", value="honorable"),
            call("record_answer", question_id="rating", value="30"), final(reply="Please sign both documents."))  # fmt: skip
    rt.message(cid, "Yes, Army, honorable, rated 30%.")
    rt.wait_until_idle()
    assert rt.store.get_case(cid).stage == 2

    lm.turn("intake", final(reply="Thanks! Our attorney is reviewing both documents."))
    rt.event(cid, "signed", {"forms": ["21-22a", "fee_agreement"]}, actor="veteran", apply=_sign)
    rt.wait_until_idle()
    assert rt.store.get_case(cid).side_state == "waiting_on_attorney"

    lm.turn("intake", final(reply="Usually within a day."))  # D1: still intake's while it waits
    rt.message(cid, "How long does the review take?")
    rt.wait_until_idle()

    pass1 = {"finished": "pass 1: 21-22a and ITF filed, fee agreement faxed", "wrote": ["filings"], "needs": [], "flags": []}
    lm.turn("intake", call("submit_va", form="21-22a"), call("submit_va", form="itf"), call("efax_ogc"),
            final(reply="Filed with VA!", result=pass1))  # fmt: skip
    lm.turn("orchestrator", call("run_prep", goal="Pull and read the C-file, prefill, face note."),
            final(reply="We've asked VA for your file."))  # fmt: skip
    lm.turn("claims_prep", call("finish_prep"), final(result={"finished": "face note verified"}))
    lm.turn("orchestrator", call("run_intake", goal="Pass 2: ask only the gaps."), final())
    lm.turn("intake", final(reply="Which conditions do you want to claim?"))
    rt.event(cid, "countersigned", {"by": "Attorney A"}, actor="staff", apply=_countersign)
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.prep.done) == (4, "intake", True)

    lm.turn("intake", call("record_answer", question_id="conditions", value="back"),
            final(reply="Thank you, that's everything.", result={"finished": "pass 2: gaps closed"}))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, "My back.")
    rt.wait_until_idle()

    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.side_state) == (5, None, None)
    results = [e.data["result"] for e in _types(rt, cid, "subagent_result")]
    assert [(r["agent"], r["finished"]) for r in results] == [
        ("intake", pass1["finished"]), ("claims_prep", "face note verified"), ("intake", "pass 2: gaps closed")]  # fmt: skip
    assert [e.data["to"] for e in _types(rt, cid, "handoff")] == ["intake", "claims_prep", "intake"]
    stages = [e.data["to"] for e in _types(rt, cid, "stage_changed")]
    assert stages == [2, 3, 4, 5]
    assert _messages(rt, cid)[0] == ("orchestrator", "Welcome!")
    assert set(rt.harness.traces.cost_by_agent(cid)) == {"orchestrator", "intake", "claims_prep"}
    # The orchestrator's memory block never holds a transcript.
    assert not any("How long" in p or "My back" in p for p in lm.prompts("orchestrator"))


def test_a_handoff_runs_the_sub_agents_first_turn_after_the_wake(rt, lm):
    _opened_with_intake(rt, lm)
    agents = [s.agent for s in lm.seen]
    first_intake = agents.index("intake")
    assert set(agents[:first_intake]) == {"orchestrator"} and "orchestrator" not in agents[first_intake:]


def test_messages_route_to_the_owner_or_support():
    assert route(CaseFile(case_id="c", owner="intake", side_state="waiting_on_attorney")) == "intake"
    assert route(CaseFile(case_id="c", owner="claims_prep")) == "support"
    assert route(CaseFile(case_id="c")) == "support"
    assert route(CaseFile(case_id="c", owner="intake", side_state="needs_human")) == "support"


def test_a_flag_during_claims_prep_is_held_and_decided_with_its_result(rt, lm):
    cid = _case_at(rt, stage=3, filings=FILED)
    gate = threading.Event()
    lm.turn("orchestrator", call("run_prep", goal="Read the C-file."), final())
    lm.turn("claims_prep", pause(gate), call("finish_prep"), final())
    lm.turn("support", call("flag_orchestrator", kind="new_condition", text="knees"), final(reply="Noted."))
    rt.event(cid, "case_imported", {}, actor="staff")  # nobody owns the case: wakes the orchestrator
    _until(lambda: any(s.agent == "claims_prep" for s in lm.seen))

    rt.message(cid, "I also want to claim my knees too.")  # support answers while prep runs
    _until(lambda: ("support", "Noted.") in _messages(rt, cid))
    case = rt.store.get_case(cid)
    assert case.owner == "claims_prep" and case.flags[0].status == "held"
    assert len([s for s in lm.seen if s.agent == "orchestrator"]) == 3  # no wake for the held flag

    lm.turn("orchestrator", call("run_intake", goal="Pass 2; also ask about the knees."), final())
    lm.turn("intake", final(reply="Tell me about your knees."))
    gate.set()
    rt.wait_until_idle()
    wake = lm.prompts("orchestrator")[-1]
    assert "subagent_result" in wake.split("[[ ## incoming ## ]]")[1] and '"text": "knees"' in wake
    case = rt.store.get_case(cid)
    assert case.flags[0].status == "handled" and case.goal == "Pass 2; also ask about the knees."


def test_a_flag_outside_stage_4_wakes_the_orchestrator_which_reopens_intake(rt, lm):
    cid = _case_at(rt, stage=5, prep=PrepState(face_note="n", verified=True, prefill_done=True),
                   checklist={"screen": [], "pass2": []}, filings=FILED)  # fmt: skip
    lm.turn("support", call("flag_orchestrator", kind="new_condition", text="knees"), final(reply="Noted."))
    lm.turn("orchestrator", call("read_skill", name="flags"), call("move_stage", to="4", reason="new condition: knees"),
            call("run_intake", goal="Ask about the knees and their narrative prompts."), final())  # fmt: skip
    lm.turn("intake", final(reply="Tell me about your knees."))
    rt.message(cid, "I also want to claim my knees too.")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.checklist["pass2"], case.flags[0].status) == (4, "intake", None, "handled")


def test_refused_moves_are_returned_logged_and_end_nothing(rt, lm):
    lm.turn("orchestrator", call("run_prep", goal="Read the C-file."), call("move_stage", to="3", reason="skip ahead"),
            call("move_stage", to="closed", reason=""), call("run_intake", goal="Pass 1."),
            call("run_prep", goal="Read the C-file."), final(reply="Hi."))  # fmt: skip
    lm.turn("intake", final(reply="Did you serve?"))
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    refused = _types(rt, cid, "refused")
    assert [e.data["tool"] for e in refused] == ["run_prep", "move_stage", "run_prep"]
    assert all(e.actor == "orchestrator" for e in refused)
    traj = lm.prompts("orchestrator", "extract")[0]
    assert "refused: claims prep starts at stage 3" in traj
    assert "refused: move_stage only moves back" in traj
    assert "invalid_args: reason" in traj
    assert "refused: this wake already handed the case to intake" in traj
    assert rt.store.get_case(cid).owner == "intake"


def test_closed_is_refused_after_filing(rt, lm):
    cid = _case_at(rt, stage=3, filings=FILED)
    lm.turn("orchestrator", call("move_stage", to="closed", reason="veteran asked"), final())
    rt.event(cid, "staff_note", {}, actor="staff")
    rt.wait_until_idle()
    assert "filed with VA" in _types(rt, cid, "refused")[0].data["reason"]
    assert rt.store.get_case(cid).side_state != "closed"


def test_crisis_language_is_handled_in_code_before_any_model(rt, lm):
    cid = _opened_with_intake(rt, lm)
    intake_calls = len(lm.prompts("intake"))
    lm.turn("orchestrator", final())
    rt.message(cid, "Honestly I just want to kill myself.")
    rt.wait_until_idle()
    assert len(lm.prompts("intake")) == intake_calls
    assert _messages(rt, cid)[-1] == ("rule", CRISIS_MESSAGE)
    case = rt.store.get_case(cid)
    assert (case.side_state, case.owner, case.tasks[0].kind) == ("needs_human", None, "urgent")
    assert "escalated" in lm.prompts("orchestrator")[-1].split("[[ ## incoming ## ]]")[1]


def test_a_request_for_a_person_or_to_withdraw_goes_to_a_person_by_rule(rt, lm):
    cid = _opened_with_intake(rt, lm)
    lm.turn("orchestrator", final())
    rt.message(cid, "Can I talk to a real person?")
    rt.wait_until_idle()
    assert _messages(rt, cid)[-1] == ("rule", HANDOFF_MESSAGE)
    assert rt.store.get_case(cid).side_state == "needs_human"
    lm.turn("support", final(reply="A person will call you."))  # parked: support answers
    rt.message(cid, "I want to cancel my representation.")
    rt.wait_until_idle()
    assert _messages(rt, cid)[-1] == ("support", "A person will call you.")

    rt2_cid = _case_at(rt, owner="intake")
    lm.turn("orchestrator", final())
    rt.message(rt2_cid, "I want to cancel my representation.")
    rt.wait_until_idle()
    assert _messages(rt, rt2_cid)[-1] == ("rule", WITHDRAW_MESSAGE)


def test_a_stop_rule_closes_the_case_and_returns_the_pass(rt, lm):
    cid = _opened_with_intake(rt, lm)
    lm.turn("intake", call("fire_stop_rule", rule="rated_100", reason="already rated 100%"),
            call("record_answer", question_id="served", value="yes"), final(reply="We can't take this case."))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, "I'm already rated 100%.")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.side_state, case.owner) == ("closed", None)
    assert "refused: you no longer own the case" in lm.prompts("intake", "extract")[-1]
    assert _types(rt, cid, "subagent_result")[0].data["result"]["finished"].endswith("closed")


def test_filing_is_refused_before_the_countersign(rt, lm):
    cid = _opened_with_intake(rt, lm)
    lm.turn("intake", call("submit_va", form="21-22a"), final(reply="We need the attorney first."))
    rt.message(cid, "Please file it now.")
    rt.wait_until_idle()
    assert "countersigned" in _types(rt, cid, "refused")[0].data["reason"]
    assert rt.store.get_case(cid).filings == {}


def test_claims_prep_continues_after_max_iters_then_needs_a_person(rt, lm):
    rt.agents["claims_prep"] = dataclasses.replace(rt.agents["claims_prep"], max_iters=1)
    cid = _case_at(rt, stage=3, filings=FILED)
    lm.turn("orchestrator", call("run_prep", goal="Read the C-file."), final())
    for _ in range(4):
        lm.turn("claims_prep", call("read_skill", name="face-note-format"), final())
    rt.event(cid, "case_imported", {}, actor="staff")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.prep.continuations, case.side_state) == (3, "needs_human")
    assert lm.prompts("claims_prep")[1].split("[[ ## incoming ## ]]")[1].strip().startswith("[continue]")


def test_a_failed_orchestrator_wake_puts_the_case_with_a_person(rt, lm):
    lm.turn("orchestrator", bad(), bad(), bad(), bad())
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert case.side_state == "needs_human" and "failed" in case.side_reason


def test_a_failed_intake_turn_sends_the_canned_reply(rt, lm):
    cid = _opened_with_intake(rt, lm)
    lm.turn("intake", bad(), bad(), bad(), bad())
    rt.message(cid, "Army.")
    rt.wait_until_idle()
    assert _messages(rt, cid)[-1] == ("intake", CANNED_REPLY)
