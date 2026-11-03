"""Support flags decided by the orchestrator, and the stops that must not lose a filing."""

from agent.intake.controller import AgentConfig
from agent.personas import get_persona
from agent.session import CaseSession
from intake_eval.runner import run_case


def _parked(tmp_path, pid="baseline_clean"):
    return run_case(get_persona(pid), "cfile", data_dir=tmp_path).session


def test_a_new_condition_reopens_intake_and_returns_to_attorney_review(tmp_path):
    s = _parked(tmp_path)
    assert s.case.phase == "attorney_review"
    turn = s.message("I also want to claim my knees.")
    assert s.case.decisions[-1].action == "reopen_intake_for_new_condition"
    assert "Which condition" in turn.messages[-1] and s.case.phase == "intake"
    s.message("My knees.")
    while s.waiting_for_chat:
        s.message("It's bad most days.")
    assert s.case.phase == "attorney_review"
    assert len(s.intake.record.claim_conditions) == 2 and s.case.open_flags == []


def test_contact_changes_and_complaints_become_staff_tasks(tmp_path):
    s = _parked(tmp_path)
    s.message("I moved last week, my new address is 12 Oak St, Tulsa.")
    assert "pass_flags_to_staff" in [d.action for d in s.case.decisions[-2:]] and s.case.open_flags == []
    assert "contact change" in s.case.tasks[-1].text and s.case.phase == "attorney_review"
    s.message("This is ridiculous, nobody has called me in two weeks.")
    assert s.case.tasks[-1].kind == "handoff"


def test_withdrawing_before_the_countersign_stops_the_filing(tmp_path):
    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path,
                    agent_config=AgentConfig(records_mode="ask", cfile_mode="confirm"))  # fmt: skip
    run = run_case(get_persona("baseline_clean"), "cfile", data_dir=tmp_path / "x")
    assert run.case.poa_submission  # (the normal path files)
    from intake_eval.runner import act_on_card, secure_form_values  # noqa: F401
    from intake_eval.simulator import OfflineSimulator

    sim, cards = OfflineSimulator(s.persona), list(s.start().cards)
    while s.case.phase != "attorney_signoff":
        if cards:
            turn, _ = act_on_card(s, s.persona, cards.pop(0), "ask")
            cards += turn.cards if turn else []
        else:
            cards += s.message(sim.respond("", s.pending)).cards
    s.message("I want to cancel my power of attorney.")
    assert s.case.phase == "human_handoff" and s.case.poa_submission is None
    s.ui_event("attorney_countersigned")  # a stale staff card does nothing now
    assert s.case.poa_submission is None


def test_a_stop_found_after_filing_goes_to_a_person_not_closed(tmp_path):
    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path)
    s.case.phase, s.case.poa_document_id, s.case.poa_countersigned_at = "intake", "d", "t"
    s.case.poa_submission, s.case.itf = {"method": "manual"}, {"date": None, "method": "manual"}
    s.intake.record.rating_pct = 100
    from agent.intake.schema import Outcome

    s.case.intake_outcome = Outcome(decision="rated_100")
    s._event("intake_stopped")
    assert s.case.phase == "human_handoff"
    assert any("withdraw" in t.text for t in s.case.tasks)


def test_claims_prep_survives_a_free_text_service_date(tmp_path):
    from agent.cfile.facts import CfileFacts
    from agent.cfile.reconcile import reconcile
    from agent.intake.schema import IntakeRecord, ServicePeriod

    record = IntakeRecord(service_periods=[ServicePeriod(branch="army", start="March 1998", end="2002")])
    facts = CfileFacts(service_periods=[ServicePeriod(branch="army", start="1998-03", end="2002-01", discharge="honorable")])
    assert reconcile(record, facts) == []  # same branch, the year still matches


def test_the_firms_own_21_22a_is_not_a_prior_representative():
    from agent.cfile.facts import CfileFacts, PriorRep
    from agent.cfile.reconcile import without_firm

    facts = CfileFacts(prior_reps=[PriorRep(name="Attorney 1, Law Firm", kind="attorney", signed="2026-11-03"),
                                   PriorRep(name="Jane Roe", kind="agent", signed="2015-01-01")])  # fmt: skip
    kept = without_firm(facts, {"firm_name": "Law Firm", "first_name": "Attorney", "last_name": "1"})
    assert [r.name for r in kept.prior_reps] == ["Jane Roe"]


def test_a_failed_face_note_is_a_critical_error(tmp_path, monkeypatch):
    import agent.session as session_mod
    from intake_eval.scoring import score_run

    def boom(*a, **kw):
        raise ValueError("template")

    monkeypatch.setattr(session_mod, "render", boom)
    p = get_persona("baseline_clean")
    run = run_case(p, "cfile", data_dir=tmp_path)
    assert "face note not generated" in score_run(p, run).critical_errors
