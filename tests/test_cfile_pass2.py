"""Claims prep before intake pass 2: what the C-file settles, and what it contradicts."""

from agent.personas import get_persona
from intake_eval.runner import run_case
from intake_eval.scoring import score_run


def _run(pid, cond, tmp_path):
    p = get_persona(pid)
    run = run_case(p, cond, data_dir=tmp_path)
    return run, score_run(p, run)


def test_the_cfile_corrects_a_wrong_va_record_before_pass_2(tmp_path):
    run, score = _run("va_record_wrong_discharge", "fetch", tmp_path)
    assert run.session.intake.record.service_periods[0].discharge == "honorable"
    assert run.session.intake.record.provenance["service_periods"].startswith("cfile+")
    assert any("DD-214" in t.text for t in run.case.tasks)  # staff still see what changed
    assert score.critical_errors == []


def test_without_va_sign_in_the_cfile_catches_a_forgotten_claim(tmp_path):
    run, score = _run("forgot_prior_claim", "cfile", tmp_path)
    assert score.critical_errors == []
    assert run.session.intake.record.filed_before is True


def test_confirm_mode_asks_the_veteran_about_conflicts(tmp_path):
    run, _ = _run("va_record_wrong_discharge", "fetch_confirm", tmp_path)
    asked = [t["text"] for t in run.transcript if t["role"] == "agent"]
    assert any("Your VA claims file shows something different" in t for t in asked)
    assert run.session.intake.record.cfile_discrepancy_answer


def test_cfile_off_leaves_intake_alone_but_tells_staff(tmp_path):
    run, _ = _run("va_record_wrong_discharge", "ask", tmp_path)
    assert run.case.cfile_prefilled == []
    assert "cfile" not in "".join(run.session.intake.record.provenance.values())


def test_cfile_prefills_pass_2_questions(tmp_path):
    run, _ = _run("recent_decision", "cfile", tmp_path)
    assert "mos" in run.case.cfile_prefilled
    assert "mos" not in run.session.intake.asked  # not asked in chat


def test_pass_2_comes_after_claims_prep(tmp_path):
    run, _ = _run("baseline_clean", "fetch_confirm", tmp_path)
    actions = [d.action for d in run.case.decisions if d.action != "wait"]
    assert actions.index("run_claims_prep") < actions.index("continue_intake")
    assert actions.index("request_attorney_signoff") < actions.index("submit_poa_to_va")
    assert actions.index("file_intent_to_file") < actions.index("fetch_cfile")
