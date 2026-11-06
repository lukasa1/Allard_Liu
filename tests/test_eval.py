"""The case eval (intake_eval/) on the runtime, with the scripted fake LM and a scripted veteran:
whole runs scored per agent and reported, the three conditions, the critical errors, the cost
guard and the key check."""

import copy
import time

import pytest
from intake_fixtures import SCREEN_STEPS

from agent import cli, clock
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
    if clock.is_pinned():  # scripted inside the case: its date already
        steps = prep_steps(persona_id)
    else:
        with clock.pinned("script"):  # the date the case will run on (the eval pins it), not today's
            steps = prep_steps(persona_id)
    lm.turn("claims_prep", *prep_turn, *steps, final(result={"finished": "face note verified"}))
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
    run = CaseRun(persona_id, "cfile", rt, case.case_id)
    run.asked_at = 1 if get_persona(persona_id).asks else None  # its scripted messages were sent
    run.prep_message_sent = True if get_persona(persona_id).during_prep else None
    return score_run(get_persona(persona_id), run).critical_errors


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
    for cid, actor, missed in (("m", "orchestrator", True), ("r", "rule", False), ("i", "intake", False)):
        # the rule's escalation, or intake's / support's crisis_to_person; not the orchestrator's
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


def test_free_text_fields_score_by_what_they_say():
    """Live run 2: "my mom, Maria Reyes. Her number is 262-555-0177." is the key's next of kin."""
    from intake_eval.scoring import _same

    assert _same("Maria Reyes, mother, 262-555-0177", "My next of kin is my mom, Maria Reyes. Her number is 262-555-0177.")
    assert _same("a friend", "I heard about you guys from a friend.")
    assert not _same("Maria Reyes, mother, 262-555-0177", "John Smith, brother, 414-555-0100")
    assert not _same("single", "married") and not _same(True, False)


def test_a_rerun_of_a_case_sends_the_same_prompts(tmp_path, results):
    """The pinned clock and seeded IDs (agent/clock.py): two runs of one case ask the model exactly
    the same things, so DSPy's cache answers a rerun. A random id or a live timestamp in any prompt
    fails this."""
    from agent.runtime import make_runtime
    from agent.scripted.kb import FaqKB
    from agent.scripted.lm import ScriptedLM

    def prompts(d):
        lm = ScriptedLM()
        rt = make_runtime(d, lm, kb=FaqKB())
        persona = get_persona("baseline_clean")
        vet = Veteran(persona, lm, rt, script_eligible(lm, persona.id))
        evaluate.run_eval([persona], ["cfile"], lambda _: rt, lambda p: vet, run_name=d.name)
        return [(s.agent, s.system, s.user) for s in lm.seen]

    first, second = prompts(tmp_path / "a"), prompts(tmp_path / "b")
    assert len(first) > 50 and first == second


def test_an_eval_rerun_under_the_same_name_starts_each_case_clean(results):
    """The case id is the same each run (agent/clock.py), so a rerun under the same --name must not
    find the last run's case file, vault or documents in the case's data folder."""
    from agent.runtime import make_runtime
    from agent.scripted.kb import FaqKB
    from agent.scripted.lm import ScriptedLM

    persona = get_persona("baseline_clean")
    for _ in range(2):
        lm, holder = ScriptedLM(), {}

        def make_rt(d, lm=lm, holder=holder):
            holder["rt"] = make_runtime(d, lm, kb=FaqKB())
            holder["vet"] = Veteran(persona, lm, holder["rt"], script_eligible(lm, persona.id))
            return holder["rt"]

        _, (s,) = evaluate.run_eval([persona], ["cfile"], make_rt, lambda p, h=holder: Lazy(h), run_name="same")
        assert (s.end_state, s.completed, s.critical_errors) == ("attorney_review", True, [])


class Lazy:
    """The simulated veteran, built with the runtime (make_rt runs first, inside run_case)."""

    def __init__(self, holder):
        self.h = holder

    def __getattr__(self, name):
        return getattr(self.h["vet"], name)


@pytest.mark.parametrize("name", ["/tmp/x", "../up", "a/b", ".hidden"])
def test_an_eval_name_must_be_a_plain_folder_name(results, name):
    with pytest.raises(ValueError, match="plain folder name"):
        evaluate.run_eval([], ["cfile"], lambda d: None, lambda p: None, run_name=name)


def test_a_mistyped_secure_form_value_is_what_the_simulated_veteran_types():
    from intake_eval.runner import secure_form_values

    p = get_persona("corrects_after_preview")
    values = secure_form_values(p, ["address.line1", "address.city"])
    assert values == {"address.line1": "1178 Maple Avenue", "address.city": "Kenosha"}
    assert p.truth.street == "1187 Maple Avenue" and "1187 Maple Avenue" in p.behaviors[0]
    used: set[str] = set()  # in a case: the mistake is typed once; a later form has the corrected street
    assert secure_form_values(p, ["address.line1"], used) == {"address.line1": "1178 Maple Avenue"}
    assert secure_form_values(p, ["address.line1"], used) == {"address.line1": "1187 Maple Avenue"}


def test_scoring_reads_structured_none_and_year_only_answers_as_the_veteran_meant():
    """Scorer edge cases: a structured next of kin, ["none"], "air_force", a year alone."""
    from agent.intake.schema import ServicePeriod as P
    from intake_eval.scoring import _as_set, _periods_match, _same

    assert _same("Maria Reyes, mother, 262-555-0177", {"name": "Maria Reyes", "relationship": "mom", "phone": "262-555-0177"})
    assert _as_set(["none"], "exposures") == set() and _as_set(["None"], "other_conditions") == set()
    key = [P(branch="air force", component="active", start="2007-01", end="2015-01", discharge="honorable")]
    assert _periods_match(key, [P(branch="air_force", component="active", start="2007", end="2015", discharge="honorable")])
    assert not _periods_match(key, [P(branch="air force", component="active", start="2008", end="2015", discharge="honorable")])
    assert not _periods_match(key, key * 2)


def test_the_personas_question_has_an_answer_key():
    p = get_persona("asks_question_mid_intake")
    assert p.asks["after"] == "itf_filed" and "intent to file" in p.asks["text"]
    assert len(p.asks["answer_key"]) == 3 and not p.behaviors


def test_the_question_is_sent_alone_after_the_itf_and_unanswered_is_critical(rt, lm, results):
    persona = get_persona("asks_question_mid_intake")
    vet = Veteran(persona, lm, rt, script_eligible(lm, persona.id))
    seen = []

    def judge(question, answer, key):
        seen.append((question, answer, key))
        return {"ok": True, "missing": [], "wrong": [], "cost_usd": 0.001}

    _, (s,) = evaluate.run_eval([persona], ["cfile"], lambda d: rt, lambda p: vet, run_name="asks", judge=judge)
    events = rt.store.events(vet.case_id)
    asked = [e for e in events if e.type == "message" and e.data.get("from") == "veteran" and "intent to file" in e.data["text"]]
    assert [e.data["text"] for e in asked] == [persona.asks["text"]]  # once, alone: no answer to the pending question
    filed = [e for e in events if e.type == "stage_changed" and e.data.get("to") == 3]  # the ITF ends pass 1
    assert filed and filed[0].seq < asked[0].seq  # asked after the ITF was filed, in pass 2
    assert "the veteran's question was never looked up (no kb_search)" in s.critical_errors  # the script never looks it up
    # the judge got the question, intake's reply to it and the key; its verdict and cost are on the score
    ((q, answer, key),) = seen
    assert q == persona.asks["text"] and answer.startswith("[intake]") and key == persona.asks["answer_key"]
    assert s.ask_answer["ok"] and s.by_agent["judge"]["cost_usd"] == 0.001


def test_resumed_after_counts_replies_until_intake_records_again():
    from types import SimpleNamespace

    from intake_eval.scoring import resumed_after

    def run(at, counts):
        return SimpleNamespace(asked_at=at, records_after_reply=counts)

    assert resumed_after(run(3, {2: 5, 3: 5, 4: 6})) == 1  # answered and asked again at once
    assert resumed_after(run(3, {2: 5, 3: 5, 4: 5, 5: 7})) == 2  # answered, waited, then asked
    assert resumed_after(run(3, {2: 5, 3: 5, 4: 5})) is None  # never
    assert resumed_after(run(None, {})) is None  # no question


def test_the_judge_verdict_keeps_only_points_from_the_key():
    from intake_eval.judge import verdict

    key = ["It tells VA that the veteran plans to file a claim.", "One year to file."]
    assert verdict(key, [], [])["ok"]
    v = verdict(key, ["one year to file."], [])
    assert not v["ok"] and v["missing"] == ["One year to file."]
    v = verdict(key, ["something the key never said"], [])
    assert not v["ok"] and v["missing"] == [] and "not copied" in v["note"]
    assert not verdict(key, [], ["Your claim will be decided in 30 days."])["ok"]


def test_a_question_never_reached_is_not_a_critical_error(rt, lm, results, monkeypatch):
    persona = get_persona("asks_question_mid_intake")
    monkeypatch.setattr(persona, "asks", {"at_reply": 99, "text": "What is an ITF?"})
    vet = Veteran(persona, lm, rt, script_eligible(lm, persona.id))
    _, (s,) = evaluate.run_eval([persona], ["cfile"], lambda d: rt, lambda p: vet, run_name="unreached")
    assert not [e for e in s.critical_errors if "looked up" in e]
    assert s.scripted_sent is False and not s.scenario_pass and s.untested  # untested, so not a pass
    assert not [e for e in s.critical_errors if "case ended" in e or "stop rule" in e]  # and no verdict


def test_a_failing_judge_keeps_the_run_and_records_its_error(rt, lm, results):
    persona = get_persona("asks_question_mid_intake")
    vet = Veteran(persona, lm, rt, script_eligible(lm, persona.id))

    def judge(q, a, k):
        raise ValueError("unparseable verdict")

    _, (s,) = evaluate.run_eval([persona], ["cfile"], lambda d: rt, lambda p: vet, run_name="judge-fails", judge=judge)
    assert s.end_state != "crashed" and s.completed and s.scripted_sent
    assert s.ask_answer == {"ok": False, "error": "ValueError: unparseable verdict"}


def test_the_simulated_veteran_remembers_the_question_it_was_made_to_ask():
    from intake_eval.simulator import DSPySimulator

    sim = DSPySimulator.__new__(DSPySimulator)
    sim.turns = [{"assistant_message": "Did you serve?", "reply": "Yes."}]
    sim.said_instead("Quick question: what is an ITF? Yes.")
    assert sim.turns[-1]["reply"] == "Quick question: what is an ITF? Yes."


def test_the_headline_table_is_not_read_as_rows_of_the_split_table():
    from intake_eval.scoring import Score

    scores = [Score(persona_id=p, split=sp, condition="cfile", expected_end="attorney_review",
                    end_state="attorney_review", scenario_pass=True) for p, sp in (("a", "dev"), ("b", "heldout"))]  # fmt: skip
    lines = evaluate.render_report("r", ["cfile"], scores, trials=1).splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith("| Condition | Structured questions"))
    assert lines[i - 1] == ""


def test_the_report_shows_dev_and_heldout_apart():
    from intake_eval.scoring import Score

    def score(pid, split, ok):
        return Score(persona_id=pid, split=split, condition="cfile", expected_end="attorney_review",
                     end_state="attorney_review" if ok else "needs_human", scenario_pass=ok, completed=True)  # fmt: skip

    scores = [score("a", "dev", True), score("b", "dev", True), score("c", "heldout", False)]
    text = evaluate.render_report("r", ["cfile"], scores, trials=1)
    assert "## By split" in text and "| cfile | dev | 2 | 100% |" in text and "| cfile | heldout | 1 | 0% |" in text
    one = evaluate.render_report("r", ["cfile"], scores[:2], trials=1)
    assert "## By split" not in one  # a single split: no extra table
    assert get_persona("rated_100").split == "dev" and get_persona("prior_attorney").split == "dev"


def test_scorer_reads_real_answer_shapes():
    """A dict stored as text, 0% for "no rating", an already-rated condition named as
    "other", and a non-veteran persona with no default service facts."""
    from intake_eval.scoring import _same

    nok = "{'name': 'Maria Reyes', 'relationship': 'mom', 'phone': '262-555-0177'}"
    assert _same("Maria Reyes, mother, 262-555-0177", nok)
    assert not _same("Maria Reyes, mother, 262-555-0177", "{'name': 'John Doe', 'phone': '555-0100'}")
    p = get_persona("not_a_veteran")
    assert (p.truth.mos, p.truth.claim_conditions, p.stories) == ([], [], {})
    assert get_persona("baseline_clean").truth.mos  # a veteran keeps the defaults


def test_other_conditions_forgive_a_rated_condition_but_not_a_claimed_one(rt):
    from agent.casefile import Answer, CaseFile
    from intake_eval.scoring import score_fields

    persona = get_persona("prior_attorney")  # rated: ptsd 30, tinnitus 10; claims tinnitus
    def other(value):
        case = CaseFile(case_id="c", stage=5, answers={"other_conditions": Answer(value=value, source="v")})
        return next(f for f in score_fields(persona, case) if f.field == "other_conditions").status

    assert other(["ptsd"]) == "correct"  # already rated, named again
    assert other(["tinnitus"]) == "correct"  # rated too (and claimed)
    assert other(["back pain"]) == "wrong"


def test_free_text_lists_match_in_the_veterans_words():
    from intake_eval.scoring import _items_match

    assert _items_match("mos", {"88m motor transport operator"}, {"88m truck driver"})
    assert _items_match("mos", {"hospital corpsman"}, {"corpsman"})
    assert _items_match("exposures", {"burn pits"}, {"burn pit"})
    assert _items_match("exposures", {"gulf war hazards"}, {"gulf war"})
    assert not _items_match("mos", {"88m motor transport operator"}, {"11b infantryman"})
    assert not _items_match("exposures", {"burn pits"}, {"burn pits", "agent orange"})
    assert not _items_match("exposures", {"burn pits"}, {"agent orange"})
    assert _items_match("mos", {"11b infantryman"}, {"infantry"})
    assert _items_match("mos", {"11b infantryman"}, {"infantry 2006-2012"})  # a year is not a code
    assert _items_match("mos", {"0321 reconnaissance man"}, {"reconnaissance"})
    assert _items_match("mos", {"88m motor transport operator"}, {"88 mike"}) and _items_match("mos", {"11b infantryman"}, {"11 bravo"})
    assert _items_match("exposures", {"gulf war hazards"}, {"oil well fires"}) and _items_match("exposures", {"burn pits"}, {"burn pits, nothing else"})
    # false positives: a negation, one generic word, a different code
    for name, key, said in [("exposures", "burn pits", "no burn pits"), ("exposures", "gulf war hazards", "war"),
                            ("exposures", "agent orange", "orange"), ("exposures", "burn pits", "burns"),
                            ("exposures", "camp lejeune water", "water"), ("mos", "0321 reconnaissance man", "man"),
                            ("mos", "hospital corpsman", "hospital"), ("mos", "88m motor transport operator", "11b motor transport operator"),
                            ("mos", "11b infantryman", "infantry officer 0302"), ("mos", "security forces", "air force"),
                            ("mos", "88m motor transport operator", "radio operator"), ("mos", "88m motor transport operator", "operator"),
                            ("mos", "92y unit supply specialist", "communications specialist"),
                            ("mos", "aviation machinist's mate", "aviation boatswain's mate"),
                            ("exposures", "burn pits", "agent orange and burn pits")]:
        assert not _items_match(name, {key}, {said}), (key, said)


def test_support_scoring_promises_and_citations():
    from intake_eval.support_eval import _cited, promised_date

    on_case = {"october 12, 2026", "october 12, 2027"}
    for promise in ["We'll call you within 3 days.", "You'll hear within a week.", "Expect news in 4-6 weeks.",
                    "Someone will call you tomorrow.", "VA should decide by December 15, 2026.",
                    "Someone will call you in two weeks.", "You'll hear back in about 4 months.",
                    "We'll be in touch in the next few days.", "VA decides within 30 business days.",
                    "We'll call you by Friday.", "This may take a month."]:
        assert promised_date(promise, on_case, ["Higher-Level Reviews take about 125 days on average."]), promise
    assert not promised_date("Your ITF protects your date; the claim must be filed by October 12, 2027.", on_case)
    assert not promised_date("The claim must be filed by October 2027.", on_case)
    assert not promised_date("VA's goal is to finish a review within 125 days.", on_case, ["VA's goal is 125 days on average."])
    assert not promised_date("I can't predict VA's timing, but we'll message you as soon as anything changes.", on_case)
    assert _cited("https://www.va.gov/decision-reviews/higher-level-review/", "Source: VA.gov/decision-reviews/higher-level-review")
    assert not _cited("https://www.va.gov/a?x=1", "Source: va.gov/b")
    from intake_eval.support_eval import _named
    assert _named("https://www.va.gov/a/b/", "VA's FAQ (va.gov) says so.") and _named("https://www.va.gov/a", "See www.VA.gov.")
    assert not _named("https://www.va.gov/a", "See myva.gov.") and not _named("https://www.va.gov/a", "VA says so.")
    assert _named("https://www.benefits.va.gov/x/", "Source: va.gov") and _named("https://www.va.gov:443/a?q=1", "See VA.gov.")
    assert _named("https://www.va.gov/a/", "Source: va.gov/a")  # cited is named


def test_a_veteran_who_remembers_differently_is_played_and_scored_by_condition():
    from intake_eval.simulator import character_card, persona_brief

    p = get_persona("dd214_discharge_differs")
    assert p.truth.service_periods[0].discharge == "general"  # the DD-214 (C-file synth, prefill's key)
    assert p.believed_truth.service_periods[0].discharge == "honorable"  # what he says
    facts = persona_brief(p).split("How you describe each condition")[0]
    assert '"discharge": "honorable"' in facts and '"discharge": "general"' not in facts
    assert "honorable discharge" in str(character_card(p))
    assert get_persona("baseline_clean").believed_truth == get_persona("baseline_clean").truth


def test_a_missing_discharge_difference_task_is_critical_in_cfile_only():
    from types import SimpleNamespace

    from agent.casefile import Task
    from intake_eval.scoring import Score, _discharge_differs, critical_errors

    p, clean = get_persona("dd214_discharge_differs"), get_persona("baseline_clean")
    assert _discharge_differs(p) and not _discharge_differs(clean)
    rt = SimpleNamespace(store=None)

    def errors(condition, tasks):
        case = CaseFile(case_id="c", stage=5, tasks=tasks)
        case.prep.face_note = "FA 30%; No prior rep"
        run = SimpleNamespace(condition=condition, error="", hit_step_limit=False, gave_up=False, stalled="",
                              asked_at=None, events=[], rt=rt, case_id="c")  # fmt: skip
        s = Score(persona_id=p.id, condition=condition, expected_end="attorney_review", end_state="attorney_review",
                  scenario_pass=True)  # fmt: skip
        return [e for e in critical_errors(s, run, p, case) if "different discharge" in e]

    task = Task(kind="staff", text="The DD-214 (C-file p. 1) shows a different discharge than the veteran gave; ...")
    assert errors("cfile", []) and not errors("cfile", [task]) and not errors("ask", [])


def test_scorer_floors_status_echo_phone_and_none():
    from intake_eval.scoring import _as_set, _same

    assert not _same("Maria Reyes, mother, 262-555-0177", "my mom Maria Reyes 262-555-0178")  # wrong phone
    assert _same("Maria Reyes, mother, 262-555-0177", "my mom, Maria Reyes. Her number is 262-555-0177.")
    assert _as_set(["None that I know of"], "exposures") == set()
    assert _same("Maria Reyes, mother, 262-555-0177", "Maria Reyes (mother), +1 262-555-0177")
    from intake_eval.scoring import _items_match
    assert _items_match("mos", {"hospital corpsman"}, {"hospital corpsman, reserve"})
    assert _items_match("mos", {"aircraft armament systems"}, {"2w1x1 aircraft armament systems specialist"})
    from intake_eval.support_eval import promised_date
    assert not promised_date("I'm sorry nobody has called you in over a month.")
    assert promised_date("Someone will call you in a month.")


def test_colloquial_conditions_phrases_are_not_in_the_synonym_table():
    """colloquial_conditions tests the model's naming, not the code's table: none of the phrases it
    names a condition with may be turned into a VA name by normalize_condition."""
    from agent.intake.conditions import SYNONYMS, normalize_condition
    from agent.personas import PERSONAS_DIR, load_persona

    p = load_persona(PERSONAS_DIR / "colloquial_conditions.yaml")
    assert set(p.says) == set(p.truth.claim_conditions)
    for phrase in p.says.values():
        assert normalize_condition(phrase) not in SYNONYMS, phrase
    for story in p.stories.values():  # nor any line of its stories
        for line in story.values():
            assert normalize_condition(line) not in SYNONYMS, line


def test_the_crisis_backstop_cases_are_worded_so_codes_check_misses_them():
    """crisis_backstop and the support `backstop` messages test the model's crisis_to_person:
    if code's check learns their words, they stop testing it, so pick new words then."""
    import yaml

    from agent.ingest import detect_crisis
    from intake_eval.support_eval import MESSAGES

    p = get_persona("crisis_backstop")
    assert p.asks["after"] == "narratives" and not p.behaviors  # the runner says it, not the simulator
    assert not detect_crisis(p.asks["text"])
    backstop = [m["text"] for m in yaml.safe_load(MESSAGES.read_text()) if m.get("backstop")]
    assert len(backstop) == 3 and not any(detect_crisis(t) for t in backstop)


def test_codes_crisis_check_catches_common_wordings_and_leaves_narratives_alone():
    from agent.ingest import detect_crisis

    for t in ["Some days I don’t want to live anymore.", "I want to die.", "I've thought about killing myself.",
              "everyone would be better off without me", "There are nights I think about ending it.",
              "I don't see the point of going on.", "I really don't want to be here anymore."]:
        assert detect_crisis(t), t
    for t in ["I hurt myself lifting a crate.", "The suicide of my friend still haunts me.",
              "My buddy died of an overdose.", "I cut myself shaving."]:
        assert not detect_crisis(t), t


def test_withdraws_mid_intake_is_worded_so_codes_checks_miss_it_and_is_scored():
    """It tests intake's to_person: code's checks must miss its words; a hand-off by the rule or
    by intake passes, the orchestrator's or none fails, and no kb_search is expected."""
    from types import SimpleNamespace

    from agent.ingest import WITHDRAW_MESSAGE, wants_human, wants_withdraw
    from agent.store import Event
    from intake_eval.scoring import Score, critical_errors

    p = get_persona("withdraws_mid_intake")
    assert p.asks["expects"] == "person" and not wants_withdraw(p.asks["text"]) and not wants_human(p.asks["text"])

    def errors(*evs):
        events = [Event(seq=i, case_id="c", at="t", type=t, actor=a, data=d) for i, (t, a, d) in enumerate(evs)]
        run = SimpleNamespace(condition="cfile", error="", hit_step_limit=False, gave_up=False, stalled="",
                              asked_at=3, events=events, rt=SimpleNamespace(store=None), case_id="c")  # fmt: skip
        case = CaseFile(case_id="c", stage=1, side_state="needs_human")
        s = Score(persona_id=p.id, condition="cfile", expected_end="needs_human", end_state="needs_human", scenario_pass=True)
        return critical_errors(s, run, p, case)

    sent = ("message", "rule", {"from": "rule", "text": WITHDRAW_MESSAGE})
    assert errors(("escalated", "intake", {"reason": "withdraw"}), sent) == []
    assert errors(("escalated", "rule", {"reason": "withdraw"}), sent) == []
    assert "missed a withdrawal (never handed to a person)" in errors(("escalated", "orchestrator", {"reason": "withdraw"}))
    assert "missed a withdrawal (never handed to a person)" in errors()


def test_the_runner_says_crisis_backstops_words_once_the_narratives_begin():
    from types import SimpleNamespace

    from intake_eval.runner import asks_now

    p, run = get_persona("crisis_backstop"), SimpleNamespace(veteran_replies=9)

    def case(stage, left, answers=()):
        c = CaseFile(case_id="c", stage=stage, owner="intake", checklist={"pass2": list(left)})
        c.answers = {k: Answer(value="x", source="v") for k in answers}
        return c

    assert not asks_now(p, run, case(4, ["dic_claim", "narrative:ptsd:h02"]), "Is this for DIC?")
    assert asks_now(p, run, case(4, ["narrative:ptsd:h02", "narrative:ptsd:h03"]), "What are your symptoms?")
    assert asks_now(p, run, case(4, ["dic_claim"], ["narrative:ptsd:h02"]), "And at its worst?")
    assert not asks_now(p, run, case(4, ["narrative:ptsd:h02"]), "Thanks.")  # no question asked
    assert not asks_now(p, run, case(1, ["narrative:ptsd:h02"]), "Which branch?")  # not pass 2


def test_crisis_disclosure_is_said_by_the_runner_in_words_codes_check_catches():
    """crisis_disclosure tests code's path, so code's check must catch its words (the opposite of
    crisis_backstop)."""
    from agent.ingest import detect_crisis

    p = get_persona("crisis_disclosure")
    assert p.asks["after"] == "narratives" and not p.behaviors and detect_crisis(p.asks["text"])
