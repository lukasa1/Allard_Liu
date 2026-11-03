"""Intake's documents (agent/intake/documents.py, poa_skill): the fee agreement and its claim number,
corrections through the secure form, stale drafts and fee terms, the countersign, staff tasks for
changes after signing, and confirmation codes."""

import io
import re

import pypdf
import pytest
from conftest import SSN, VETERAN
from fastapi.testclient import TestClient
from helpers import pdf_text, refusals, say
from intake_fixtures import CONSENTS, screened

from agent.casefile import Answer
from agent.harness import Turn
from agent.intake import checklist, documents
from agent.intake.agent import (
    DraftArgs,
    FaxArgs,
    RecordArgs,
    SubmitArgs,
    efax_ogc,
    record_answer,
    submit_va,
    update_draft,
)
from agent.scripted.lm import call, final
from poa_skill.fee_agreement import CLAIM_NUMBER_LABEL, claim_number, missing_fields
from poa_skill.service import ESIGN_CONSENT, FORMS, WorkflowError
from poa_skill.tools import preview_card


def _drafted(rt, signature_uri, *sign):
    """A screened case with both drafts and a saved signature, the forms in `sign` signed."""
    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    svc.prepare(CONSENTS)
    svc.prepare(form_key="fee_agreement", terms={"fee_pct": 30})
    for form in sign:
        documents.sign(rt, cid, form, FORMS[form].consent)
    rt.wait_until_idle()
    return cid, svc, Turn(rt=rt, case_id=cid, agent="intake", incoming="", number=1)


# ------------------------------------------------------------------------------ the fee agreement


def test_the_fee_agreement_states_the_fee_and_how_it_is_paid():
    from poa_skill.fee_agreement import sections

    rep = {"first_name": "Attorney", "last_name": "1", "firm_name": "Law Firm"}
    at_20, at_30 = (dict(sections({"first_name": "Jo"}, rep, pct)) for pct in (20, 30))
    assert "withhold the fee" in at_20["How the fee is paid"] and "14.636(h)" in at_20["How the fee is paid"]
    assert "pays the fee directly to the Firm" in at_30["How the fee is paid"]
    assert "owes no fee" in at_30["Fee"] and "discharge" in at_30["Ending the representation"]
    assert "cannot promise" in at_30["No guarantee"] and "ask the Client" in at_30["Conditions of costs"]


def test_the_fee_agreement_needs_its_fee_percentage(rt, lm, svc):
    with pytest.raises(WorkflowError, match="fee percentage"):
        svc.prepare(form_key="fee_agreement", terms={"fee_pct": None})
    case = screened()
    del case.answers["prior_attorney"]
    checklist.refresh(case)
    case.stage = 2
    cid = rt.store.create_case(case).case_id
    documents.service(rt, cid).vault.put(VETERAN)
    lm.turn("intake", call("fill_pdf", form="fee_agreement", fields={}), final(reply="Had a lawyer before?"))
    say(rt, cid, "What's next?")
    assert refusals(rt, cid) == ["the fee isn't set yet: record prior_attorney first (the fee comes from the firm's rules)"]


def test_the_fee_agreement_shows_the_va_file_number_or_the_ssn():
    assert claim_number({"va_file_number": "12345678", "ssn": "123456789"}) == "VA file number: 12345678"
    assert claim_number({"ssn": "123456789"}) == "VA claim number (Social Security number): 123-45-6789"
    assert missing_fields({"first_name": "A", "last_name": "B"}) == [CLAIM_NUMBER_LABEL]
    assert missing_fields({"first_name": "A", "last_name": "B", "ssn": "123456789"}, None) == ["fee percentage"]


def test_the_claim_number_is_in_the_encrypted_pdf_and_nowhere_else(rt, lm, tmp_path):
    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    lm.turn("intake", call("get_case"), call("fill_pdf", form="fee_agreement", fields={}), final(reply="Here it is."))
    say(rt, cid, "Show me the fee agreement.")
    doc = svc.live("fee_agreement")
    assert doc.missing == [] and f"Social Security number): {SSN}" in pdf_text(svc.document_pdf(doc.id))
    digits = SSN.replace("-", "")
    assert not any(SSN in s.user or digits in s.user for s in lm.seen)
    plain = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".bin" and p.name != "vault.key"]
    assert plain and not [p for p in plain if SSN in (t := p.read_text(errors="ignore")) or digits in t]


# ------------------------------------------------------------------------------ corrections and stale drafts


def test_a_secure_form_correction_refreshes_the_draft_and_voids_the_sign_card(rt, signature_uri):
    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    doc = svc.prepare(CONSENTS)
    rt.post_card(cid, "intake", preview_card(svc, doc))
    rt.post_card(cid, "intake", {"type": "sign_button", "form": "21-22a", "document_id": doc.id, "consent_text": "x"})
    assert documents.sign_card_open(rt, cid, "21-22a")

    req = svc.create_capture_request(["address.city"], "Your new city.")
    assert documents.submit_secure_form(rt, cid, req["id"], {"address.city": "Waukesha"}) == {}
    rt.wait_until_idle()
    doc = svc.live("21-22a")
    fields = pypdf.PdfReader(io.BytesIO(svc.docs.pdf(doc.id))).get_fields()
    assert doc.version == 2 and any("WAUKESHA" in str(f.get("/V", "")).upper() for f in fields.values())
    assert not documents.sign_card_open(rt, cid, "21-22a")  # the new preview is the newest card
    assert svc.ready_to_sign(doc.id) == (True, "ready")
    assert rt.store.get_case(cid).answers["city"].value == "Waukesha"

    svc.vault.put({"address.city": "Madison"})  # a vault change with no re-render: signing is refused
    ok, why = svc.ready_to_sign(doc.id)
    assert not ok and "changed after this draft" in why
    with pytest.raises(WorkflowError):
        svc.sign(doc.id, consent_text="x", ip="", user_agent="")


def test_the_demo_refuses_a_sign_click_after_a_newer_preview(rt, signature_uri):
    from demo.app import app, get_runtime

    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    doc = svc.prepare(CONSENTS)
    rt.post_card(cid, "intake", {"type": "sign_button", "form": "21-22a", "document_id": doc.id, "consent_text": "x"})
    rt.post_card(cid, "intake", preview_card(svc, svc.edit(doc.id, {"address.city": "Waukesha"}, actor="intake")))
    app.dependency_overrides[get_runtime] = lambda: rt
    try:
        r = TestClient(app).post(f"/api/cases/{cid}/sign/21-22a", json={"consent_text": "x"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 409 and svc.live("21-22a").status == "draft"


def test_update_draft_updates_the_masked_answer_in_the_case_file(rt, lm):
    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.prepare(CONSENTS)
    svc.prepare(form_key="fee_agreement", terms={"fee_pct": 30})
    lm.turn("intake", call("update_draft", form="21-22a", changes={"address.city": "Waukesha", "first_name": "Jo"}),
            final(reply="Updated."))  # fmt: skip
    say(rt, cid, "My city is Waukesha now, and I go by Jo.")
    case = rt.store.get_case(cid)
    assert case.answers["city"].value == "Waukesha" and case.answers["first_name"].value == "Jo"
    assert svc.live("fee_agreement").version == 2  # the other draft shows the new name too
    assert "Jo Q Testveteran" in pdf_text(svc.docs.pdf(svc.live("fee_agreement").id))


def test_stale_fee_terms_get_no_sign_card(rt, lm, signature_uri):
    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    svc.prepare(form_key="fee_agreement", terms={"fee_pct": 30})
    rt.patch(cid, lambda c: c.answers.__setitem__("prior_attorney", Answer(value=True, source="chat")), "intake")
    lm.turn("intake", call("get_signature", form="fee_agreement"), final(reply="One moment."))
    say(rt, cid, "Actually I did have a lawyer once. Ready to sign.")
    traj = lm.prompts("intake", "extract")[-1]
    assert "the fee terms changed" in traj and not [o for o in rt.updates(cid) if o.payload.get("type") == "sign_button"]


def test_stale_fee_terms_cannot_be_signed_from_an_open_sign_card(rt, signature_uri):
    cid = rt.store.create_case(screened()).case_id
    svc = documents.service(rt, cid)
    svc.vault.put(VETERAN)
    svc.save_signature(signature_uri)
    svc.prepare(form_key="fee_agreement", terms={"fee_pct": 30})
    rt.patch(cid, lambda c: c.answers.__setitem__("prior_attorney", Answer(value=True, source="chat")), "intake")
    with pytest.raises(ValueError, match="fee terms changed"):
        documents.sign(rt, cid, "fee_agreement", ESIGN_CONSENT)
    assert svc.live("fee_agreement").status == "draft"


# ------------------------------------------------------------------------------ signing and the countersign


def test_countersigning_needs_both_documents_signed(rt, signature_uri):
    cid, svc, _turn = _drafted(rt, signature_uri, "21-22a")
    with pytest.raises(ValueError, match="both documents"):
        documents.countersign(rt, cid, by="Attorney 1")
    assert svc.live("21-22a").status == "signed" and svc.live("fee_agreement").status == "draft"


def test_a_vault_change_after_signing_gets_a_staff_task(rt, signature_uri):
    cid, svc, _turn = _drafted(rt, signature_uri, "21-22a")
    req = svc.create_capture_request(["address.city", "email"], "Your new city.")
    documents.submit_secure_form(rt, cid, req["id"], {"address.city": "Waukesha", "email": VETERAN["email"]})
    rt.wait_until_idle()
    (task,) = [t for t in rt.store.get_case(cid).tasks if "after signing" in t.text]
    assert task.kind == "staff" and "address.city" in task.text and "email" not in task.text


def test_update_draft_after_signing_creates_a_staff_task(rt, signature_uri):
    cid, _svc, turn = _drafted(rt, signature_uri, "21-22a")
    update_draft(turn, DraftArgs(form="fee_agreement", changes={"address.city": "Waukesha"}))
    rt.wait_until_idle()
    tasks = [t.text for t in rt.store.get_case(cid).tasks if t.kind == "staff"]
    assert any("address.city" in t and "21-22a" in t and "update_draft" in t for t in tasks)


def test_update_draft_on_a_signed_form_leaves_a_staff_task_without_values(rt, signature_uri):
    cid, _svc, turn = _drafted(rt, signature_uri, "21-22a")
    for _ in range(2):
        out = update_draft(turn, DraftArgs(form="21-22a", changes={"address.city": "Waukesha"}))
    rt.wait_until_idle()
    assert "error" in out
    tasks = [t.text for t in rt.store.get_case(cid).tasks if "signed 21-22a" in t.text]
    assert len(tasks) == 1 and "address.city" in tasks[0] and "Waukesha" not in tasks[0]


def test_a_fee_change_after_signing_creates_a_staff_task(rt, signature_uri):
    cid, _svc, turn = _drafted(rt, signature_uri, "21-22a", "fee_agreement")
    record_answer(turn, RecordArgs(q="prior_attorney", a="Yes, a lawyer did", value=True))
    record_answer(turn, RecordArgs(q="prior_attorney", a="Yes, a lawyer did", value=True))
    tasks = [t.text for t in rt.store.get_case(cid).tasks if t.text.startswith("Fee mismatch")]
    assert tasks == [("Fee mismatch: the signed fee agreement says 30%, but the firm's rules now give 20% after "
                      "prior representation was re-recorded. Decide whether a new fee agreement is needed.")]  # fmt: skip


def test_confirmation_codes_are_letters(rt, signature_uri):
    _cid, _svc, turn = _drafted(rt, signature_uri)
    codes = [submit_va(turn, SubmitArgs(form="itf"))["confirmation"],
             efax_ogc(turn, FaxArgs(doc="fee_agreement"))["confirmation"]]  # fmt: skip
    assert all(re.fullmatch(r"(VA|FAX)-[A-Z]{10}", c) for c in codes)
