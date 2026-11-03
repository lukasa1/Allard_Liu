"""Whole cases through CaseSession (offline), and the eval's headline result as a regression test."""

import json

import pytest

from agent.intake.schema import Outcome
from agent.personas import get_persona, load_personas
from intake_eval.runner import CONDITIONS, run_case
from intake_eval.scoring import END_PHASE, score_run


@pytest.mark.parametrize("persona", load_personas(), ids=lambda p: p.id)
def test_every_persona_ends_in_the_right_place(persona, tmp_path):
    run = run_case(persona, "fetch_confirm", data_dir=tmp_path)
    assert not run.hit_step_limit
    assert run.case.phase == END_PHASE[persona.expected_decision]
    assert score_run(persona, run).critical_errors == []


def test_eligible_case_produces_signed_poa_itf_and_face_note(tmp_path):
    run = run_case(get_persona("recent_decision"), "fetch_confirm", data_dir=tmp_path)
    case = run.case
    assert (
        case.poa_signed and case.poa_submission["method"] == "lighthouse_stub" and case.itf["date"]
    )
    assert case.face_note.startswith("FA 30%; No prior rep")
    assert any(t.kind == "deadline" and t.due == "2027-03-13" for t in case.tasks)
    actions = [d.action for d in case.decisions if d.action != "wait"]
    assert actions == [
        "request_va_sign_in", "fetch_va_records", "start_screening", "start_poa", "request_attorney_signoff",
        "submit_poa_to_va", "file_intent_to_file", "fetch_cfile", "run_claims_prep", "continue_intake",
        "send_to_attorney_review",
    ]  # fmt: skip


def test_no_raw_pii_in_the_case_file_or_intake_transcript(tmp_path):
    p = get_persona("baseline_clean")
    run = run_case(p, "fetch_confirm", data_dir=tmp_path)
    saved = json.loads((tmp_path / "cases" / f"{run.case.case_id}.json").read_text())
    digits = p.identity["ssn"].replace("-", "")
    face_note = saved.pop("face_note")
    rest = json.dumps(saved)
    assert p.identity["ssn"] not in rest + face_note and digits not in rest + face_note
    assert p.identity["dob"] not in rest  # only the face note shows the DOB (the firm's template)
    assert saved["cfile_facts"]["dob"].startswith("**/**/")
    assert p.identity["ssn"] not in json.dumps(run.session.intake.transcript)


def test_typed_ssn_is_redacted_before_the_agent(tmp_path):
    from agent.session import CaseSession

    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path)
    s.start()
    s.ui_event("va_sign_in_declined")
    turn = s.message("sure, my social is 123-45-6789")
    assert turn.redacted and "hidden that number" in turn.messages[0]
    assert "123-45-6789" not in json.dumps(s.intake.transcript)


def test_ablation_headline(tmp_path):
    """The result the report leads with: VA's records miss an unlisted Reserve period, and the
    C-file (read before pass 2) catches it even when the records are trusted; asking without
    probes and without the C-file misses more."""

    def critical(pid, cond):
        return score_run(
            get_persona(pid), run_case(get_persona(pid), cond, data_dir=tmp_path)
        ).critical_errors

    assert critical("reserve_not_in_records", "fetch") == []  # the C-file's DD-214 adds it
    assert critical("reserve_not_in_records", "fetch_confirm") == []
    assert critical("two_service_periods", "cfile") == []
    assert critical("two_service_periods", "ask_no_probes") == [
        "service periods: expected 2, collected 1"
    ]
    assert critical("forgot_prior_claim", "ask_no_probes") == ["missed a prior VA claim"]
    assert critical("forgot_prior_claim", "fetch") == []
    assert set(CONDITIONS) == {"ask_no_probes", "ask", "cfile", "fetch", "fetch_confirm"}


def test_offline_poa_review_doesnt_take_a_no_as_approval(svc):
    from agent.poa import OfflinePoaStep

    step = OfflinePoaStep(svc)
    step.waiting_for = "review"
    step.message("No, my address is not correct")
    assert not step.reviewed
    step.message("Looks good, no changes needed")
    assert step.reviewed


def test_crisis_during_the_poa_step_is_scored_as_an_escalation(tmp_path):
    from intake_eval.simulator import OfflineSimulator

    class Discloses(OfflineSimulator):
        def respond(self, text, pending):
            return "Honestly some days I don't want to live anymore." if pending == "item20" else super().respond(text, pending)

    p = get_persona("baseline_clean")
    run = run_case(p, "fetch_confirm", simulator=Discloses(p), data_dir=tmp_path)
    assert run.case.phase == "human_handoff" and run.case.intake_outcome.decision == "escalated"


def test_no_cfile_source_hands_off_instead_of_stalling(tmp_path):
    from agent.lighthouse import RecordedLighthouse
    from agent.session import CaseSession

    s = CaseSession(provider="offline", persona=None, lighthouse=RecordedLighthouse(tmp_path), data_dir=tmp_path)
    s.case.phase, s.case.poa_countersigned_at = "attorney_signoff", "t"
    s.case.poa_document_id, s.case.poa_submission = "d", {"method": "manual"}
    s.case.itf = {"date": None, "method": "manual"}
    s._event("filed")  # no C-file source: pass 2 runs without it
    assert s.case.cfile_manual and s.case.phase == "intake"
    s.intake.record.claim_conditions = ["back"]
    s.case.intake_outcome = Outcome(decision="eligible", fee_pct=30)
    s.case.awaiting_veteran = False  # (pass 2 finished)
    s._event("intake_complete")  # then a person must pull the C-file: no stalling
    assert s.case.phase == "human_handoff"


def _at_item20(tmp_path):
    from agent.session import CaseSession
    from intake_eval.runner import secure_form_values
    from intake_eval.simulator import OfflineSimulator

    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path)
    sim = OfflineSimulator(s.persona)
    s.start()
    s.ui_event("va_sign_in", icn=s.persona.icn)
    while s.case.phase == "screening":
        s.message(sim.respond("", s.pending))
    req = s.svc.pending_requests()[0]
    s.svc.complete_capture_request(req["id"], secure_form_values(s.persona, req["fields"]))
    s.ui_event("secure_form_submitted")
    assert s.poa.waiting_for == "item20"
    return s


def test_questions_and_requests_for_a_person_work_in_the_poa_step(tmp_path):
    s = _at_item20(tmp_path)
    turn = s.message("How much do you charge?")
    assert "past-due benefits" in turn.messages[0] and turn.messages[1].startswith("Back to the form")
    turn = s.message("Can I talk to a real person?")
    assert s.case.phase == "human_handoff" and "person on our team" in turn.messages[0]


def test_a_reply_that_is_only_an_id_number_is_not_stored(tmp_path):
    from agent.session import CaseSession

    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path)
    s.start()
    s.ui_event("va_sign_in_declined")
    turn = s.message("123-45-6789")
    assert "hidden that number" in turn.messages[0] and s.intake.pending.key == "is_veteran"
    assert "is_veteran" not in s.intake.status


def test_cards_left_open_after_a_hand_off_do_nothing(tmp_path):
    from intake_eval.runner import act_on_card

    s = _at_item20(tmp_path)
    s.message("I want to talk to a real person")
    turn, note = act_on_card(s, s.persona, {"type": "signature_pad"}, "fetch_confirm")
    assert turn is None and "ignored" in note and not s.svc.vault.has_signature()


def _session_at_poa(tmp_path):
    from agent.session import CaseSession

    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path)
    s.start()
    s.ui_event("va_sign_in_declined")
    for m in ["Yes", "Army, active, from 2004-06 to 2010-05, honorable", "No", "No", "No", "No"]:
        s.message(m)
    assert s.case.phase == "poa"
    return s


def test_declining_the_21_22a_hands_off_instead_of_waiting(tmp_path):
    s = _session_at_poa(tmp_path)
    s.message("I changed my mind, I don't want to sign anything.")
    assert s.case.phase == "human_handoff"
    assert "declined to sign" in s.case.escalation
    assert any(t.kind == "handoff" for t in s.case.tasks)


def test_message_to_a_parked_case_creates_a_task(tmp_path):
    from agent.session import CaseSession

    s = CaseSession(provider="offline", persona=get_persona("not_a_veteran"), data_dir=tmp_path)
    s.start()
    s.ui_event("va_sign_in_declined")
    s.message("No")
    assert s.case.phase == "closed"
    s.message("Wait, I'd like to speak with a person about my husband's claim")
    assert s.case.tasks and s.case.tasks[-1].kind == "handoff"


def test_dob_typed_in_chat_is_hidden(tmp_path):
    s = _session_at_poa(tmp_path)
    turn = s.message("ok, I was born 03/14/1985 if that helps")
    assert turn.redacted
    assert "03/14/1985" not in json.dumps(s.case.model_dump()) + json.dumps(turn.case)


@pytest.mark.parametrize("text", ["No, I don't want this shared", "I changed my mind, yes they can see them", "cancel that, I meant yes"])
def test_item20_answers_are_not_a_refusal_to_sign(tmp_path, text):
    s = _session_at_poa(tmp_path)
    s.ui_event("secure_form_submitted")  # nothing submitted: the step re-asks, still in poa
    s.poa.waiting_for = "item20"
    s.message(text)
    assert s.case.phase == "poa" and s.case.escalation is None
