"""The eval harness survives crashes and model failures, and scores them as failures."""

import json
from collections import Counter
from types import SimpleNamespace

import pytest

from agent.case import Decision
from agent.personas import get_persona
from intake_eval import evaluate, runner
from intake_eval.runner import run_case
from intake_eval.scoring import Score, process_metrics, score_run
from intake_eval.simulator import MID_INTAKE_QUESTION, OfflineSimulator


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "RESULTS_DIR", tmp_path)
    return tmp_path


class _Refuses:
    def respond(self, *_):
        raise ValueError("model refused")


def test_one_crashing_run_does_not_abort_the_eval(results, monkeypatch):
    real = runner.CaseSession.message

    def boom(self, text):
        if self.persona.id == "baseline_clean":
            raise KeyError("boom")
        return real(self, text)

    monkeypatch.setattr(runner.CaseSession, "message", boom)
    personas = [get_persona("baseline_clean"), get_persona("rated_100")]
    out, scores = evaluate.run_eval(personas, ["ask"], run_name="crash")
    crashed, ok = scores
    assert crashed.decision == "crashed" and crashed.critical_errors == ["run crashed: KeyError"]
    assert not ok.critical_errors
    assert evaluate.pass_hat_k(scores) == 0.5
    summary = json.loads((out / "summary.json").read_text())
    assert len(summary["scores"]) == 2
    transcript = (out / "transcripts" / "ask" / "baseline_clean.md").read_text()
    assert "Traceback" in transcript and "KeyError: 'boom'" in transcript
    assert "| ask | 2 |" in (out / "report.md").read_text()


def test_a_run_that_cannot_start_is_scored_too(results, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no session")

    monkeypatch.setattr(evaluate, "run_case", broken)
    out, [score] = evaluate.run_eval([get_persona("rated_100")], ["ask"], run_name="nostart")
    assert score.decision == "crashed" and score.error == "RuntimeError"
    assert "RuntimeError: no session" in (out / "transcripts" / "ask" / "rated_100.md").read_text()


def test_simulator_failures_end_the_run_as_a_critical_error(tmp_path):
    p = get_persona("baseline_clean")
    run = run_case(p, "ask", simulator=_Refuses(), data_dir=tmp_path)
    assert run.model_failures == 3 and run.gave_up and not run.crashed
    score = score_run(p, run)
    assert score.model_failures == 3
    assert any("repeated model failures" in e for e in score.critical_errors)


def test_step_limit_is_a_critical_error(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "MAX_STEPS", 3)
    p = get_persona("baseline_clean")
    run = run_case(p, "ask", data_dir=tmp_path)
    assert run.hit_step_limit
    assert any("step limit" in e for e in score_run(p, run).critical_errors)


def test_face_note_failure_is_a_critical_error(tmp_path, monkeypatch):
    import agent.session

    def fail(*a, **k):
        raise ValueError("unparseable date")

    monkeypatch.setattr(agent.session, "extract_cfile", fail)
    p = get_persona("recent_decision")
    run = run_case(p, "fetch_confirm", data_dir=tmp_path)
    score = score_run(p, run)
    assert run.case.cfile_facts is None
    assert score.facenote_accuracy == 0.0 and "face note not generated" in score.critical_errors


def test_trials_with_dspy_turn_the_cache_off_and_vary_rollouts(results, monkeypatch):
    import os

    import dspy

    seen = []

    class FakeLM:
        def __init__(self, rollout_id=None):
            self.rollout_id = rollout_id

        def copy(self, **kw):
            return FakeLM(**kw)

    class Sim:
        def __init__(self):
            self.lm = FakeLM()

    def fake_run_case(persona, condition, provider, simulator, lm):
        seen.append((dspy.cache.enable_disk_cache, dspy.cache.enable_memory_cache,
                     os.environ.get("DSPY_CACHE"), lm.rollout_id, simulator.lm.rollout_id))  # fmt: skip
        raise RuntimeError("stop here")

    monkeypatch.setattr(evaluate, "run_case", fake_run_case)
    monkeypatch.setattr(evaluate.config, "make_lm", lambda role="agent": FakeLM())
    before = dspy.cache
    evaluate.run_eval(
        [get_persona("rated_100")], ["ask"], provider="dspy", run_name="trials",
        make_sim=lambda p: Sim(), trials=2,
    )  # fmt: skip
    assert seen == [(False, False, "0", 0, 0), (False, False, "0", 1, 1)]
    assert dspy.cache is before  # restored afterwards


# ---------------------------------------------------------------- metrics (no whole-case flow)


def _score(condition="ask", **kw) -> Score:
    base = {
        "persona_id": "p", "condition": condition, "expected_decision": "eligible",
        "decision": "eligible", "decision_correct": True, "end_phase": "attorney_review",
        "end_phase_correct": True, "fee_expected": 30, "fee_got": 30, "flags_expected": [],
        "flags_got": [], "critical_errors": [],
    }  # fmt: skip
    return Score(**{**base, **kw})


def _fake_run(**case_kw):
    record = SimpleNamespace(
        qa_log=[{"question": "q", "answer": "a"}], questions_for_team=["x", "y"]
    )
    intake = SimpleNamespace(
        asked=Counter({"service_periods": 2, "filed_before": 1, "narrative:tinnitus:h02": 3}),
        record=record,
    )
    return SimpleNamespace(session=SimpleNamespace(intake=intake), case=SimpleNamespace(**case_kw))


def test_process_metrics_split_questions_and_read_usage_and_decisions():
    decisions = [
        Decision(event="e", action="wait", reason="r", allowed=["wait"], policy="offline"),
        Decision(event="e", action="a", reason="r", allowed=["a", "b"], policy="dspy"),
        Decision(event="e", action="a", reason="[model chose c] fell back", allowed=["a", "b"], policy="dspy_fallback"),
        Decision(event="e", action="handoff", reason="crisis", allowed=["handoff"], policy="rule"),
    ]  # fmt: skip
    run = _fake_run(
        usage={"lm_calls": 4, "input_tokens": 1000, "output_tokens": 200, "cost_usd": 0.012},
        cfile_prefilled=["filed_before", "rating_pct"],
        decisions=decisions,
    )
    run.poa_chat_turns, run.turns_to_signed_poa = 3, 7
    m = process_metrics(run)
    assert m["structured_questions"] == 3 and m["narrative_prompts"] == 3
    assert m["cfile_prefilled"] == 2 and m["poa_chat_turns"] == 3 and m["turns_to_signed_poa"] == 7
    assert m["veteran_questions_answered"] == 3
    assert (m["lm_calls"], m["input_tokens"], m["output_tokens"], m["cost_usd"]) == (
        4,
        1000,
        200,
        0.012,
    )
    assert m["decisions"] == 4 and m["single_option_decisions"] == 1 and m["wait_only_decisions"] == 1
    assert m["model_decisions"] == 1 and m["fallbacks"] == 1 and m["illegal_choices"] == 1


def test_process_metrics_default_to_zero_when_attributes_are_missing():
    m = process_metrics(_fake_run())  # no usage, cfile_prefilled, decisions or POA counters
    assert m["lm_calls"] == 0 and m["cost_usd"] == 0.0 and m["decisions"] == 0
    assert (
        m["cfile_prefilled"] == 0 and m["poa_chat_turns"] == 0 and m["turns_to_signed_poa"] is None
    )


def test_headline_means_only_completed_runs_and_reports_n():
    scores = [
        _score(structured_questions=10, field_accuracy=1.0, cost_usd=0.5, lm_calls=5),
        _score(structured_questions=20, field_accuracy=0.5, cost_usd=0.25, lm_calls=3),
        _score(structured_questions=2, error="KeyError", critical_errors=["run crashed: KeyError"]),
        _score(structured_questions=1, gave_up=True, critical_errors=["gave up"]),
        _score(structured_questions=1, hit_step_limit=True, critical_errors=["step limit"]),
    ]
    a = evaluate.aggregate(scores)
    assert a["runs"] == 5 and a["completed_runs"] == 2
    assert a["mean_structured_questions"] == 15.0
    assert a["runs_with_critical_errors"] == 3 and a["runs_gave_up"] == 1
    assert a["total_cost_usd"] == 0.75 and a["mean_lm_calls"] == 8 / 5
    line = evaluate.headline_line("ask", a)
    assert "15.0 structured questions" in line and "n=2/5" in line and "3 of 5 runs" in line
    report = evaluate.render_report("r", "offline", ["ask"], scores, 1)
    assert "| ask | **15.0** | 2/5 | 3 of 5 | 75% |" in report
    for section in ("## Headline: structured questions asked", "## Cost per case", "## Orchestrator",
                    "## POA step and veteran questions"):  # fmt: skip
        assert section in report
    assert "deterministic policy" in report and "cache" in report
    assert "(2, incomplete)" in report  # the crashed run's count is shown but marked


def test_headline_with_no_completed_runs_shows_a_dash():
    a = evaluate.aggregate([_score(error="KeyError")])
    assert a["mean_structured_questions"] is None
    assert "– structured questions" in evaluate.headline_line("ask", a)


def test_offline_simulator_asks_one_question_mid_intake():
    from agent.intake.brains import split_question
    from agent.intake.questions import Ask, QuestionBank

    sim = OfflineSimulator(get_persona("asks_question_mid_intake"))
    questions = [q for q in QuestionBank.load().structured if q.type == "bool"][:5]
    replies = [sim.respond("", Ask(question=q)) for q in questions]
    with_q = [r for r in replies if r.startswith(MID_INTAKE_QUESTION)]
    assert len(with_q) == 1 and replies.index(with_q[0]) == 2  # once, on the third question
    plain = OfflineSimulator(get_persona("baseline_clean"))
    normal = [plain.respond("", Ask(question=q)) for q in questions]
    assert [r for r in replies if r not in with_q] == normal[:2] + normal[3:]
    answer, asked = split_question(with_q[0])  # the intake still sees the normal answer
    assert asked == MID_INTAKE_QUESTION and answer == normal[2]


def test_asks_question_persona_gets_its_question_answered_and_still_scores_clean(tmp_path):
    p = get_persona("asks_question_mid_intake")
    run = run_case(p, "ask", data_dir=tmp_path)
    score = score_run(p, run)
    assert not score.critical_errors, score.critical_errors
    assert score.veteran_questions_answered == 1
    assert score.field_accuracy == 1.0
