"""Review round 4: a hedge about the dates only, "under honorable conditions", a no to other
service that names the first discharge, update_draft on a signed form, and letter-only
confirmation codes."""

import re

import pytest
from test_intake_review_b3 import P, _signed

from agent.intake import checklist
from agent.intake.agent import DraftArgs, FaxArgs, SubmitArgs, efax_ogc, submit_va, update_draft

OTH = [{**P[0], "discharge": "oth"}]

# ------------------------------------------------------------------------------ B4-M1


@pytest.mark.parametrize("a", [
    "Not sure of the exact months, but Army active 2004 to 2010, honorable.",
    "Honorable. Army active 2004-2010, can't remember the exact month I got out",
    "Army active 2004 to 2010 I believe, honorable discharge",
    "Army active, started maybe summer 2004, out in 2010. Honorable.",
    "Army active June 2004 to May 2010, I think it was June anyway. Honorable.",
    "Honorable, Army active 2004 to 2010. If I remember right I got out in May.",
])  # fmt: skip
@pytest.mark.parametrize("value", [P, None])
def test_a_hedge_only_about_the_dates_is_fine(a, value):
    if value is None and "but" in a:
        value = P  # a "but" left in the words needs the model's value
    assert checklist.parse("service_periods", a, value)[0]["discharge"] == "honorable"


@pytest.mark.parametrize("a", [
    "Army 2004 to 2010, honorable I think",
    "Army 2004 to 2010, honorable, I believe",
    "I think it was honorable, Army 2004 to 2010",
    "Army 2004 to 2010. Not sure about the discharge",
    "Army 2004 to 2010, not sure what kind",
    "Army 2004 to 2010. Probably.",
    "I guess I may be misremembering, honorable",
])  # fmt: skip
def test_an_unsure_discharge_is_still_asked_again(a):
    with pytest.raises(checklist.StrictError, match="unsure"):
        checklist.parse("service_periods", a, P)


@pytest.mark.parametrize("a", [
    "Not sure of the exact months, but Army active 2004 to 2010, OTH",
    "Army 2004 to 2010 I believe, OTH",
])  # fmt: skip
def test_a_date_hedge_doesnt_skip_the_cross_check(a):
    with pytest.raises(checklist.StrictError, match="the veteran said"):
        checklist.parse("service_periods", a, P)


# ------------------------------------------------------------------------------ minors


def test_under_honorable_conditions_alone_is_unclear_so_the_value_wins():
    a = "Army active 2004 to 2010, under honorable conditions"
    general = [{**P[0], "discharge": "general"}]
    assert checklist.parse("service_periods", a, general)[0]["discharge"] == "general"
    with pytest.raises(checklist.StrictError, match="could not read"):
        checklist.parse("service_periods", a)


def test_no_other_period_may_name_the_first_discharge():
    for a in ("Nope. Just the one enlistment, honorable.", "No, just the one, OTH"):
        assert checklist.parse("other_service_periods", a, []) == []
    with pytest.raises(checklist.StrictError, match="the veteran said"):
        checklist.parse("other_service_periods", "Navy reserve 2012 to 2014, OTH", [])


def test_update_draft_on_a_signed_form_leaves_a_staff_task_without_values(rt, signature_uri):
    cid, _svc, turn = _signed(rt, signature_uri, "21-22a")
    for _ in range(2):
        out = update_draft(turn, DraftArgs(form="21-22a", changes={"address.city": "Waukesha"}))
    rt.wait_until_idle()
    assert "error" in out
    tasks = [t.text for t in rt.store.get_case(cid).tasks if "signed 21-22a" in t.text]
    assert len(tasks) == 1 and "address.city" in tasks[0] and "Waukesha" not in tasks[0]


def test_confirmation_codes_are_letters(rt, signature_uri):
    _cid, _svc, turn = _signed(rt, signature_uri)
    codes = [submit_va(turn, SubmitArgs(form="itf"))["confirmation"],
             efax_ogc(turn, FaxArgs(doc="fee_agreement"))["confirmation"]]  # fmt: skip
    assert all(re.fullmatch(r"(VA|FAX)-[A-Z]{10}", c) for c in codes)


@pytest.mark.parametrize("a", ["No, but Navy too, OTH", "No, I also did Navy 2010 to 2014"])
def test_an_empty_other_period_list_is_refused_when_the_veteran_names_one(a):
    """A1 can't be skipped by value=[] when the veteran's words mention another period."""
    with pytest.raises(checklist.StrictError):
        checklist.parse("other_service_periods", a, [])
