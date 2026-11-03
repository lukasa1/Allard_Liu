"""Memory (save and resume a case mid-conversation) and the read-only customer-support subagent."""

import json

import pytest

from agent.lighthouse import StubLighthouse
from agent.personas import get_persona
from agent.session import CaseSession
from intake_eval.runner import run_case
from intake_eval.scoring import score_run

# ------------------------------------------------------------------------------ memory


@pytest.mark.parametrize(
    "persona_id,condition",
    [("two_service_periods", "ask"), ("recent_decision", "fetch_confirm"), ("crisis_disclosure", "fetch"),
     ("oth_only_period", "fetch_confirm")],
)  # fmt: skip
def test_restarting_after_every_turn_changes_nothing(persona_id, condition, tmp_path):
    """The server 'restarts' before every step: the case must end exactly as without restarts.
    One expected difference: the saved case keeps the C-file DOB masked (only the face note shows
    it), so after a reload the scorer's DOB check reads the mask; the face note itself is identical."""
    persona = get_persona(persona_id)
    a = run_case(persona, condition, data_dir=tmp_path / "a")
    b = run_case(persona, condition, data_dir=tmp_path / "b", restart_every_turn=True)
    assert not b.error, b.error
    assert b.case.face_note == a.case.face_note

    def comparable(run):
        d = score_run(persona, run).to_dict()
        d.pop("facenote_accuracy")
        d["facenote_checks"] = {k: v for k, v in (d["facenote_checks"] or {}).items() if k != "dob"}
        return d

    assert comparable(b) == comparable(a)


def test_resume_mid_intake_asks_the_same_next_question(tmp_path):
    s = CaseSession(provider="offline", persona=get_persona("baseline_clean"), data_dir=tmp_path)
    s.start()
    s.ui_event("va_sign_in_declined")
    first = s.message("Yes")
    r = CaseSession.resume(s.case.case_id, data_dir=tmp_path, lighthouse=StubLighthouse())
    assert r.case.phase == "screening" and r.pending.key == s.pending.key
    assert r.intake.transcript == s.intake.transcript and r.intake.asked == s.intake.asked
    assert first.messages  # and the next reply goes on from there
    assert r.message("Army, active, from 2004-06 to 2010-05, honorable").messages == s.message(
        "Army, active, from 2004-06 to 2010-05, honorable"
    ).messages


def test_resume_refuses_unknown_or_unsafe_ids(tmp_path):
    for bad in ("nope", "../etc/passwd", ""):
        with pytest.raises(KeyError):
            CaseSession.resume(bad, data_dir=tmp_path)


def test_saved_memory_has_no_raw_pii(tmp_path):
    p = get_persona("baseline_clean")
    run = run_case(p, "fetch_confirm", data_dir=tmp_path)
    saved = json.loads((tmp_path / "cases" / f"{run.case.case_id}.json").read_text())
    memory = json.dumps(saved["subagents"])
    assert p.identity["ssn"] not in memory and p.identity["ssn"].replace("-", "") not in memory
    assert p.identity["dob"] not in memory


# ------------------------------------------------------------------------------ support


def _parked(tmp_path, persona_id="baseline_clean", condition="fetch_confirm"):
    run = run_case(get_persona(persona_id), condition, data_dir=tmp_path)
    return run.session


def test_support_answers_status_and_fee_without_changing_the_case(tmp_path):
    s = _parked(tmp_path)
    assert s.case.phase == "attorney_review"
    before = s.case.model_dump(exclude={"tasks", "events", "decisions", "subagents"})
    n_tasks = len(s.case.tasks)
    turn = s.message("Any news on my file? And do I owe you anything yet?")
    text = " ".join(turn.messages)
    assert "with our attorney" in text and "nothing to pay up front" in text
    assert "can't predict VA's timing" in text
    assert len(s.case.tasks) == n_tasks  # answered: nobody needs to read it
    assert s.case.model_dump(exclude={"tasks", "events", "decisions", "subagents"}) == before
    assert s.case.events[-1].type == "support_message" and s.case.events[-1].data["answered"] == ["status", "qa"]


def test_support_returns_a_new_condition_to_the_orchestrator(tmp_path):
    s = _parked(tmp_path)
    s.message("I also want to claim my knees.")
    event = next(e for e in reversed(s.case.events) if e.type == "support_message")
    assert event.data["flags"] == ["new_condition"]  # support only flags it; it changes nothing
    assert s.case.decisions[-1].action == "reopen_intake_for_new_condition"  # the orchestrator decides


def test_support_hands_withdrawals_and_complaints_to_a_person(tmp_path):
    s = _parked(tmp_path)
    s.message("I don't want you to represent me anymore.")
    assert s.case.tasks[-1].kind == "handoff" and "withdraw" in s.case.tasks[-1].text
    assert s.case.poa_signed  # nothing about the representation changed by itself


def test_support_never_answers_case_predictions(tmp_path):
    s = _parked(tmp_path)
    turn = s.message("What rating will I get for my back?")
    assert "passed it to our team" in " ".join(turn.messages)
    assert s.case.tasks[-1].kind == "review"


def test_crisis_in_a_parked_case_still_goes_to_a_person(tmp_path):
    s = _parked(tmp_path)
    turn = s.message("Some days I think about killing myself.")
    assert "988" in " ".join(turn.messages)
    assert s.case.tasks[-1].kind == "handoff"


def test_support_eval_set_passes():
    from intake_eval.support_eval import misses, run_support_eval, summarize

    scores = run_support_eval()
    summary = summarize(scores)
    assert misses(scores) == []
    assert summary["crisis_handled"].split("/")[0] == summary["crisis_handled"].split("/")[1]
