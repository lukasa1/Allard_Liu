from conftest import VETERAN
from fastapi.testclient import TestClient

from demo.server import app


def test_full_manual_flow_over_http(signature_uri):
    c = TestClient(app)
    assert c.get("/").status_code == 200 and "poa_session" in c.cookies
    req = c.post(
        "/api/tool",
        json={"name": "request_secure_info", "args": {"fields": list(VETERAN), "purpose": "t"}},
    ).json()
    rid = req["cards"][0]["request_id"]
    assert c.post(f"/api/secure/{rid}", json={"values": VETERAN}).json()["errors"] == {}
    assert c.post("/api/signature", json={"data_uri": signature_uri}).status_code == 200
    prep = c.post(
        "/api/tool",
        json={
            "name": "prepare_poa_21_22a",
            "args": {"authorize_7332_records": True, "authorize_address_change": True},
        },
    ).json()
    doc = prep["result"]["document_id"]
    assert (
        c.post(
            f"/api/documents/{doc}/edit", json={"changes": {"address.city": "Waukesha"}}
        ).status_code
        == 200
    )
    card = c.post(
        "/api/tool", json={"name": "present_for_signature", "args": {"document_id": doc}}
    ).json()["cards"][0]
    signed = c.post(
        f"/api/documents/{doc}/sign", json={"consent_text": card["consent_text"]}
    ).json()
    assert signed["document"]["status"] == "signed"
    pdf = c.get(f"/api/documents/{doc}/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")


def test_documents_are_session_scoped():
    a, b = TestClient(app), TestClient(app)
    a.get("/"), b.get("/")
    assert b.get("/api/documents/doc_000000000000/pdf").status_code == 404
