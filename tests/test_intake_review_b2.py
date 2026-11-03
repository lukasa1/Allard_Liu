"""Review round 2, reviewer B: stop-rule fields take a structured value from the model (D22), the
-ly discharge forms, hedges, the fee check at signing, a vault change after signing, and guards."""

import pytest
from conftest import VETERAN
from test_intake_review_b import CONSENTS, _refusals, _say, _screened

from agent.casefile import Answer, CaseFile, StopRule
from agent.harness import Turn
from agent.intake import checklist, documents
from agent.intake.agent import DraftArgs, SecureArgs, SubmitArgs, guard
from agent.intake.parsing import coerce, parse_discharge, parse_service_periods
from agent.scripted.lm import call, final
from agent.stages import settle
from poa_skill.service import ESIGN_CONSENT

PERIOD = {"branch": "army", "component": "active", "start": "2004-06", "end": "2008-06"}


def _read(key: str, text: str, value=None):
    try:
        return checklist.parse(key, text, value)
    except checklist.StrictError as err:
        return err


# ------------------------------------------------------------------------------ B2-M1


@pytest.mark.parametrize("text", [
    "I never served in combat", "Never served overseas", "I didn't serve in a war zone",
    "No, I didn't serve in combat", "No, not a combat veteran", "I'm not a combat veteran",
    "I'm not a disabled veteran yet", "Not a retired veteran, I got out after 4", "No, I'm not retired military",
    "I am not currently serving", "No, I'm not active duty anymore", "No longer serving",
    "I'm not in the military anymore", "I don't serve anymore, I got out in 2008",
    "No, I'm a reservist, not a veteran I think", "I'm not serving now, but I did four years in the Army",
    "I'm not active anymore but I was in the Army", "I haven't served since 2008, I was Army",
    "I'm not in the military now, I was in the Marines 2004-2008", "I don't serve anymore but I was a Marine",
    "Not anymore, got out in 2008", "I'm not currently serving, I got out in 2010", "I did, but I'm not serving now",
    "I was in the National Guard, never deployed though", "Never deployed but I was in the Guard 6 years",
    "Army, 2004-2008", "I was in the Army", "I'm a vet",
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


@pytest.mark.parametrize(("text", "value"), [
    ("yes", True), ("No.", False), ("Yes, I served", True), ("No, I never served", False), ("I did not", False), ("I did not serve", False),
    ("false", False), ("true", True),
])  # fmt: skip
def test_plain_yes_and_no_are_read_in_code(text, value):
    assert checklist.parse("is_veteran", text) is value
    assert checklist.parse("receiving_va_pay", text) is value


def test_the_models_value_is_saved_with_the_veterans_words(rt, lm):
    lm.turn("orchestrator", call("run_intake", goal="Pass 1"), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served?"))
    cid = rt.open_case().case_id
    rt.wait_until_idle()
    words = "I haven't served since 2008, I was Army"
    lm.turn("intake", call("record_answer", q="is_veteran", a=words),
            call("record_answer", q="is_veteran", a=words, value=True), final(reply="Thanks!"))  # fmt: skip
    _say(rt, cid, words)
    traj = lm.prompts("intake", "extract")[-1]
    assert "Pass the structured value you understood in `value` (true or false)" in traj
    case = rt.store.get_case(cid)
    assert case.answers["is_veteran"].value is True and case.answers["is_veteran"].raw == words
    assert case.stop is None
    assert isinstance(_read("is_veteran", "no", True), checklist.StrictError)  # words and value disagree


# ------------------------------------------------------------------------------ B2-M2


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
    "discharged other than honorably", "less than honorably discharged", "not honorably",
    "honorable discharge, general? no honorable", "not exactly honorable", "honorable but it was upgraded",
    "technically honorable", "honorable, I think", "honorable I believe", "probably honorable",
    "it was honorable originally", "Discharged for misconduct", "chaptered out",
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


def test_the_structured_periods_value_closes_the_gap():
    words = "Army 2004 to 2008, it wasn't exactly honorable, they called it other than that"
    assert isinstance(_read("service_periods", words), checklist.StrictError)
    (p,) = checklist.parse("service_periods", words, [{**PERIOD, "discharge": "oth"}])
    assert p["discharge"] == "oth"


# ------------------------------------------------------------------------------ minors 1-4, 7


@pytest.mark.parametrize(("key", "text"), [
    ("is_veteran", "Yes, I think so"), ("receiving_va_pay", "probably"), ("rating_pct", "70, I think"),
    ("prior_attorney", "Not sure, maybe the DAV"), ("service_periods", "Army 2004 to 2008, honorable I believe"),
])  # fmt: skip
def test_a_hedge_on_a_stop_rule_field_is_asked_again(key, text):
    err = _read(key, text, True if key != "rating_pct" else 70)
    assert isinstance(err, checklist.StrictError) and "sounds unsure" in str(err)


def test_both_periods_share_one_discharge_and_plain_ratings():
    periods = parse_service_periods("Army 2004 to 2008 and Navy 2010 to 2014, both honorable")
    assert [p.discharge for p in periods] == ["honorable", "honorable"]
    assert checklist.parse("rating_pct", "70%") == 70 and checklist.parse("rating_pct", "x", 70) == 70
    assert isinstance(_read("rating_pct", "I'm rated at seventy"), checklist.StrictError)
    assert checklist.parse("prior_attorney", "A VSO from the DAV") is False


@pytest.mark.parametrize("qid", ["rating_pct", "receiving_va_pay"])
def test_an_unknown_rating_goes_to_a_person(qid):
    case = CaseFile(case_id="c1", stage=1)
    case.answers["is_veteran"] = Answer(value=True, source="chat")
    case.answers[qid] = Answer(value=None, source="chat", unknown=True)
    checklist.refresh(case)
    assert (case.stop.rule, case.stop.to) == ("screen_unresolved", "needs_human")


# ------------------------------------------------------------------------------ minors 5, 6


def test_stale_fee_terms_cannot_be_signed_from_an_open_sign_card(rt, signature_uri):
    cid = rt.store.create_case(_screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    svc.prepare(form_key="fee_agreement", terms={"fee_pct": 30})
    rt.patch(cid, lambda c: c.answers.__setitem__("prior_attorney", Answer(value=True, source="chat")), "intake")
    with pytest.raises(ValueError, match="fee terms changed"):
        documents.sign(rt, cid, "fee_agreement", ESIGN_CONSENT)
    assert svc.live("fee_agreement").status == "draft"


def test_a_vault_change_after_signing_gets_a_staff_task(rt, signature_uri):
    cid = rt.store.create_case(_screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    svc.prepare(CONSENTS)
    documents.sign(rt, cid, "21-22a", ESIGN_CONSENT)
    rt.wait_until_idle()
    req = svc.create_capture_request(["address.city", "email"], "Your new city.")
    documents.submit_secure_form(rt, cid, req["id"], {"address.city": "Waukesha", "email": VETERAN["email"]})
    rt.wait_until_idle()
    (task,) = [t for t in rt.store.get_case(cid).tasks if "after signing" in t.text]
    assert task.kind == "staff" and "address.city" in task.text and "email" not in task.text


# ------------------------------------------------------------------------------ minor 8


def test_itf_needs_the_filed_21_22a_and_no_drafts_or_forms_after_a_stop_or_before_screening(rt):
    case = _screened()
    case.documents = {f: documents.DocState(signed_at="t", countersigned_at="t") for f in documents.FORM_KEYS}
    cid = rt.store.create_case(case).case_id
    turn = Turn(rt=rt, case_id=cid, agent="intake", incoming="", number=1)
    assert guard(turn, "submit_va", SubmitArgs(form="itf")).startswith("file the 21-22a first")
    assert guard(turn, "submit_va", SubmitArgs(form="21-22a")) is None
    draft, secure = DraftArgs(form="21-22a", changes={}), SecureArgs(fields=["email"], purpose="contact")
    rt.patch(cid, lambda c: setattr(c, "stop", StopRule(rule="rated_100", reason="r")), "intake")
    for name, args in (("update_draft", draft), ("request_secure_info", secure)):
        assert guard(turn, name, args).startswith("stop rule rated_100 fired"), name
    early = rt.store.create_case(CaseFile(case_id="c2", stage=1, owner="intake", goal="g")).case_id
    turn = Turn(rt=rt, case_id=early, agent="intake", incoming="", number=1)
    for name, args in (("update_draft", draft), ("request_secure_info", secure)):
        assert guard(turn, name, args).startswith("screening isn't finished"), name
    assert _refusals(rt, early) == []
