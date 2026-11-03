"""The question bank and the checklists built from it (agent/intake/questions.py, checklist.py):
what is still missing, the record, and the screening answers that go to a person."""

import pytest
from intake_fixtures import screened

from agent.casefile import Answer, CaseFile
from agent.intake import checklist
from agent.intake.questions import QuestionBank


def test_question_bank_tags_every_question():
    bank = QuestionBank.load()
    # 34 questions from the firm's form + 3 verification probes (second period, old claim, C-file
    # check) + add_condition (asked only if intake is reopened)
    assert len(bank.structured) == 38 and len(bank.narrative) == 16
    assert sum(q.probe for q in bank.structured) == 3
    assert {q.id for q in bank.structured if q.cfile} == {"sc_conditions", "prior_attorney_name", "mos"}
    assert {q.stage for q in bank.structured} == {"screen", "post_poa", "reopen"}
    secure = {q.id for q in bank.structured if q.source == "secure_form"}
    assert secure == {
        "first_name",
        "last_name",
        "street",
        "city",
        "state",
        "zip",
        "cell_phone",
        "email",
    }
    probes = {q.id: q for q in bank.structured if q.probe}
    assert set(probes) == {"other_service_periods", "prior_claim_probe", "cfile_discrepancy_check"}
    assert all(q.confirms for q in probes.values())


def test_every_narrative_prompt_names_the_condition():
    assert all("{condition}" in p.ask for p in checklist.BANK.narrative if not p.auto)


def test_the_pass_2_checklist_has_the_firms_questions_and_16_prompts_per_condition():
    case = CaseFile(case_id="c1", stage=4, answers={
        "is_veteran": Answer(value=True, source="v"), "claim_conditions": Answer(value=["tinnitus"], source="v")})  # fmt: skip
    items = [i.id for i in checklist.missing(case, "pass2")]
    narratives = [i for i in items if i.startswith("narrative:tinnitus:")]
    assert len(narratives) == 15 and narratives[0].endswith("h02")  # h01 is the condition itself
    assert {"service_periods", "street", "mos", "heard_about"} <= set(items) and "receiving_va_pay" not in items
    assert [i.id for i in checklist.missing(CaseFile(case_id="c2"), "screen")] == ["is_veteran"]


def test_a_period_without_a_discharge_stays_on_the_screen_checklist():
    case = screened()
    assert case.checklist["screen"] == []
    case.answers["service_periods"] = Answer(value=checklist.parse("service_periods", "Army 2004 to 2010"),
                                             source="chat")  # fmt: skip
    checklist.refresh(case)
    assert case.checklist["screen"] == ["service_periods"] and case.stop is None
    (item,) = checklist.missing(case, "screen")
    assert "discharge is missing" in item.ask and "army 2004-01 to 2010-12" in item.ask
    case.answers["other_service_periods"] = Answer(value=checklist.parse("other_service_periods", "Navy reserve 2012 to 2014"),
                                                   source="chat")  # fmt: skip
    checklist.refresh(case)
    assert case.checklist["screen"] == ["service_periods", "other_service_periods"]


@pytest.mark.parametrize("qid", ["is_veteran", "service_periods", "rating_pct", "receiving_va_pay"])
def test_an_unknown_screening_answer_goes_to_a_person(qid):
    case = CaseFile(case_id="c1", stage=1)
    case.answers["is_veteran"] = Answer(value=True, source="chat")
    case.answers[qid] = Answer(value=None, source="chat", unknown=True)
    checklist.refresh(case)
    assert (case.stop.rule, case.stop.to) == ("screen_unresolved", "needs_human")


def test_unknown_prior_attorney_sets_no_fee_and_goes_to_a_person():
    case = screened()
    case.answers["prior_attorney"] = Answer(value=None, source="veteran, chat", unknown=True)
    case.stage, case.stop = 1, None
    checklist.refresh(case)
    assert checklist.fee_pct(case) is None
    assert case.stop and case.stop.rule == "screen_unresolved" and "lawyer" in case.stop.reason


def test_an_answer_a_later_answer_hid_is_dropped_from_the_record():
    case = screened()
    case.answers["receiving_va_pay"] = Answer(value=True, source="v")
    case.answers["rating_pct"] = Answer(value=100, source="v")
    assert checklist.record(case).rating_pct == 100
    case.answers["receiving_va_pay"] = Answer(value=False, source="v")
    assert checklist.record(case).rating_pct is None
    assert checklist.stop_rule(checklist.record(case)) is None
