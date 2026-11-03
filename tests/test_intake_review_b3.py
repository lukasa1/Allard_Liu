"""Review round 3, reviewer B: an empty service history, vault changes and fee changes after
signing, raw text vs. value, hedges about other things, unknown prior representation, stale
answers, British spellings and chat redaction gaps."""

import pytest
from conftest import VETERAN
from test_intake_review_b import CONSENTS, _screened

from agent.casefile import Answer
from agent.harness import Turn
from agent.ingest import redact_chat
from agent.intake import checklist, documents
from agent.intake.agent import DraftArgs, RecordArgs, record_answer, update_draft
from poa_skill.service import FORMS

P = [{"branch": "army", "component": "active", "start": "2004-06", "end": "2008-05", "discharge": "honorable"}]


def _signed(rt, signature_uri, *forms):
    cid = rt.store.create_case(_screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    svc.prepare(CONSENTS)
    svc.prepare(form_key="fee_agreement", terms={"fee_pct": 30})
    for form in forms:
        documents.sign(rt, cid, form, FORMS[form].consent)
    rt.wait_until_idle()
    return cid, svc, Turn(rt=rt, case_id=cid, agent="intake", incoming="", number=1)


# ------------------------------------------------------------------------------ B3-M1


@pytest.mark.parametrize("value", [None, []])
def test_a_veteran_with_no_service_period_is_refused(value):
    with pytest.raises(checklist.StrictError, match="at least one period"):
        checklist.parse("service_periods", "None really, I washed out of basic", value)
    assert checklist.parse("other_service_periods", "No", []) == []


# ------------------------------------------------------------------------------ B3-M2


def test_update_draft_after_signing_creates_a_staff_task(rt, signature_uri):
    cid, _svc, turn = _signed(rt, signature_uri, "21-22a")
    update_draft(turn, DraftArgs(form="fee_agreement", changes={"address.city": "Waukesha"}))
    rt.wait_until_idle()
    tasks = [t.text for t in rt.store.get_case(cid).tasks if t.kind == "staff"]
    assert any("address.city" in t and "21-22a" in t and "update_draft" in t for t in tasks)


# ------------------------------------------------------------------------------ minors


@pytest.mark.parametrize(("key", "a", "value"), [
    ("service_periods", "Army 2004 to 2008, OTH", P),
    ("service_periods", "Army 2004 to 2008 honorable", []),
    ("rating_pct", "100", 70),
    ("rating_pct", "70%", 100),
])  # fmt: skip
def test_plain_words_must_match_the_value(key, a, value):
    with pytest.raises(checklist.StrictError, match="the veteran said"):
        checklist.parse(key, a, value)


def test_a_qualified_text_is_not_cross_checked():
    assert checklist.parse("service_periods", "x", P)[0]["discharge"] == "honorable"
    assert checklist.parse("service_periods", "Army 2004 to 2008, honorable", P)[0]["discharge"] == "honorable"


def test_a_hedge_about_something_else_doesnt_count():
    assert checklist.parse("is_veteran", "Yes, Army 2004 to 2008. My knees probably got wrecked there.", True)
    for a in ("Yes. Probably.", "Yes, I think so", "Yes. I think I was in the Army."):
        with pytest.raises(checklist.StrictError, match="unsure"):
            checklist.parse("is_veteran", a, True)
    with pytest.raises(checklist.StrictError, match="unsure"):
        checklist.parse("service_periods", "Army 2004 to 2008. Honorable, I think.", P)


def test_unknown_prior_attorney_sets_no_fee_and_goes_to_a_person():
    case = _screened()
    case.answers["prior_attorney"] = Answer(value=None, source="veteran, chat", unknown=True)
    case.stage, case.stop = 1, None
    checklist.refresh(case)
    assert checklist.fee_pct(case) is None
    assert case.stop and case.stop.rule == "screen_unresolved" and "lawyer" in case.stop.reason


def test_a_fee_change_after_signing_creates_a_staff_task(rt, signature_uri):
    cid, _svc, turn = _signed(rt, signature_uri, "21-22a", "fee_agreement")
    record_answer(turn, RecordArgs(q="prior_attorney", a="Yes, a lawyer did", value=True))
    record_answer(turn, RecordArgs(q="prior_attorney", a="Yes, a lawyer did", value=True))
    tasks = [t.text for t in rt.store.get_case(cid).tasks if t.text.startswith("Fee mismatch")]
    assert tasks == [("Fee mismatch: the signed fee agreement says 30%, but the firm's rules now give 20% after "
                      "prior representation was re-recorded. Decide whether a new fee agreement is needed.")]  # fmt: skip


def test_an_answer_a_later_answer_hid_is_dropped_from_the_record():
    case = _screened()
    case.answers["receiving_va_pay"] = Answer(value=True, source="v")
    case.answers["rating_pct"] = Answer(value=100, source="v")
    assert checklist.record(case).rating_pct == 100
    case.answers["receiving_va_pay"] = Answer(value=False, source="v")
    assert checklist.record(case).rating_pct is None
    assert checklist.stop_rule(checklist.record(case)) is None


def test_british_spellings_read():
    period = [{**P[0], "discharge": "honourable"}]
    assert checklist.parse("service_periods", "x", period)[0]["discharge"] == "honorable"
    assert checklist.parse("service_periods", "x", [{**P[0], "discharge": "dishonourable"}])[0]["discharge"] == "dishonorable"


@pytest.mark.parametrize("text", ["my birthday's march 4th 1980", "my file number is 1234567"])
def test_chat_redaction_gaps(text):
    clean, hidden = redact_chat(text)
    assert hidden and "1980" not in clean and "1234567" not in clean


def test_a_decimal_is_not_an_id_number():
    assert redact_chat("cost 0.0001234 and 12.3456789") == ("cost 0.0001234 and 12.3456789", False)
