"""Answer parsing in code (agent/intake/parsing.py, checklist.parse): yes/no, discharges, service
periods, ratings, hedges, and the cross-check of the veteran's words against the model's value."""

import pytest

from agent.casefile import Answer, CaseFile
from agent.intake import checklist
from agent.intake.parsing import (
    coerce,
    parse_bool,
    parse_discharge,
    parse_service_periods,
    parse_text,
)
from agent.stages import settle

PERIOD = {"branch": "army", "component": "active", "start": "2004-06", "end": "2008-06"}
P = [{"branch": "army", "component": "active", "start": "2004-06", "end": "2008-05", "discharge": "honorable"}]


def _read(key: str, text: str, value=None):
    try:
        return checklist.parse(key, text, value)
    except checklist.StrictError as err:
        return err


# ------------------------------------------------------------------------------ yes and no


@pytest.mark.parametrize(("text", "value"), [
    ("yes", True), ("No.", False), ("Yes, I served", True), ("No, I never served", False), ("I did not", False), ("I did not serve", False),
    ("false", False), ("true", True),
])  # fmt: skip
def test_plain_yes_and_no_are_read_in_code(text, value):
    assert checklist.parse("is_veteran", text) is value
    assert checklist.parse("receiving_va_pay", text) is value


@pytest.mark.parametrize("text", [
    "Never deployed, but yes I served", "No combat, but I was in the Navy", "Nah just kidding, yes",
    "I never deployed but I served", "Yes, actually no",
])  # fmt: skip
def test_a_no_that_turns_into_a_yes_is_unclear(text):
    assert parse_bool(text) is None
    with pytest.raises(ValueError):
        checklist.parse("is_veteran", text)


@pytest.mark.parametrize("text", [
    "No, I didn't serve in combat", "I never served in combat", "Never served overseas", "I'm not a combat veteran",
    "I'm not a disabled veteran yet", "No, I'm a reservist, not a veteran I think", "I am not currently serving",
    "I'm not in the military anymore", "I don't serve anymore, I got out in 2008",
    "I haven't served since 2008, I was Army", "No longer serving", "Not anymore, got out in 2008",
    "Never deployed but I was in the Guard 6 years", "I'm a vet",
])  # fmt: skip
def test_free_text_never_reads_as_not_a_veteran(text):
    result = _read("is_veteran", text)
    assert result is not False, text
    if isinstance(result, checklist.StrictError):  # the model is told to pass its value, not unknown
        assert "Pass the structured value" in str(result) or "unsure" in str(result)
    case = CaseFile(case_id="c", stage=1, owner="intake", goal="g")
    if not isinstance(result, checklist.StrictError):
        case.answers["is_veteran"] = Answer(value=result, source="v", raw=text)
    checklist.refresh(case)
    settle(case)
    assert case.stop is None and case.side_state != "closed"


def test_parsing_fixes():
    assert parse_bool("No idea") is None
    assert checklist.parse("filed_before", "Never") is False  # not a stop-rule field
    rated = coerce("conditions_rated", [{"name": "PTSD", "rating_pct": 30}, {"name": "post traumatic stress disorder", "rating_pct": 50}, {"name": "tinnitus", "rating_pct": 10}])
    assert [(r.name, r.rating_pct) for r in rated] == [("ptsd", 30), ("tinnitus", 10)]


def test_review3_parsing_regressions():
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
    # "I'm confused" is not a yes; "No problem" is not a no; "No, I'm not sure" is unsure
    for text in ("I'm confused", "I have a question", "I did drugs once, does that matter"):
        assert parse_bool(text) is None, text
    assert parse_bool("No problem") is True and parse_bool("No, I'm not sure") is None
    # unsure answers are not stored as definite empties
    for qtype in ("conditions", "list_str", "conditions_rated", "service_periods_append"):
        assert parse_text(qtype, "No idea, honestly") is None, qtype
    assert parse_text("conditions", "PTSD, no clue about the rest") == ["PTSD"]
    assert parse_text("str", "Not sure, maybe 11B") == "Not sure, maybe 11B"


def test_a_vso_is_not_a_prior_attorney():
    assert checklist.parse("prior_attorney", "A VSO from the DAV") is False
    assert checklist.parse("prior_attorney", "Yes, a VSO from the DAV helped") is False
    assert checklist.parse("prior_attorney", "Yes, a lawyer and then the DAV", True) is True


# ------------------------------------------------------------------------------ discharges


@pytest.mark.parametrize(("text", "code"), [
    ("honorable", "honorable"),
    ("Honorable discharge", "honorable"),
    ("other than honorable", "oth"),
    ("other-than-honorable", "oth"),
    ("Under Other Than Honorable Conditions", "oth"),
    ("OTH", "oth"),
    ("less than honorable", "oth"),
    ("not honorable", "oth"),
    ("it wasn't honorable", "oth"),
    ("un-honorable", "oth"),
    ("bad-conduct discharge", "bad_conduct"),
    ("BCD", "bad_conduct"),
    ("dishonorable", "dishonorable"),
    ("general", "general"),
    ("general under honorable conditions", "general"),
    ("uncharacterized", "uncharacterized"),
    ("entry-level separation", "uncharacterized"),
    ("not sure, maybe honorable", None),
    ("not dishonorable", None),
    ("honorable, then general", None),
    ("I don't remember", None),
])  # fmt: skip
def test_discharge_phrasings(text, code):
    assert parse_discharge(text) == code


def test_discharge_in_free_text_and_json():
    (p,) = parse_text("service_periods", "Navy, active, 2001-01 to 2003-06, other-than-honorable")
    assert p.discharge == "oth"
    (p,) = parse_text("service_periods", "Army 2001 to 2005, bad-conduct discharge")
    assert p.discharge == "bad_conduct"
    (p,) = parse_text("service_periods", "Army 2001 to 2005, less than honorable")
    assert p.discharge == "oth"
    for dis, code in (("Other-Than-Honorable", "oth"), ("not honorable", "oth"), ("Bad Conduct", "bad_conduct"),
                      ("honorable", "honorable"), ("GENERAL", "general")):  # fmt: skip
        (p,) = coerce("service_periods", [{"branch": "Army", "start": "2001-01", "end": "2005-01", "discharge": dis}])
        assert p.discharge == code, dis
    with pytest.raises(ValueError):  # unreadable: refused (re-ask), not stored as no discharge
        coerce("service_periods", [{"branch": "army", "start": "2001-01", "end": "2005-01", "discharge": "the usual"}])


@pytest.mark.parametrize(("text", "code"), [
    ("discharged other than honorably", "oth"), ("less than honorably discharged", "oth"),
    ("not honorably", "oth"), ("I was dishonorably discharged", "dishonorable"),
    ("discharged dishonorably", "dishonorable"), ("general discharge under honorable conditions", "general"),
])  # fmt: skip
def test_ly_forms_and_general_discharge(text, code):
    assert parse_discharge(text) == code
    (p,) = checklist.parse("service_periods", f"Army 2004 to 2008, {text}")
    assert p["discharge"] == code
    (p,) = coerce("service_periods", [{**PERIOD, "discharge": text}], strict=True)
    assert p.discharge == code


@pytest.mark.parametrize("text", [
    "honorable discharge, general? no honorable", "not exactly honorable", "honorable but it was upgraded",
    "technically honorable", "honorable, I think", "it was honorable originally", "Discharged for misconduct",
    "chaptered out",
])  # fmt: skip
def test_a_qualified_discharge_never_reads_as_honorable(text):
    result = _read("service_periods", f"Army 2004 to 2008, {text}")
    assert isinstance(result, checklist.StrictError) or result[0]["discharge"] != "honorable", text
    for dis in (text, "unknown", "the usual"):  # the JSON path: plain, or refused
        try:
            (p,) = coerce("service_periods", [{**PERIOD, "discharge": dis}], strict=True)
        except ValueError:
            continue
        assert p.discharge != "honorable", dis


def test_british_spellings_read():
    period = [{**P[0], "discharge": "honourable"}]
    assert checklist.parse("service_periods", "x", period)[0]["discharge"] == "honorable"
    assert checklist.parse("service_periods", "x", [{**P[0], "discharge": "dishonourable"}])[0]["discharge"] == "dishonorable"


def test_under_honorable_conditions_alone_is_unclear_so_the_value_wins():
    a = "Army active 2004 to 2010, under honorable conditions"
    general = [{**P[0], "discharge": "general"}]
    assert checklist.parse("service_periods", a, general)[0]["discharge"] == "general"
    with pytest.raises(checklist.StrictError, match="could not read"):
        checklist.parse("service_periods", a)


# ------------------------------------------------------------------------------ service periods


def test_both_periods_share_one_discharge():
    periods = parse_service_periods("Army 2004 to 2008 and Navy 2010 to 2014, both honorable")
    assert [p.discharge for p in periods] == ["honorable", "honorable"]


def test_the_structured_periods_value_closes_the_gap():
    words = "Army 2004 to 2008, it wasn't exactly honorable, they called it other than that"
    assert isinstance(_read("service_periods", words), checklist.StrictError)
    (p,) = checklist.parse("service_periods", words, [{**PERIOD, "discharge": "oth"}])
    assert p["discharge"] == "oth"


@pytest.mark.parametrize("value", [None, []])
def test_a_veteran_with_no_service_period_is_refused(value):
    with pytest.raises(checklist.StrictError, match="at least one period"):
        checklist.parse("service_periods", "None really, I washed out of basic", value)
    assert checklist.parse("other_service_periods", "No", []) == []


def test_no_other_period_may_name_the_first_discharge():
    for a in ("Nope. Just the one enlistment, honorable.", "No, just the one, OTH"):
        assert checklist.parse("other_service_periods", a, []) == []
    with pytest.raises(checklist.StrictError, match="the veteran said"):
        checklist.parse("other_service_periods", "Navy reserve 2012 to 2014, OTH", [])


@pytest.mark.parametrize("a", ["No, but Navy too, OTH", "No, I also did Navy 2010 to 2014"])
def test_an_empty_other_period_list_is_refused_when_the_veteran_names_one(a):
    """A1 can't be skipped by value=[] when the veteran's words mention another period."""
    with pytest.raises(checklist.StrictError):
        checklist.parse("other_service_periods", a, [])


# ------------------------------------------------------------------------------ ratings


def test_a_rating_answer_with_two_numbers_or_a_negation_is_asked_again():
    assert checklist.parse("rating_pct", "100 percent") == 100
    assert checklist.parse("rating_pct", "70%") == 70 and checklist.parse("rating_pct", "x", 70) == 70
    assert isinstance(_read("rating_pct", "I'm rated at seventy"), checklist.StrictError)
    for text in ("I'm not 100, I'm 70", "70, maybe 100 soon", "between 70 and 100"):
        with pytest.raises(ValueError):
            checklist.parse("rating_pct", text)


# ------------------------------------------------------------------------------ hedges


@pytest.mark.parametrize(("key", "text"), [
    ("is_veteran", "Yes, I think so"), ("receiving_va_pay", "probably"), ("rating_pct", "70, I think"),
    ("prior_attorney", "Not sure, maybe the DAV"),
])  # fmt: skip
def test_a_hedge_on_a_stop_rule_field_is_asked_again(key, text):
    err = _read(key, text, True if key != "rating_pct" else 70)
    assert isinstance(err, checklist.StrictError) and "sounds unsure" in str(err)


def test_a_hedge_about_something_else_doesnt_count():
    assert checklist.parse("is_veteran", "Yes, Army 2004 to 2008. My knees probably got wrecked there.", True)
    for a in ("Yes. Probably.", "Yes. I think I was in the Army."):
        with pytest.raises(checklist.StrictError, match="unsure"):
            checklist.parse("is_veteran", a, True)
    with pytest.raises(checklist.StrictError, match="unsure"):
        checklist.parse("service_periods", "Army 2004 to 2008. Honorable, I think.", P)


DATE_HEDGES = [
    "Not sure of the exact months, but Army active 2004 to 2010, honorable.",
    "Honorable. Army active 2004-2010, can't remember the exact month I got out",
    "Army active 2004 to 2010 I believe, honorable discharge",
    "Army active, started maybe summer 2004, out in 2010. Honorable.",
    "Army active June 2004 to May 2010, I think it was June anyway. Honorable.",
    "Honorable, Army active 2004 to 2010. If I remember right I got out in May.",
]


# A "but" left in the words needs the model's value: that input is only tested with one.
@pytest.mark.parametrize(("a", "value"), [(a, v) for a in DATE_HEDGES for v in (P, None) if v is not None or "but" not in a])
def test_a_hedge_only_about_the_dates_is_fine(a, value):
    assert checklist.parse("service_periods", a, value)[0]["discharge"] == "honorable"


@pytest.mark.parametrize("a", [
    "Army 2004 to 2010, honorable I think",
    "I think it was honorable, Army 2004 to 2010",
    "Army 2004 to 2010. Not sure about the discharge",
    "Army 2004 to 2010. Probably.",
    "I guess I may be misremembering, honorable",
])  # fmt: skip
def test_an_unsure_discharge_is_still_asked_again(a):
    with pytest.raises(checklist.StrictError, match="unsure"):
        checklist.parse("service_periods", a, P)


@pytest.mark.parametrize("a", [
    "honorable, but not sure when it got downgraded",
    "not sure when but I got court-martialed",
])  # fmt: skip
def test_a_hedge_about_how_service_ended_is_still_asked_again(a):
    """Only hedges about *when* are dropped; one about the discharge or its change is re-asked."""
    with pytest.raises(checklist.StrictError, match="unsure"):
        checklist.parse("service_periods", a, P)


# ------------------------------------------------------------------------------ words vs. value


@pytest.mark.parametrize(("key", "a", "value"), [
    ("service_periods", "Army 2004 to 2008, OTH", P),
    ("service_periods", "Army 2004 to 2008 honorable", []),
    ("rating_pct", "100", 70),
])  # fmt: skip
def test_plain_words_must_match_the_value(key, a, value):
    with pytest.raises(checklist.StrictError, match="the veteran said"):
        checklist.parse(key, a, value)


@pytest.mark.parametrize("a", [
    "Not sure of the exact months, but Army active 2004 to 2010, OTH",
    "Army 2004 to 2010 I believe, OTH",
])  # fmt: skip
def test_a_date_hedge_doesnt_skip_the_cross_check(a):
    with pytest.raises(checklist.StrictError, match="the veteran said"):
        checklist.parse("service_periods", a, P)


def test_a_qualified_text_is_not_cross_checked():
    assert checklist.parse("service_periods", "x", P)[0]["discharge"] == "honorable"
    assert checklist.parse("service_periods", "Army 2004 to 2008, honorable", P)[0]["discharge"] == "honorable"
