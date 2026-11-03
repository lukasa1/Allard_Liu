import pytest

"""The intake subagent: stages, VA prefill per records_mode, QA, safety."""

from agent.intake.brains import OfflineBrain, split_question
from agent.intake.controller import AgentConfig, IntakeAgent, QAResult
from agent.intake.questions import QuestionBank
from agent.intake.schema import ServicePeriod

PERIOD = ServicePeriod(
    branch="army", component="active", start="2004-06", end="2010-05", discharge="honorable"
)


def agent(mode="fetch_confirm", qa=None, **kw) -> IntakeAgent:
    return IntakeAgent(OfflineBrain(), config=AgentConfig(records_mode=mode, **kw), qa=qa)


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
    assert all(q.confirms and q.ask_with_records for q in probes.values())


def test_screen_stage_ends_with_stage_complete_not_a_closing():
    a = agent(mode="ask")
    turn = a.start("screen")
    assert "served in the U.S. military" in turn.text
    for reply in [
        "Yes.",
        "Army, active duty, from 2004-06 to 2010-05, honorable discharge",
        "No.",
        "No.",
        "No.",
        "No.",
    ]:
        turn = a.reply(reply)
    assert turn.event == "stage_complete" and not a.done
    assert a.record.service_periods == [PERIOD]
    # contact/name questions are never asked in chat: the POA secure form collects them
    assert not set(a.asked) & {"first_name", "street", "email"}


def test_fetch_mode_skips_va_questions_and_probes():
    a = agent(mode="fetch")
    settled = a.prefill_from_records(
        {"is_veteran": True, "service_periods": [PERIOD], "filed_before": False}, "Army ..."
    )
    assert set(settled) == {"is_veteran", "service_periods", "filed_before"}
    turn = a.start("screen")
    assert "attorney or law firm" in turn.text  # only prior_attorney is left
    assert a.record.provenance["service_periods"] == "va_records"


def test_fetch_confirm_asks_probes_worded_around_the_records():
    a = agent(mode="fetch_confirm")
    a.prefill_from_records(
        {"is_veteran": True, "service_periods": [PERIOD], "filed_before": False},
        "Army active duty 2004-06 to 2010-05 (honorable)",
    )
    turn = a.start("screen")
    assert "VA's records list this service: Army active duty 2004-06 to 2010-05" in turn.text
    turn = a.reply("Yes, Army, reserve, from 2012-01 to 2014-12, honorable discharge")
    assert (
        len(a.record.service_periods) == 2
        and a.record.provenance["service_periods"] == "chat+va_records"
    )
    assert turn.text.startswith("VA's records don't show an earlier claim")


def test_ask_mode_ignores_records():
    a = agent(mode="ask")
    assert a.prefill_from_records({"is_veteran": True}, "x") == []
    assert "served in the U.S. military" in a.start("screen").text


def test_a_question_is_answered_without_counting_as_a_clarification():
    calls = []

    def qa(q):
        calls.append(q)
        return QAResult(
            text="VA fees come from past-due benefits.",
            sources=["https://www.va.gov/ogc/accreditation.asp"],
        )

    a = agent(mode="ask", qa=qa)
    a.start("screen")
    turn = a.reply("How much does this cost?")
    assert calls == ["How much does this cost?"]
    assert "past-due benefits" in turn.text and "va.gov" in turn.text and "served" in turn.text
    assert a.asked["is_veteran"] == 1  # not burned as a clarification
    assert a.record.qa_log[0]["sources"]


def test_unanswerable_questions_go_to_the_team():
    a = agent(mode="ask", qa=lambda q: QAResult(text="", handoff=True))
    a.start("screen")
    turn = a.reply("Will I win my case?")
    assert "someone from our team" in turn.text
    assert a.record.questions_for_team == ["Will I win my case?"]


def test_crisis_escalates_immediately():
    a = agent(mode="ask")
    a.start("screen")
    turn = a.reply("Honestly I don't want to live anymore")
    assert turn.event == "escalated" and a.done and "988" in turn.text


def test_early_stop_from_records_ends_at_start():
    a = agent(mode="fetch")
    a.prefill_from_records({"is_veteran": True, "rating_pct": 100, "receiving_va_pay": True}, None)
    turn = a.start("screen")
    assert turn.event == "stopped" and a.outcome().decision == "rated_100"


def test_split_question():
    assert split_question("Yes. How much do you charge?") == ("Yes.", "How much do you charge?")
    assert split_question("No, that's all of my service.") == ("No, that's all of my service.", "")


def test_unknown_veteran_status_never_reaches_the_poa():
    a = agent(mode="ask")
    a.start("screen")
    turn = a.reply("I'm not sure.")  # "I don't know" is taken as an answer, so screening stops
    assert turn.event == "stopped" and a.outcome().decision == "incomplete"


def test_parsing_fixes():
    from agent.intake.parsing import coerce, parse_bool

    assert parse_bool("No idea") is None and parse_bool("No.") is False
    rated = coerce("conditions_rated", [{"name": "PTSD", "rating_pct": 30}, {"name": "post traumatic stress disorder", "rating_pct": 50}, {"name": "tinnitus", "rating_pct": 10}])
    assert [(r.name, r.rating_pct) for r in rated] == [("ptsd", 30), ("tinnitus", 10)]


def test_review3_parsing_regressions():
    from agent.intake.parsing import coerce, parse_text

    def period(text):
        (p,) = parse_text("service_periods", text)
        return p.branch, p.component, p.start, p.end, p.discharge

    # whole words only: "both"/"another"/"nothing" are not OTH, "generally" is not general
    assert period("Army, active, 2004-06 to 2010-05, honorable, both tours in Iraq")[4] == "honorable"
    assert period("Navy 2001 to 2005, honorable, served on another carrier")[4] == "honorable"
    assert period("Marines 2001 to 2005, general discharge, nothing else")[4] == "general"
    assert period("Army 2001 to 2005, honorable, generally good")[4] == "honorable"
    assert period("Army, active, 06/15/2004 to 05/20/2010, honorable")[2:4] == ("2004-06", "2010-05")
    assert parse_text("service_periods", "Army, active, 2004-13 to 2010-05, honorable") is None
    assert period("Air National Guard, 2005-01 to 2011-01, honorable")[:2] == ("air force", "guard")
    # a leading "No" doesn't throw away what follows
    assert period("No other active duty, but Navy, reserve, 2014 to 2016, honorable")[:2] == ("navy", "reserve")
    assert parse_text("service_periods", "No") == []
    assert parse_text("conditions", "No, but my knees hurt") == ["my knees hurt"]
    # a leading yes/no wins over a later "not sure"; "No idea" is still unsure
    assert parse_text("bool", "Yes I served, not sure what else you need") is True
    assert parse_text("bool", "No idea") is None
    assert parse_text("bool", "I'm a veteran") is True and parse_text("bool", "Not yet") is False
    # "I don't know" is not a value
    assert parse_text("conditions", "I don't know") is None
    assert parse_text("str", "not sure") is None
    assert parse_text("conditions", "tinnitus, and I don't know what else") == ["tinnitus"]
    for qtype, value in (("conditions", ["I don't know"]), ("str", "not sure")):
        with pytest.raises(ValueError):
            coerce(qtype, value)
    opts = ("single", "married", "divorced", "separated", "widowed")
    assert parse_text("enum", "never married", opts) == "single"
    assert parse_text("enum", "divorced, never remarried", opts) == "divorced"


def test_review4_parsing_and_handoff_regressions():
    from agent.intake.brains import _WANTS_HUMAN
    from agent.intake.parsing import parse_bool, parse_text

    # a request for a person, not a mention of one
    for text in ("Can I talk to a person?", "I'd like to speak with someone", "Have someone call me"):
        assert _WANTS_HUMAN.search(text), text
    for text in (
        "Yes. I never could talk to someone about what happened over there.",
        "Does a human read this?",
        "Do I need to talk to someone at VA?",
        "Yes - I'm a veteran, my wife told me to speak with someone",
    ):
        assert not _WANTS_HUMAN.search(text), text
    # "I'm confused" is not a yes; "No problem" is not a no; "No, I'm not sure" is unsure
    for text in ("I'm confused", "I have a question", "I did drugs once, does that matter"):
        assert parse_bool(text) is None, text
    assert parse_bool("No problem") is True and parse_bool("No, I'm not sure") is None
    # unsure answers are not stored as definite empties
    for qtype in ("conditions", "list_str", "conditions_rated", "service_periods_append"):
        assert parse_text(qtype, "No idea, honestly") is None, qtype
    assert parse_text("conditions", "PTSD, no clue about the rest") == ["PTSD"]
    assert parse_text("str", "Not sure, maybe 11B") == "Not sure, maybe 11B"
    # two periods joined by "and"
    assert [p.branch for p in parse_text("service_periods", "Army 2004 to 2008 and Navy 2010 to 2014")] == ["army", "navy"]
