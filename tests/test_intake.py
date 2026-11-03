"""The intake question bank and answer parsing (agent/intake/questions.py, parsing.py)."""

import pytest

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


def test_review4_parsing_regressions():
    from agent.intake.parsing import parse_bool, parse_text

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
