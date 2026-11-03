"""The stage table and its guard (plan §2): derived in code, every change checked."""

from agent import stages
from agent.casefile import CaseFile, DocState, Filing, StopRule

T = "2026-11-03T10:00:00+00:00"


def _case(**kw) -> CaseFile:
    return CaseFile(case_id="c", **kw)


def _signed(countersigned=False):
    return {f: DocState(signed_at=T, countersigned_at=T if countersigned else None) for f in stages.SIGNED_FORMS}


def _filed(*names):
    return {n: Filing(confirmation="X") for n in names}


def test_intake_moves_forward_automatically_when_criteria_hold():
    case = _case(owner="intake", checklist={"screen": []})
    events = stages.settle(case)
    assert case.stage == 2 and events[0]["data"] == {"from": 1, "to": 2, "actor": "derive", "reason": "exit criteria met"}
    case.filings = _filed("21-22a", "itf")
    stages.settle(case)
    assert case.stage == 3


def test_nothing_moves_without_its_criteria_or_without_the_owner():
    case = _case(owner="intake", checklist={"screen": ["branch"]})
    assert stages.settle(case) == [] and case.stage == 1
    case = _case(checklist={"screen": []})  # nobody owns it: forward moves need the owner's pass
    stages.settle(case)
    assert case.stage == 1
    case = _case(owner="intake", stage=2, filings=_filed("21-22a"))
    stages.settle(case)
    assert case.stage == 2


def test_stage_4_only_by_handoff_and_stage_6_never():
    case = _case(stage=3, filings=_filed("21-22a", "itf"))
    assert "run_prep" in stages.check_stage(case, 4, "derive")
    assert stages.check_stage(case, 4, "handoff") is None
    assert "F7" in stages.check_stage(_case(stage=5), 6, "derive")


def test_waiting_states_are_derived():
    case = _case(owner="intake", stage=2, documents=_signed())
    stages.settle(case)
    assert case.side_state == "waiting_on_attorney"
    case.documents = _signed(countersigned=True)
    case.awaiting_veteran = True
    stages.settle(case)
    assert case.side_state == "waiting_on_veteran"
    case.owner, case.stage, case.filings = None, 3, _filed("21-22a", "itf")
    stages.settle(case)
    assert case.side_state == "waiting_on_va"


def test_a_stop_rule_closes_before_filing_and_needs_a_person_after():
    case = _case(owner="intake", stop=StopRule(rule="rated_100", reason="rated 100%"))
    stages.settle(case)
    assert case.side_state == "closed" and "rated_100" in case.side_reason and case.owner is None
    case = _case(owner="intake", stage=3, filings=_filed("21-22a", "itf"),
                 stop=StopRule(rule="not_veteran", reason="never served"))  # fmt: skip
    stages.settle(case)
    assert case.side_state == "needs_human"


def test_the_guard_refuses_illegal_moves_with_reasons():
    case = _case(stage=2)
    assert "skip" in stages.check_stage(case, 4, "orchestrator")
    assert "forward moves happen in code" in stages.check_stage(_case(stage=1, checklist={"screen": []}), 2, "orchestrator")
    at_5 = _case(stage=5)
    assert "needs a reason" in stages.check_stage(at_5, 4, "orchestrator")
    assert "only the orchestrator" in stages.check_stage(at_5, 4, "intake", "why")
    assert "holds the case" in stages.check_stage(_case(stage=5, owner="intake"), 4, "orchestrator", "why")
    assert stages.check_stage(at_5, 4, "orchestrator", "new condition") is None
    # F9: the only move back is to pass 2 (a move to stage 1-3 would strand the case)
    assert "only move back is to stage 4" in stages.check_stage(case, 1, "orchestrator", "redo screening")
    assert "only move back is to stage 4" in stages.check_stage(at_5, 2, "orchestrator", "redo")
    assert "filed with VA" in stages.check_side(_case(filings=_filed("21-22a")), "closed", "orchestrator", "no")
    assert "derived" in stages.check_side(case, "waiting_on_va", "orchestrator", "x")
    parked = _case(stage=2, side_state="needs_human")
    assert "only a person" in stages.check_stage(parked, 1, "orchestrator", "x")
    assert "only a person" in stages.check_side(parked, None, "derive")


def test_handoffs_are_guarded_one_owner_at_a_time():
    assert stages.check_handoff(_case(), "intake", set()) is None
    assert "owns the case" in stages.check_handoff(_case(owner="intake"), "claims_prep", set())
    assert "running turn" in stages.check_handoff(_case(stage=4), "intake", {"claims_prep"})
    assert "after claims prep" in stages.check_handoff(_case(stage=4), "intake", set())
    assert "stage 3" in stages.check_handoff(_case(stage=1), "claims_prep", set())
    assert "exit criteria" in stages.check_handoff(_case(stage=3), "claims_prep", set())
    assert stages.check_handoff(_case(stage=3, filings=_filed("21-22a", "itf")), "claims_prep", set()) is None
    assert "move the case back" in stages.check_handoff(_case(stage=5), "intake", set())


def test_moving_back_reopens_the_stage_checklist():
    case = _case(stage=5, checklist={"screen": [], "pass2": []})
    event = stages.move(case, 4, "orchestrator", "new condition")
    assert event["type"] == "stage_changed" and case.stage == 4 and case.checklist == {"screen": [], "pass2": None}
    event = stages.move(case, "needs_human", "orchestrator", "")
    assert event["type"] == "refused" and "reason" in event["data"]["reason"]
