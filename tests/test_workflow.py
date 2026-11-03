import io
import json

import pypdf
import pytest
from conftest import SSN, VETERAN

from poa_skill.service import ESIGN_CONSENT, WorkflowError
from poa_skill.tools import TOOLS, run_tool

SSN_DIGITS = SSN.replace("-", "")


def _capture_all(svc):
    req = svc.create_capture_request(list(VETERAN), "test")
    assert svc.complete_capture_request(req["id"], VETERAN) == {}


def test_vault_is_encrypted_at_rest_and_masks_for_the_agent(svc):
    _capture_all(svc)
    raw = svc.vault.path.read_bytes()
    assert SSN_DIGITS.encode() not in raw and b"Testveteran" not in raw
    masked = svc.vault.masked()
    assert masked["ssn"] == "***-**-6789"
    assert masked["date_of_birth"] == "**/**/1988"
    assert masked["first_name"] == "Jordan"


def test_secure_form_accepts_only_its_own_fields(svc):
    req = svc.create_capture_request(["first_name"], "name only")
    svc.complete_capture_request(req["id"], {"first_name": "Jordan", "ssn": SSN})
    assert "ssn" not in svc.vault.masked()


def test_validation_rejects_bad_ssn_and_keeps_form_open(svc):
    req = svc.create_capture_request(["ssn"], "x")
    assert "ssn" in svc.complete_capture_request(req["id"], {"ssn": "000-12-3456"})
    assert svc.pending_requests()[0]["id"] == req["id"]


def test_no_tool_result_ever_contains_raw_pii(svc, signature_uri):
    _capture_all(svc)
    svc.save_signature(signature_uri)
    outs = [run_tool(svc, "get_intake_status", {})]
    outs.append(
        run_tool(
            svc,
            "prepare_poa_21_22a",
            {"authorize_7332_records": True, "authorize_address_change": True},
        )
    )
    doc_id = outs[-1].result["document_id"]
    outs.append(
        run_tool(
            svc,
            "update_poa_draft",
            {"document_id": doc_id, "changes": {"address.city": "Waukesha"}},
        )
    )
    outs.append(run_tool(svc, "present_for_signature", {"document_id": doc_id}))
    blob = json.dumps([[o.result, o.cards] for o in outs])
    assert SSN_DIGITS not in blob and SSN not in blob and "1988-04-09" not in blob


def test_agent_cannot_edit_secret_fields(svc):
    _capture_all(svc)
    doc = svc.prepare({"authorize_7332_records": False, "authorize_address_change": False})
    out = run_tool(
        svc, "update_poa_draft", {"document_id": doc.id, "changes": {"ssn": "987654321"}}
    )
    assert out.is_error and "secure form" in out.result["error"]


def test_no_tool_can_sign():
    assert not any("sign" == t["name"] or t["name"].startswith("sign") for t in TOOLS)


def test_sign_requires_complete_draft_saved_signature_and_shown_consent(svc, signature_uri):
    req = svc.create_capture_request(["first_name"], "x")
    svc.complete_capture_request(req["id"], {"first_name": "Jordan"})
    doc = svc.prepare({"authorize_7332_records": True, "authorize_address_change": True})
    with pytest.raises(WorkflowError, match="missing"):
        svc.sign(doc.id, consent_text=ESIGN_CONSENT, ip="127.0.0.1", user_agent="t")
    _capture_all(svc)
    doc = svc.prepare({"authorize_7332_records": True, "authorize_address_change": True})
    with pytest.raises(WorkflowError, match="signature"):
        svc.sign(doc.id, consent_text=ESIGN_CONSENT, ip="127.0.0.1", user_agent="t")
    svc.save_signature(signature_uri)
    with pytest.raises(WorkflowError, match="consent"):
        svc.sign(doc.id, consent_text="ok", ip="127.0.0.1", user_agent="t")


def test_click_to_sign_stamps_23a_dates_23b_and_audits_without_pii(svc, signature_uri):
    _capture_all(svc)
    svc.save_signature(signature_uri)
    doc = svc.prepare({"authorize_7332_records": True, "authorize_address_change": False})
    draft = svc.document_pdf(doc.id)
    signed_doc = svc.sign(doc.id, consent_text=ESIGN_CONSENT, ip="127.0.0.1", user_agent="pytest")
    signed = svc.document_pdf(doc.id)
    assert signed_doc.status == "signed" and signed != draft
    fields = {
        k.split(".")[-1]: v.get("/V")
        for k, v in pypdf.PdfReader(io.BytesIO(signed)).get_fields().items()
    }
    assert len(fields["Date_Signed_Year[3]"]) == 4
    page3 = pypdf.PdfReader(io.BytesIO(signed)).pages[2]
    assert "/XObject" in page3["/Resources"]  # the stamped signature image
    with pytest.raises(WorkflowError):
        svc.edit(doc.id, {"address.city": "X"}, actor="user")  # signed docs are frozen
    audit = svc.docs.audit_path.read_text()
    assert "document_signed" in audit and SSN_DIGITS not in audit and "Testveteran" not in audit


def test_preparing_again_supersedes_the_old_draft(svc):
    _capture_all(svc)
    a = svc.prepare({"authorize_7332_records": True, "authorize_address_change": True})
    b = svc.prepare({"authorize_7332_records": True, "authorize_address_change": True})
    assert svc.docs.get(a.id).status == "superseded" and svc.docs.get(b.id).status == "draft"
