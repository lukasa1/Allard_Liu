"""The orchestrator's gates and policies."""

from agent.case import CaseState
from agent.intake.schema import Outcome
from agent.orchestrator import WAIT, DSPyPolicy, OfflinePolicy, Orchestrator, allowed_actions


def test_gates_follow_the_phases():
    c = CaseState(case_id="c1")
    assert allowed_actions(c) == ["request_va_sign_in"]
    c.phase, c.va_consent = "va_sign_in", "pending"
    assert allowed_actions(c) == [WAIT]
    c.va_consent = "granted"
    assert allowed_actions(c) == ["fetch_va_records"]  # records first, then screening


def test_nothing_is_filed_before_the_attorney_countersigns():
    c = CaseState(case_id="c2a", phase="poa", va_consent="declined", poa_document_id="doc")
    assert allowed_actions(c) == ["request_attorney_signoff"]
    c.phase = "attorney_signoff"
    assert allowed_actions(c) == [WAIT]  # the attorney's move
    c.poa_countersigned_at = "2026-11-03T10:00:00+00:00"
    assert allowed_actions(c) == ["submit_poa_to_va"]


def test_no_cfile_before_the_poa_and_the_intent_to_file_are_filed():
    c = CaseState(case_id="c2", phase="attorney_signoff", va_consent="declined", poa_document_id="doc",
                  poa_countersigned_at="t")  # fmt: skip
    assert "fetch_cfile" not in allowed_actions(c)
    c.poa_submission = {"method": "manual"}
    assert "fetch_cfile" not in allowed_actions(c)  # the intent to file comes first
    assert allowed_actions(c) == ["file_intent_to_file"]
    c.itf = {"date": None, "method": "manual"}
    assert allowed_actions(c) == ["fetch_cfile"]


def test_pass_2_only_after_claims_prep():
    c = CaseState(case_id="c2b", phase="case_prep", cfile_documents=[{"documentId": "x"}])
    assert allowed_actions(c) == ["run_claims_prep"]
    c.face_note = "note"
    assert allowed_actions(c) == ["continue_intake"]


def test_one_handoff_per_wake():
    executed = []

    def execute(action, case):
        executed.append(action)
        case.va_consent, case.phase = "declined", "screening"

    c = CaseState(case_id="c2c", phase="va_sign_in", va_consent="declined")
    Orchestrator(OfflinePolicy(), execute).handle(c, "va_sign_in_declined")
    assert executed == ["start_screening"]  # the wake ends at the handoff, without a wait step


def test_after_escalation_only_the_hand_off():
    c = CaseState(case_id="c3", phase="poa", poa_document_id="doc", escalation="crisis")
    assert allowed_actions(c) == ["hand_off_to_staff"]  # no waiting on a crisis


def test_escalation_is_handed_off_by_rule_even_if_the_model_says_wait():
    class Stubborn:
        name = "dspy"

        def choose(self, case, event, allowed):
            return WAIT, "nah"

    done = []
    c = CaseState(case_id="c3b", phase="intake", escalation="crisis")
    Orchestrator(Stubborn(), lambda a, case: (done.append(a), setattr(case, "phase", "human_handoff"))).handle(c, "x")
    assert done == ["hand_off_to_staff"] and c.decisions[0].policy == "rule"


def test_a_finished_intake_cannot_be_left_waiting():
    c = CaseState(case_id="c3c", phase="intake", poa_document_id="d", poa_submission={"method": "manual"},
                  itf={"date": None}, face_note="note")  # fmt: skip
    c.intake_outcome = Outcome(decision="eligible", fee_pct=30)
    assert allowed_actions(c) == ["send_to_attorney_review"]  # awaiting_veteran is False: no wait
    c.awaiting_veteran = True
    assert WAIT in allowed_actions(c)


def test_non_blocking_concern_does_not_interrupt_a_conversation():
    c = CaseState(case_id="c4", phase="screening", face_note_flags=["something minor"], awaiting_veteran=True)
    allowed = allowed_actions(c)
    assert allowed == ["hand_off_to_staff", WAIT]
    assert OfflinePolicy().choose(c, "x", allowed)[0] == WAIT


class _Pred:
    def __init__(self, action, reason="r"):
        self.action, self.reason = action, reason


def test_dspy_policy_falls_back_when_the_model_picks_something_not_allowed():
    policy = DSPyPolicy(lm=None)
    policy.predict = lambda **kw: _Pred("fetch_cfile")
    c = CaseState(case_id="c5")
    action, reason = policy.choose(c, "case_opened", allowed_actions(c))
    assert action == "request_va_sign_in" and "fallback" in reason


def test_dspy_policy_uses_the_models_choice_and_survives_errors():
    policy = DSPyPolicy(lm=None)
    c = CaseState(
        case_id="c6", phase="intake", face_note="note", face_note_flags=["DOB mismatch"],
        intake_outcome=Outcome(decision="eligible", fee_pct=30),
    )
    policy.predict = lambda **kw: _Pred("hand_off_to_staff", "DOB must be fixed first")
    assert policy.choose(c, "e", allowed_actions(c)) == (
        "hand_off_to_staff",
        "DOB must be fixed first",
    )

    def boom(**kw):
        raise RuntimeError("network")

    policy.predict = boom
    action, reason = policy.choose(c, "e", allowed_actions(c))
    assert action == "send_to_attorney_review" and "unavailable" in reason


def test_loop_logs_every_decision():
    executed = []

    def execute(action, case):
        executed.append(action)
        case.phase, case.va_consent = "va_sign_in", "pending"

    c = CaseState(case_id="c7")
    Orchestrator(OfflinePolicy(), execute).handle(c, "case_opened")
    assert executed == ["request_va_sign_in"]
    assert [d.action for d in c.decisions] == ["request_va_sign_in", WAIT]
