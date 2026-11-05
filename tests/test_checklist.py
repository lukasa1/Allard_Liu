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
    assert "discharge is missing" in item.ask and "army 2004 to 2010" in item.ask
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


def test_only_every_period_non_honorable_stops_and_some_get_a_staff_task():
    """Every period OTH / bad conduct / dishonorable stops (an attorney decides);
    only some: the case goes on, with a staff task naming the period."""
    from agent.casefile import CaseFile

    def case(periods, others):
        c = CaseFile(case_id="c", answers={"is_veteran": Answer(value=True, source="v"),
                                           "service_periods": Answer(value=periods, source="v")})  # fmt: skip
        if others is not None:
            c.answers["other_service_periods"] = Answer(value=others, source="v")
        checklist.refresh(c)
        return c

    oth = {"branch": "army", "component": "active", "start": "2006-03", "end": "2008-07", "discharge": "oth"}
    hon = {"branch": "army", "component": "active", "start": "2001-01", "end": "2005-01", "discharge": "honorable"}
    assert case([oth], None).stop is None  # other periods not asked yet: not decided
    assert case([oth], []).stop.rule == "non_honorable_period"
    mixed = case([hon], [oth])
    assert mixed.stop is None and next(t.text for t in mixed.tasks if "attorney reviews" in t.text).startswith(
        "Service period 2006-03 to 2008-07")
    gen = case([{**hon, "discharge": "general"}], [])
    assert gen.stop is None and not gen.tasks  # general is neither


def test_without_probes_every_period_oth_still_stops():
    """ask_no_probes never asks about other periods: the stop rule decides on the first answer."""
    c = CaseFile(case_id="c", eval_condition="ask_no_probes", answers={
        "is_veteran": Answer(value=True, source="v"),
        "service_periods": Answer(value=[{"branch": "army", "component": "active", "start": "2006",
                                          "end": "2008", "discharge": "oth"}], source="v")})  # fmt: skip
    checklist.refresh(c)
    assert c.stop and c.stop.rule == "non_honorable_period"


@pytest.mark.parametrize("branch", ["army", "marine corps", "air force"])
def test_one_staff_task_per_non_honorable_period_when_months_are_filled_in_later(branch):
    hon = {"branch": "navy", "component": "active", "start": "2001", "end": "2005", "discharge": "honorable"}
    oth = {"branch": branch, "component": "active", "start": "2006", "end": "2008", "discharge": "oth"}
    c = CaseFile(case_id="c", answers={"is_veteran": Answer(value=True, source="v"),
                                       "service_periods": Answer(value=[hon], source="v"),
                                       "other_service_periods": Answer(value=[oth], source="v")})  # fmt: skip
    checklist.refresh(c)
    checklist.refresh(c)  # every intake turn refreshes
    c.answers["other_service_periods"] = Answer(value=[{**oth, "start": "2006-03", "end": "2008-07"}], source="v")
    checklist.refresh(c)
    assert sum("attorney reviews" in t.text for t in c.tasks) == 1
    # a second non-honorable period in the same branch and start year (a short stint, then the Reserve)
    c.answers["other_service_periods"] = Answer(value=[{**oth, "start": "2006-03", "end": "2008-07"},
                                                       {**oth, "component": "reserve", "end": "2012"}], source="v")
    checklist.refresh(c)
    assert sum("attorney reviews" in t.text for t in c.tasks) == 2
