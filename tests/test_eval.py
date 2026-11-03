"""The case eval (intake_eval/) on the runtime, with the scripted fake LM and a scripted veteran:
whole runs scored per agent and reported, the three conditions, the critical errors, the cost
guard and the key check (D7)."""

import copy
import time

import pytest
from intake_fixtures import SCREEN_STEPS

from agent import cli
from agent.casefile import Answer, CaseFile
from agent.cfile.facts import CfileFacts
from agent.intake import checklist
from agent.personas import get_persona
from agent.runtime import make_runtime
from agent.scripted.kb import FaqKB
from agent.scripted.lm import call, final, pause
from agent.scripted.prep import prep_steps
from intake_eval import evaluate
from intake_eval.runner import CaseRun, run_case
from intake_eval.scoring import score_run

PASS1 = {"finished": "pass 1: 21-22a and ITF filed, fee agreement faxed"}
WRONG = {"heard_about": "a TV ad"}  # the one answer the scripted veteran gets wrong


class Veteran:
    """Answers from the persona's key. It also scripts intake's next turn: pass 1 from a fixed
    list, pass 2 by recording up to 7 of the checklist's missing items per turn (intake's limit is
    8 steps), and queues the orchestrator's wake once that batch empties the checklist."""

    def __init__(self, persona, lm, rt, pass1_replies):
        self.p, self.lm, self.rt, self.replies, self.case_id = persona, lm, rt, list(pass1_replies), None
        orig = rt.open_case

        def open_case(*a, **kw):  # the runner opens the case: remember its id
            case = orig(*a, **kw)
            self.case_id = case.case_id
            return case

        rt.open_case = open_case
        self.calls, self.cost = 0, 0.0

    def respond(self, text: str) -> str:
        self.calls += 1
        if self.replies:
            return self.replies.pop(0)
        case = self.rt.store.get_case(self.case_id)
        batch = [i.id for i in checklist.missing(case, "pass2")][:7]
        self.lm.turn("intake", *[call("record_answer", q=q, a=a or "not sure", unknown=a is None)
                                 for q, a in ((q, self.answer(q)) for q in batch)], final(reply="Next?"))  # fmt: skip
        trial = copy.deepcopy(case)
        for q in batch:
            a = self.answer(q)
            trial.answers[q] = Answer(value=None if a is None else checklist.parse(q, a), source="x", unknown=a is None)
        checklist.refresh(trial)
        if not checklist.missing(trial, "pass2"):
            self.lm.turn("orchestrator", final())
        return "Here you go."

    def answer(self, qid: str) -> str | None:
        if qid.startswith("narrative:"):
            _, cond, pid = qid.split(":")
            return self.p.stories.get(cond, {}).get(pid)
        if qid in WRONG:
            return WRONG[qid]
        value = getattr(self.p.truth, checklist.BANK.by_id[qid].field)
        if value is None:
            return None
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return ", ".join(map(str, value)) or "None"
        return str(value)


def script_eligible(lm, persona_id: str, prep_turn=(), orchestrator_goal="Pass 2: ask only the gaps."):
    """A clean pass 1 (screen, secure form, 21-22a, fee agreement, countersign, filing), claims
    prep's passing turn, and the handoff to pass 2. Returns the veteran's pass-1 replies."""
    lm.turn("orchestrator", call("run_intake", goal="Pass 1: screen, sign, file."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    lm.turn("intake", *SCREEN_STEPS, call("request_secure_info", fields=["first_name", "last_name", "ssn",
            "date_of_birth", "branch", "address.line1", "address.city", "address.state", "address.zip",
            "phone", "email"], purpose="For the 21-22a."), final(reply="Please fill in the secure form."))  # fmt: skip
    lm.turn("intake", call("fill_pdf", form="21-22a", fields={"authorize_7332_records": True,
            "authorize_address_change": True}), final(reply="Here is your 21-22a. Does it look right?"))  # fmt: skip
    lm.turn("intake", call("get_signature", form="21-22a"), final(reply="Please draw your signature."))
    lm.turn("intake", call("get_signature", form="21-22a"), final(reply="Click Sign when you're ready."))
    lm.turn("intake", call("fill_pdf", form="fee_agreement", fields={}), final(reply="Here's the fee agreement. Agree?"))
    lm.turn("intake", call("get_signature", form="fee_agreement"), final(reply="Click Sign to sign it."))
    lm.turn("intake", final(reply="Our attorney is reviewing both documents now."))
    lm.turn("intake", call("submit_va", form="21-22a"), call("submit_va", form="itf"),
            call("efax_ogc", doc="fee_agreement"), final(reply="Filed with VA!", result=PASS1))  # fmt: skip
    lm.turn("orchestrator", call("run_prep", goal="Pull and read the C-file, prefill, face note."), final())
    lm.turn("claims_prep", *prep_turn, *prep_steps(persona_id), final(result={"finished": "face note verified"}))
    lm.turn("orchestrator", call("run_intake", goal=orchestrator_goal), final())
    lm.turn("intake", final(reply="Now a few more questions about your claim."))
    return ["Yes. Army 2004-06 to 2010-05, honorable. Never filed. No lawyer.", "Yes, it's right.", "Yes, I agree."]


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "RESULTS_DIR", tmp_path / "results")
    return tmp_path / "results"


def test_an_eligible_case_runs_end_to_end_and_is_scored_per_agent(rt, lm, results):
    persona = get_persona("baseline_clean")
    vet = Veteran(persona, lm, rt, script_eligible(lm, persona.id))
    out, (s,) = evaluate.run_eval([persona], ["cfile"], lambda d: rt, lambda p: vet, run_name="e2e")

    assert (s.end_state, s.expected_end, s.scenario_pass, s.completed) == ("attorney_review", "attorney_review", True, True)
    assert s.critical_errors == []
    # intake: the screening six and every pass-2 question settled in chat, mos from the C-file
    assert s.turns_to_signed_poa == 5  # first message, secure form, "looks right", signature, Sign
    assert s.fee_got == s.fee_expected == 30
    case = rt.store.get_case(vet.case_id)
    from_vet = [k for k, a in case.answers.items() if k in checklist.BANK.by_id and a.source.startswith("veteran")]
    assert s.structured_questions == len(from_vet) and s.cfile_prefilled == 1 and case.answers["mos"].source.startswith("C-file")
    assert s.prefill_share == pytest.approx(1 / (len(from_vet) + 1))
    assert s.clarifications == 0 and s.narrative_answers == 15
    status = {f.field: f.status for f in s.fields}
    assert status["heard_about"] == "wrong" and status["is_veteran"] == status["service_periods"] == "correct"
    scored = [f for f in s.fields if f.status != "n/a"]
    assert {f.status for f in scored} == {"correct", "wrong"}
    assert s.field_accuracy == pytest.approx((len(scored) - 1) / len(scored))
    # orchestrator and claims prep
    assert s.handoffs == ["intake", "claims_prep", "intake"] and s.refused == {} and s.flag_decision_correct is None
    assert (s.facenote_line_accuracy, s.verify_passed, s.citation_precision) == (1.0, True, 1.0)
    assert all(s.facenote_checks.values())
    # cost per agent, from the traces
    assert {"orchestrator", "intake", "claims_prep", "simulator"} <= set(s.by_agent)
    assert s.by_agent["intake"]["calls"] > 0 and s.cost_usd > 0
    report = (out / "report.md").read_text()
    assert f"| cfile | **{s.structured_questions}.0** | 1/1 | 0 of 1 |" in report
    assert "structured questions settled in chat" in report and "## Claims prep" in report and "## Cost and latency per agent" in report
    assert (out / "summary.json").exists() and (out / "transcripts" / "cfile" / "baseline_clean.md").exists()


def test_a_stop_rule_case_closes_and_scores_clean(rt, lm, results):
    persona = get_persona("not_a_veteran")
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    lm.turn("intake", call("record_answer", q="is_veteran", a="No"), final(reply="Sorry, we can only help veterans."))
    lm.turn("orchestrator", final())
    vet = Veteran(persona, lm, rt, ["No, I never served."])
    _, (s,) = evaluate.run_eval([persona], ["ask_no_probes"], lambda d: rt, lambda p: vet, run_name="stop")
    assert (s.end_state, s.scenario_pass, s.critical_errors) == ("closed", True, [])
    assert [(f.field, f.status) for f in s.fields if f.status != "n/a"] == [("is_veteran", "correct")]
    assert s.facenote_line_accuracy is None and s.turns_to_signed_poa is None


class UntilFlagged:
    """A pause gate for claims prep that opens once support has flagged something on the case."""

    def __init__(self, rt, vet):
        self.rt, self.vet = rt, vet

    def wait(self, timeout):
        end = time.monotonic() + timeout
        while not self.rt.store.events(self.vet.case_id, types=("support_flag",)):
            if time.monotonic() > end:
                return False
            time.sleep(0.01)
        return True


def test_the_orchestrator_scenario_flags_a_new_condition_during_prep(rt, lm, results):
    persona = get_persona("new_condition_during_prep")
    vet = Veteran(persona, lm, rt, [])
    vet.replies = script_eligible(lm, persona.id, prep_turn=[pause(UntilFlagged(rt, vet))],
                                  orchestrator_goal="Pass 2: ask only the gaps; also ask about the new condition: sleep apnea")  # fmt: skip
    lm.turn("support", call("flag_orchestrator", kind="new_condition", text="sleep apnea"),
            final(reply="I've passed that to the team."))  # fmt: skip
    _, (s,) = evaluate.run_eval([persona], ["cfile"], lambda d: rt, lambda p: vet, run_name="flag")
    assert s.flag_decisions == ["reopen_intake"] and s.flag_decision_correct is True
    assert s.scenario_pass and s.critical_errors == []
    assert {f.field: f.status for f in s.fields}["claim_conditions"] == "correct"


# ------------------------------------------------------------------------------ conditions


def test_ask_no_probes_leaves_the_verification_probes_out():
    case = CaseFile(case_id="c", answers={"is_veteran": Answer(value=True, source="x"),
                                          "filed_before": Answer(value=False, source="x")})  # fmt: skip
    probes = {"other_service_periods", "prior_claim_probe"}
    assert probes <= {i.id for i in checklist.missing(case, "screen")}
    case.eval_condition = "ask_no_probes"
    assert not probes & {i.id for i in checklist.missing(case, "screen")}


def test_without_cfile_prefill_nothing_is_written():
    from agent.claims_prep import prefill

    case = CaseFile(case_id="c", stage=4, eval_condition="ask",
                    answers={"filed_before": Answer(value=False, source="veteran")})  # fmt: skip
    out = prefill.apply(case, ["filed_before", "mos"], CfileFacts(mos=["88M"]), {})
    assert out == {"skipped": ["filed_before", "mos"]} and case.prep.prefill_done
    assert set(case.answers) == {"filed_before"} and case.conflicts == []


# ------------------------------------------------------------------------------ critical errors


def _scored(rt, persona_id: str, case: CaseFile, events=()) -> list[str]:
    rt.store.create_case(case)
    for type, data, actor in events:
        rt.store.append_event(case.case_id, type, data, actor=actor)
    return score_run(get_persona(persona_id), CaseRun(persona_id, "cfile", rt, case.case_id)).critical_errors


def _screened(**answers) -> dict[str, Answer]:
    base = {"is_veteran": "Yes", "service_periods": "Army, active duty, 2004-06 to 2010-05, honorable",
            "other_service_periods": "No", "filed_before": "No", "prior_claim_probe": "No", "prior_attorney": "No"}  # fmt: skip
    base.update(answers)
    return {q: Answer(value=checklist.parse(q, a), source="veteran") for q, a in base.items()}


def test_a_missed_second_service_period_is_critical(rt):
    errors = _scored(rt, "two_service_periods", CaseFile(case_id="c", stage=2, answers=_screened(
        service_periods="Army, active duty, 1990-06 to 1994-06, honorable")))  # fmt: skip
    assert "service periods: expected 2, collected 1" in errors


def test_a_missed_prior_claim_is_critical(rt):
    assert "missed a prior VA claim" in _scored(rt, "forgot_prior_claim", CaseFile(case_id="c", stage=2, answers=_screened()))


def test_a_wrong_stop_decision_is_critical(rt):
    assert "stop rule: expected not_veteran, got none" in _scored(
        rt, "not_a_veteran", CaseFile(case_id="a", stage=2, answers=_screened()))  # fmt: skip
    rated = CaseFile(case_id="b", stage=1, side_state="closed", answers=_screened(),
                     stop={"rule": "rated_100", "reason": "r"})  # fmt: skip
    errors = _scored(rt, "baseline_clean", rated)
    assert "stop rule: expected none, got rated_100" in errors and "case ended in closed, expected attorney_review" in errors


def test_a_missed_crisis_escalation_and_an_ignored_flag_are_critical(rt):
    parked = CaseFile(case_id="a", stage=4, side_state="needs_human", answers=_screened())
    assert "missed a crisis escalation" in _scored(rt, "crisis_disclosure", parked)
    for cid, actor, missed in (("m", "orchestrator", True), ("r", "rule", False)):  # only the rule's escalation counts
        case = parked.model_copy(update={"case_id": cid})
        errors = _scored(rt, "crisis_disclosure", case, events=[("escalated", {"reason": "crisis"}, actor)])
        assert ("missed a crisis escalation" in errors) is missed
    flagged = CaseFile(case_id="b", stage=5, answers=_screened())
    errors = _scored(rt, "new_condition_during_prep", flagged, events=[
        ("support_flag", {"kind": "new_condition", "text": "sleep apnea"}, "support"),
        ("task_created", {"text": "Ask the attorney about sleep apnea"}, "orchestrator")])  # fmt: skip
    assert "flag decision: expected reopen_intake, got ['staff_task']" in errors


# ------------------------------------------------------------------------------ cost and key


def test_max_cost_stops_the_run_and_the_eval(tmp_path, lm, results):
    rt = make_runtime(tmp_path / "a", lm, kb=FaqKB())
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    personas = [get_persona("baseline_clean"), get_persona("not_a_veteran")]
    vet = Veteran(personas[0], lm, rt, [])
    _, scores = evaluate.run_eval(personas, ["cfile"], lambda d: rt, lambda p: vet, max_cost=1e-9)
    assert len(scores) == 1 and not scores[0].completed and vet.calls == 0
    assert "Stopped early" in (results / next(results.iterdir()).name / "report.md").read_text()
    assert lm.unused() == {}


def test_a_run_that_cannot_start_is_scored_and_the_eval_goes_on(results):
    def broken(data_dir):
        raise OSError("disk full")

    _, scores = evaluate.run_eval([get_persona("baseline_clean"), get_persona("rated_100")], ["ask"], broken, lambda p: None)
    assert [(s.end_state, s.critical_errors) for s in scores] == [("crashed", ["run crashed: OSError"])] * 2


def test_a_veteran_that_keeps_failing_ends_the_run_as_given_up(rt, lm):
    class Mute:
        calls, cost = 0, 0.0

        def respond(self, text):
            raise ValueError("unparseable")

    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    run = run_case(get_persona("baseline_clean"), "cfile", lambda: rt, Mute())
    assert run.gave_up and run.model_failures == 3 and not run.completed
    assert "stopped after repeated model failures (3)" in score_run(get_persona("baseline_clean"), run).critical_errors


@pytest.mark.parametrize("argv", [["eval"], ["simulate", "--persona", "baseline_clean"], ["support-eval"]])
def test_live_commands_refuse_to_run_without_the_key(argv):
    with pytest.raises(SystemExit) as exc:  # conftest sets OPENROUTER_API_KEY to ""
        cli.main(argv)
    assert "OPENROUTER_API_KEY" in str(exc.value)


@pytest.mark.parametrize("argv", [["eval", "--max-cost", "1"], ["simulate", "--max-cost", "1"],
                                  ["support-eval", "--max-cost", "1"]])  # fmt: skip
def test_max_cost_is_refused_for_a_model_without_a_price(argv, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("DSPY_MODEL", "openrouter/some/unpriced-model")
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert "--max-cost can't be enforced" in str(exc.value) and "unpriced-model" in str(exc.value)
    monkeypatch.delenv("DSPY_MODEL")
    cli.check_prices(1.0)  # the default models are priced
    monkeypatch.setenv("QA_MODEL", "unpriced/qa")
    cli.check_prices(None)  # without --max-cost: a warning, not a refusal
    assert "unpriced/qa" in capsys.readouterr().err


def test_the_dspy_simulator_replies_in_character_and_counts_its_calls():
    from dspy.utils.dummies import DummyLM

    from intake_eval.simulator import DSPySimulator

    sim = DSPySimulator(get_persona("two_service_periods"), DummyLM([{"reply": "Army, 1990 to 1994."}]))
    assert "ONLY your first service period" in sim.brief and "Dale" in sim.brief
    assert sim.respond("When did you serve?") == "Army, 1990 to 1994." and sim.calls == 1


def test_facenote_mos_check_ignores_case_and_spacing():
    from intake_eval.scoring import facenote_checks

    want = CfileFacts(mos=["88M Motor Transport Operator"])
    assert facenote_checks(CfileFacts(mos=["88M  MOTOR TRANSPORT OPERATOR"]), want)["mos"]
    assert not facenote_checks(CfileFacts(mos=["11B Infantryman"]), want)["mos"]
