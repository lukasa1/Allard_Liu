"""The orchestrator (plan §2-§3, L10-L13) with the real sub-agents and the scripted fake LM: its
refused moves, stop rules, claims prep's continuations and hand back, flags, reopening intake
after stage 5, and staff tasks."""

import dataclasses

from helpers import FILED, PREP_DONE, events, incoming, messages, opened
from intake_fixtures import answered

from agent.casefile import Answer, CaseFile, Flag, PrepState
from agent.intake import checklist
from agent.runtime import Job
from agent.scripted.lm import bad, call, final

# ------------------------------------------------------------------------------ moves and stop rules


def test_refused_moves_are_returned_logged_and_end_nothing(rt, lm):
    lm.turn("orchestrator", call("run_prep", goal="Read the C-file."), call("move_stage", to="4", reason="skip ahead"),
            call("move_stage", to="closed", reason=""), call("run_intake", goal="Pass 1."),
            call("run_prep", goal="Read the C-file."), final(reply="Hi."))  # fmt: skip
    lm.turn("intake", final(reply="Did you serve?"))
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    refused = events(rt, cid, "refused")
    assert [e.data["tool"] for e in refused] == ["run_prep", "move_stage", "run_prep"]
    assert all(e.actor == "orchestrator" for e in refused)
    traj = lm.prompts("orchestrator", "extract")[0]
    assert "refused: claims prep starts at stage 3" in traj
    assert "refused: move_stage only moves back" in traj
    assert "invalid_args: reason" in traj
    assert "refused: this wake already handed the case to intake" in traj
    assert rt.store.get_case(cid).owner == "intake"


def test_closed_is_refused_after_filing(rt, lm):
    cid = rt.store.create_case(CaseFile(case_id="c1", stage=3, filings=FILED)).case_id
    lm.turn("orchestrator", call("move_stage", to="closed", reason="veteran asked"), final())
    rt.event(cid, "staff_note", {}, actor="staff")
    rt.wait_until_idle()
    assert "filed with VA" in events(rt, cid, "refused")[0].data["reason"]
    assert rt.store.get_case(cid).side_state != "closed"


def test_a_stop_rule_closes_the_case_and_returns_the_pass(rt, lm):
    cid = opened(rt, lm)
    lm.turn("intake", call("record_answer", q="is_veteran", a="No, I never served"),
            call("record_answer", q="filed_before", a="no"), final(reply="We can't take this case."))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, "I never served, I'm asking for my dad.")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stop.rule, case.side_state, case.owner) == ("not_veteran", "closed", None)
    assert "refused: you no longer own the case" in lm.prompts("intake", "extract")[-1]
    assert events(rt, cid, "subagent_result")[0].data["result"]["finished"].endswith("closed")
    # The owner's reply goes out: a stop rule isn't a person taking over.
    assert messages(rt, cid)[-1] == ("intake", "We can't take this case.") and not events(rt, cid, "reply_held")


# ------------------------------------------------------------------------------ claims prep


def test_claims_prep_continues_after_max_iters_then_needs_a_person(rt, lm):
    rt.agents["claims_prep"] = dataclasses.replace(rt.agents["claims_prep"], max_iters=1)
    cid = rt.store.create_case(CaseFile(case_id="c1", stage=3, filings=FILED)).case_id
    lm.turn("orchestrator", call("run_prep", goal="Read the C-file."), final())
    for _ in range(4):
        lm.turn("claims_prep", call("read_skill", name="face-note-format"), final())
    rt.event(cid, "case_imported", {}, actor="staff")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.prep.continuations, case.side_state) == (3, "needs_human")
    assert incoming(lm.prompts("claims_prep")[1]).strip().startswith("[continue]")


def test_prep_hand_back_lets_the_result_wake_hand_off_to_intake(rt, lm):
    cid = answered(rt, 4, leave=("narrative:tinnitus:h02",), owner="claims_prep")
    lm.turn("claims_prep", final())  # the stop rule holds: hand back
    lm.turn("orchestrator", call("run_intake", goal="Pass 2."), final())
    lm.turn("intake", final(reply="A few questions."))
    rt._enqueue(cid, Job("claims_prep", "[continue]", "continue"))
    rt.wait_until_idle()
    assert rt.store.get_case(cid).owner == "intake" and not events(rt, cid, "refused")
    assert "<untrusted" in incoming(lm.prompts("orchestrator")[0])  # the result is model text: data


def test_prep_out_of_continuations_leaves_a_staff_task_with_the_held_flags(rt, lm):
    cid = rt.store.create_case(CaseFile(case_id="c", stage=4, owner="claims_prep", filings=FILED,
                                        prep=PrepState(continuations=3),
                                        flags=[Flag(kind="new_condition", text="knees", status="held")])).case_id  # fmt: skip
    lm.turn("claims_prep", final())
    rt._enqueue(cid, Job("claims_prep", "[continue]", "continue"))
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert case.side_state == "needs_human"
    assert any("new_condition: knees" in t.text for t in case.tasks)


# ------------------------------------------------------------------------------ flags and reopening intake


def test_reopening_a_fully_answered_case_waits_for_the_new_condition(rt, lm):
    cid = answered(rt, 5, case_id="c5")
    assert rt.store.get_case(cid).checklist["pass2"] == []
    lm.turn("support", call("flag_orchestrator", kind="new_condition", text="knees"), final(reply="Noted."))
    lm.turn("orchestrator", call("move_stage", to="4", reason="new condition: knees"),
            call("run_intake", goal="Ask about the knees and their narrative prompts."), final())  # fmt: skip
    lm.turn("intake", final(reply="Tell me about your knees."))
    rt.message(cid, "I also want to claim my knees.")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.checklist["pass2"]) == (4, "intake", ["claim_conditions"])
    assert case.flags[0].status == "handled"
    (item,) = checklist.missing(case, "pass2")
    assert "new condition: knees" in item.ask

    lm.turn("intake", call("record_answer", q="claim_conditions", a='["tinnitus", "knees"]'), final(reply="Thanks."))
    rt.message(cid, "Yes, tinnitus and my knees.")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert case.stage == 4 and case.owner == "intake"  # the veteran's answer went to intake, not support
    assert case.checklist["pass2"] and all(k.startswith("narrative:") for k in case.checklist["pass2"])

    def narratives(c):
        for key in c.checklist["pass2"]:
            c.answers[key] = Answer(value="it hurts", source="veteran, chat")
        checklist.refresh(c)

    rt.patch(cid, narratives, actor="intake")
    assert rt.store.get_case(cid).stage == 5


def test_run_intake_at_stage_4_after_a_new_condition_flag_reopens_claim_conditions(rt, lm):
    cid = answered(rt, 4, flags=[Flag(kind="new_condition", text="knees")])
    lm.turn("orchestrator", call("run_intake", goal="Pass 2; also ask about the knees."), final())
    lm.turn("intake", final(reply="Tell me about your knees."))
    rt.event(cid, "prep_returned", {}, actor="staff")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.checklist["pass2"]) == (4, "intake", ["claim_conditions"])


def test_flags_stay_open_when_the_wake_did_nothing(rt, lm):
    case = CaseFile(case_id="c5", stage=5, prep=PREP_DONE, filings=FILED, flags=[Flag(kind="new_condition", text="knees")])
    cid = rt.store.create_case(case).case_id
    lm.turn("orchestrator", call("run_intake", goal="Ask about the knees."), final())  # refused at stage 5
    rt.event(cid, "staff_note", {}, actor="staff")
    rt.wait_until_idle()
    assert rt.store.get_case(cid).flags[0].status == "open"


def test_two_flags_in_one_support_turn_wake_the_orchestrator_once(rt, lm):
    cid = rt.store.create_case(CaseFile(case_id="c", stage=3, filings=FILED)).case_id
    lm.turn("support", call("flag_orchestrator", kind="contact_change", text="new phone"),
            call("flag_orchestrator", kind="complaint", text="slow"), final(reply="Passed on."))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, "My phone changed and you're slow")
    rt.wait_until_idle()
    assert len(lm.prompts("orchestrator")) == 1 and not lm.unused()
    assert [f.kind for f in rt.store.get_case(cid).flags] == ["contact_change", "complaint"]


def test_a_retried_support_attempt_does_not_duplicate_its_flag(rt, lm):
    cid = rt.store.create_case(CaseFile(case_id="c", stage=3, filings=FILED)).case_id
    lm.turn("support", call("flag_orchestrator", kind="complaint", text="slow"), bad(),
            call("flag_orchestrator", kind="complaint", text="slow"), final(reply="Passed on."))  # fmt: skip
    lm.turn("orchestrator", final())
    rt.message(cid, "You're slow")
    rt.wait_until_idle()
    assert [f.kind for f in rt.store.get_case(cid).flags] == ["complaint"]
    assert len(events(rt, cid, "support_flag")) == 1


def test_staff_tasks_are_deduped_and_allowed_after_a_handoff(rt, lm):
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), call("staff_task", text="Call the veteran."),
            call("staff_task", text="Call the veteran."), final())  # fmt: skip
    lm.turn("intake", final(reply="Did you serve?"))
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    assert [t.text for t in rt.store.get_case(cid).tasks] == ["Call the veteran."]
    traj = lm.prompts("orchestrator", "extract")[0]
    assert "staff task created" in traj and "already open" in traj
