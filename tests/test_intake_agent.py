"""The intake sub-agent (L14-L21) through the real harness, tools, guards and documents, driven by
the scripted fake LM: pass 1 to stage 3, the guards, the stop rules, pass 2 and a restart."""

import re

import pytest
from conftest import SSN, VETERAN
from helpers import FILED, PREP_DONE, events, opened, pdf_text, refusals, say
from intake_fixtures import CONSENTS, SCREEN_STEPS, prefill_pass2, screened

from agent.casefile import Answer, CaseFile, Conflict, StopRule
from agent.harness import Turn
from agent.intake import checklist, documents
from agent.intake.agent import DraftArgs, FaxArgs, FormArgs, SecureArgs, SubmitArgs, guard
from agent.kb import NO_ANSWER
from agent.runtime import make_runtime
from agent.scripted.kb import FaqKB
from agent.scripted.lm import call, final
from poa_skill.documents import sha256
from poa_skill.service import FEE_ESIGN_CONSENT

SKILL = (call("read_skill", name="screen-veteran"),)


def _cards(rt, cid, kind):
    return [o.payload for o in rt.updates(cid) if o.kind == "card" and o.payload["type"] == kind]


# ------------------------------------------------------------------------------ pass 1


def test_pass_1_screens_signs_both_documents_waits_for_the_countersign_and_files(rt, lm, signature_uri):
    cid = opened(rt, lm, first=SKILL)

    lm.turn("intake", *SCREEN_STEPS, call("request_secure_info", fields=list(VETERAN), purpose="For the 21-22a."),
            final(reply="Please fill in the secure form."))  # fmt: skip
    say(rt, cid, "Yes. Army 2004-06 to 2010-05, honorable. Nothing else. Never filed. No lawyer.")
    case = rt.store.get_case(cid)
    assert (case.stage, case.checklist["screen"]) == (2, [])
    periods = case.answers["service_periods"]
    assert periods.value[0]["discharge"] == "honorable" and periods.raw.startswith("Army")
    assert periods.source.startswith("veteran, chat")

    lm.turn("intake", final(reply="Thanks. May our attorney see records about ...?"))
    request = _cards(rt, cid, "secure_form")[-1]["request_id"]
    assert documents.submit_secure_form(rt, cid, request, VETERAN) == {}
    rt.wait_until_idle()
    assert rt.store.get_case(cid).answers["first_name"] == Answer(
        value="Jordan", source="secure form", at=rt.store.get_case(cid).answers["first_name"].at)

    lm.turn("intake", call("fill_pdf", form="21-22a", fields={"authorize_7332_records": True,
            "authorize_address_change": False}), final(reply="Here is your form. Does it look right?"))  # fmt: skip
    say(rt, cid, "Yes to the records, no to the address.")
    assert _cards(rt, cid, "document_preview")[-1]["form"] == "21-22a"

    lm.turn("intake", call("get_signature", form="21-22a"), final(reply="Please draw your signature."))
    say(rt, cid, "It looks right.")
    assert _cards(rt, cid, "signature_pad") and not _cards(rt, cid, "sign_button")

    lm.turn("intake", call("get_signature", form="21-22a"), final(reply="Click Sign when you're ready."))
    documents.save_signature(rt, cid, signature_uri)
    rt.wait_until_idle()
    poa_card = _cards(rt, cid, "sign_button")[-1]
    assert poa_card["form"] == "21-22a" and rt.store.get_case(cid).documents["21-22a"].signed_at is None

    lm.turn("intake", call("fill_pdf", form="fee_agreement", fields={}),
            final(reply="Here's the fee agreement: 30% of past-due benefits, only if you win. Do you agree?"))  # fmt: skip
    documents.sign(rt, cid, "21-22a", poa_card["consent_text"])
    rt.wait_until_idle()
    assert "the client pays the firm directly" in lm.prompts("intake")[-1]

    lm.turn("intake", call("get_signature", form="fee_agreement"), final(reply="Click Sign to sign it."))
    say(rt, cid, "Yes, I agree to those terms.")
    fee_card = _cards(rt, cid, "sign_button")[-1]
    assert (fee_card["form"], fee_card["consent_text"]) == ("fee_agreement", FEE_ESIGN_CONSENT)

    lm.turn("intake", final(reply="Our attorney is reviewing both documents now."))
    documents.sign(rt, cid, "fee_agreement", fee_card["consent_text"])
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.side_state) == (2, "intake", "waiting_on_attorney")

    # Messages still go to intake while it waits; filing is refused before the countersign.
    lm.turn("intake", call("submit_va", form="21-22a"), call("efax_ogc", doc="fee_agreement"),
            final(reply="As soon as the attorney countersigns."))  # fmt: skip
    say(rt, cid, "Can you file it now?")
    reasons = [e.data["reason"] for e in events(rt, cid, "refused")]
    assert reasons == ["the 21-22a must be countersigned by the attorney first",
                       "the fee agreement must be signed and countersigned first"]  # fmt: skip
    assert rt.store.get_case(cid).filings == {}

    result = {"finished": "pass 1: 21-22a and ITF filed, fee agreement faxed"}
    lm.turn("intake", call("submit_va", form="21-22a"), call("submit_va", form="itf"),
            call("efax_ogc", doc="fee_agreement"), final(reply="Filed with VA!", result=result))  # fmt: skip
    lm.turn("orchestrator", final())
    documents.countersign(rt, cid, by="Attorney 1")
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.side_state) == (3, None, "waiting_on_va")
    assert set(case.filings) == {"21-22a", "itf", "fee_agreement"}
    assert case.filings["itf"].data["itf_date"] and case.filings["fee_agreement"].confirmation.startswith("FAX-")
    assert [(t.kind, t.done_at is not None) for t in case.tasks] == [("deadline", True)]  # the OGC deadline, met
    assert all(d.countersigned_by == "Attorney 1" for d in case.documents.values())
    assert events(rt, cid, "subagent_result")[0].data["result"]["finished"] == result["finished"]

    # The countersign is a new version; the veteran-signed PDF and its hash are unchanged.
    svc = documents.service(rt, cid)
    for form in ("21-22a", "fee_agreement"):
        doc = svc.live(form)
        signed = svc.docs.pdf(doc.id)
        assert doc.status == "countersigned" and doc.version == 2
        assert doc.signature_audit["signed_pdf_sha256"] == sha256(signed) == doc.countersign_audit["signed_pdf_sha256"]
        stamped = svc.document_pdf(doc.id)
        assert sha256(stamped) == doc.countersign_audit["countersigned_pdf_sha256"] != sha256(signed)
        assert "/s/ Attorney 1" in pdf_text(stamped) and "/s/ Attorney 1" not in pdf_text(signed)
    assert svc.live("fee_agreement").terms == {"fee_pct": 30}
    assert "document_countersigned" in svc.docs.audit_path.read_text()
    # The SSN went only through the secure form: never into any prompt.
    assert not any(SSN in s.user or SSN.replace("-", "") in s.user for s in lm.seen)


def test_record_answer_parses_in_code_and_refuses_what_it_must(rt, lm):
    cid = opened(rt, lm, first=SKILL)
    lm.turn("intake", call("record_answer", q="is_veteran", a="maybe?"),
            call("record_answer", q="is_veteran", a="Yes I did"),
            call("record_answer", q="filed_before", a="not sure", unknown=True),
            call("record_answer", q="favorite_color", a="blue"),
            call("record_answer", q="street", a="100 Main St"),
            call("record_answer", q="narrative:tinnitus:h02", a="ringing"),
            call("fill_pdf", form="21-22a", fields={}), final(reply="Thanks."))  # fmt: skip
    say(rt, cid, "Yes I did. Not sure about a claim.")
    traj = lm.prompts("intake", "extract")[-1]
    assert "the veteran sounds unsure ('maybe')" in traj
    case = rt.store.get_case(cid)
    assert case.answers["is_veteran"].value is True and case.answers["is_veteran"].raw == "Yes I did"
    assert case.answers["filed_before"].unknown and "filed_before" not in case.checklist["screen"]
    reasons = [e.data["reason"] for e in events(rt, cid, "refused")]
    assert reasons[0].startswith("no checklist field 'favorite_color'")
    assert reasons[1] == "street is collected by the secure form: use request_secure_info"
    assert "not a claimed condition" in reasons[2] and reasons[3].startswith("screening isn't finished")


def test_an_ssn_typed_in_chat_never_reaches_the_model_or_the_case_file(rt, lm):
    cid = opened(rt, lm, first=SKILL)
    lm.turn("intake", call("record_answer", q="is_veteran", a=f"yes, SSN {SSN}"),
            final(reply="Please don't type ID numbers here; I'll open a secure form."))  # fmt: skip
    say(rt, cid, f"Yes I served, my SSN is {SSN}")
    first_call = lm.prompts("intake")[-2]  # this turn's first react call: the incoming, no trajectory yet
    assert SSN not in first_call and "[number hidden for your privacy]" in first_call
    refusal = events(rt, cid, "refused")[0].data
    assert refusal["reason"].startswith("ID numbers and dates of birth") and SSN not in str(refusal["args"])
    assert "is_veteran" not in rt.store.get_case(cid).answers


def test_screening_with_an_undischarged_period_never_reaches_stage_2(rt, lm):
    cid = opened(rt, lm)
    steps = [s if s.args.get("q") != "service_periods" else call("record_answer", q="service_periods", a="Army, active, 2004-06 to 2010-05")
             for s in SCREEN_STEPS]  # fmt: skip
    lm.turn("intake", *steps, call("fill_pdf", form="21-22a", fields=CONSENTS), final(reply="What was your discharge?"))
    say(rt, cid, "Yes, Army 2004 to 2010.")
    case = rt.store.get_case(cid)
    assert case.stage == 1 and case.checklist["screen"] == ["service_periods"]
    assert refusals(rt, cid)[-1].startswith("screening isn't finished: still missing service_periods")


def test_the_models_value_is_saved_with_the_veterans_words(rt, lm):
    cid = opened(rt, lm)
    words = "I haven't served since 2008, I was Army"
    lm.turn("intake", call("record_answer", q="is_veteran", a=words),
            call("record_answer", q="is_veteran", a=words, value=True), final(reply="Thanks!"))  # fmt: skip
    say(rt, cid, words)
    traj = lm.prompts("intake", "extract")[-1]
    assert "Pass the structured value you understood in `value` (true or false)" in traj
    case = rt.store.get_case(cid)
    assert case.answers["is_veteran"].value is True and case.answers["is_veteran"].raw == words
    assert case.stop is None
    with pytest.raises(checklist.StrictError):  # words and value disagree
        checklist.parse("is_veteran", "no", True)


def test_kb_search_answers_from_official_sources_or_hands_off(rt, lm):
    cid = opened(rt, lm, first=SKILL)
    lm.turn("intake", call("kb_search", question="Do I have to pay any fee up front?"),
            call("kb_search", question="Will I win my case?"), final(reply="Nothing up front."))  # fmt: skip
    say(rt, cid, "Do I pay anything up front? And will I win?")
    traj = lm.prompts("intake", "extract")[-1]
    assert "https://www.va.gov/ogc/accreditation.asp" in traj and NO_ANSWER[:40] in traj
    assert [e.data["answered"] for e in events(rt, cid, "kb_search")] == [True, False]


# ------------------------------------------------------------------------------ stop rules


@pytest.mark.parametrize(("steps", "rule", "parked"), [
    ([("is_veteran", "yes"), ("filed_before", "yes"), ("receiving_va_pay", "yes"), ("rating_pct", "100 percent")],
     "rated_100", "closed"),
    ([("is_veteran", "yes"), ("service_periods", "Navy 2001-01 to 2003-06, other than honorable")],
     "non_honorable_period", "needs_human"),
])  # fmt: skip
def test_the_firms_stop_rules_run_in_code(rt, lm, steps, rule, parked):
    cid = opened(rt, lm, first=SKILL)
    lm.turn("intake", *[call("record_answer", q=q, a=a) for q, a in steps], final(reply="Thank you for telling me."))
    lm.turn("orchestrator", final())
    say(rt, cid, "Here are my answers.")
    case = rt.store.get_case(cid)
    assert (case.stop.rule, case.side_state, case.owner) == (rule, parked, None)
    assert events(rt, cid, "subagent_result")[0].data["result"]["finished"].endswith(parked)


def test_a_stop_rule_after_filing_goes_to_a_person(rt, lm):
    cid = rt.store.create_case(CaseFile(case_id="c1", stage=4, owner="intake", prep=PREP_DONE, filings=FILED,
                                        goal="Pass 2")).case_id  # fmt: skip
    lm.turn("intake", call("record_answer", q="rating_pct", a="100"), final(reply="Thanks, an attorney will call you."))
    lm.turn("orchestrator", final())
    say(rt, cid, "Actually VA rated me 100% last month.")
    case = rt.store.get_case(cid)
    assert (case.stop.rule, case.side_state) == ("rated_100", "needs_human")


# ------------------------------------------------------------------------------ guards


def test_nothing_is_signed_or_sent_after_a_stop(rt):
    case = screened()
    case.stop = StopRule(rule="non_honorable_period", reason="r", to="needs_human")
    cid = rt.store.create_case(case).case_id
    turn = Turn(rt=rt, case_id=cid, agent="intake", incoming="", number=1)
    for name, args in (("submit_va", SubmitArgs(form="itf")), ("efax_ogc", FaxArgs(doc="fee_agreement")),
                       ("get_signature", FormArgs(form="21-22a"))):  # fmt: skip
        assert re.match(r"stop rule non_honorable_period fired", guard(turn, name, args) or ""), name


def test_itf_needs_the_filed_21_22a_and_no_drafts_or_forms_after_a_stop_or_before_screening(rt):
    case = screened()
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
    assert refusals(rt, early) == []


# ------------------------------------------------------------------------------ pass 2


def _pass2_case() -> CaseFile:
    """After claims prep: the screening answers, prefill from the C-file (an earlier claim, the
    MOS), a conflict on the MOS, and three gaps left."""
    case = CaseFile(case_id="c1", stage=4, filings=FILED, prep=PREP_DONE)
    veteran = "veteran, chat 10:00 UTC"
    case.answers = {
        "is_veteran": Answer(value=True, source=veteran),
        "service_periods": Answer(value=[{"branch": "army", "start": "2004-06", "end": "2010-05",
                                          "discharge": "honorable"}], source=veteran),
        "other_service_periods": Answer(value=[], source=veteran),
        "prior_attorney": Answer(value=False, source=veteran),
        "filed_before": Answer(value=True, source="C-file p. 3"),
        "mos": Answer(value=["11B"], source=veteran),
    }
    case.conflicts = [Conflict(question="mos", on_file=["11B"], cfile=["13B"], cite="C-file p. 7")]
    prefill_pass2(case, leave=("receiving_va_pay", "marital_status", "narrative:tinnitus:h02"))
    return case


def test_pass_2_asks_only_the_gaps_confirms_the_conflict_then_the_narratives(rt, lm):
    cid = rt.store.create_case(_pass2_case()).case_id
    lm.turn("orchestrator", call("run_intake", goal="Pass 2: close the gaps."), final())
    lm.turn("intake", call("read_skill", name="close-gaps"), final(reply="Are you receiving VA disability pay now?"))
    rt.event(cid, "prep_returned", {}, actor="staff")  # nobody owns the case: wakes the orchestrator
    rt.wait_until_idle()
    case = rt.store.get_case(cid)
    assert case.checklist["pass2"] == ["receiving_va_pay", "marital_status", "confirm:mos", "narrative:tinnitus:h02"]
    context = lm.prompts("intake")[0]
    assert '- claim_conditions: ["tinnitus"] (C-file p. 4)' in context
    assert "The C-file (C-file p. 7) says ['13B']" in context

    lm.turn("intake", call("record_answer", q="receiving_va_pay", a="No"),
            call("record_answer", q="marital_status", a="I'm single"),
            call("record_answer", q="confirm:mos", a="13B"),
            final(reply="What symptoms do you have from your tinnitus?"))  # fmt: skip
    say(rt, cid, "No. Single. And the file is right, it was 13B.")
    case = rt.store.get_case(cid)
    assert case.conflicts[0].resolved_at and case.answers["mos"].value == ["13B"]
    assert (case.stage, case.checklist["pass2"]) == (4, ["narrative:tinnitus:h02"])

    lm.turn("intake", call("record_answer", q="narrative:tinnitus:h02", a="Constant ringing, worse at night."),
            final(reply="Thank you. The attorney reviews your file next.", result={"finished": "pass 2: gaps closed"}))  # fmt: skip
    lm.turn("orchestrator", final())
    say(rt, cid, "Constant ringing, worse at night.")
    case = rt.store.get_case(cid)
    assert (case.stage, case.owner, case.checklist["pass2"]) == (5, None, [])
    assert case.answers["narrative:tinnitus:h02"].value == "Constant ringing, worse at night."


def test_an_unsure_confirm_keeps_the_answer_on_file_and_asks_a_person(rt, lm):
    case = screened()
    case.stage, case.filings = 4, dict(FILED)
    case.conflicts = [Conflict(question="filed_before", on_file=False, cfile=True, cite="C-file p. 3")]
    cid = rt.store.create_case(case).case_id
    lm.turn("intake", call("record_answer", q="confirm:filed_before", a="not sure", unknown=True), final(reply="Thanks."))
    say(rt, cid, "I really don't remember.")
    case = rt.store.get_case(cid)
    assert case.answers["filed_before"].value is False and not case.answers["filed_before"].unknown
    assert case.conflicts[0].resolved_at and "C-file p. 3" in case.tasks[-1].text and case.tasks[-1].kind == "staff"


# ------------------------------------------------------------------------------ memory


def test_a_restart_mid_intake_resumes_from_the_store(rt, lm, tmp_path):
    cid = opened(rt, lm, first=SKILL)
    lm.turn("intake", *SCREEN_STEPS[:2], final(reply="Any other period of service?"))
    say(rt, cid, "Yes, Army 2004-06 to 2010-05, honorable.")

    rt2 = make_runtime(tmp_path, lm, kb=FaqKB())  # a new process on the same store
    lm.turn("intake", *SCREEN_STEPS[2:], final(reply="Thanks, next is the 21-22a."))
    rt2.message(cid, "No other service, never filed, no lawyer.")
    rt2.wait_until_idle()
    context = lm.prompts("intake")[-len(SCREEN_STEPS[2:]) - 1]  # the resumed turn's first call
    assert '- is_veteran: true (veteran, chat' in context and "Any other period of service?" in context
    missing = context.split("## Missing")[1].split("## Documents")[0]
    assert "is_veteran" not in missing and "other_service_periods" in missing
    assert rt2.store.get_case(cid).stage == 2
