"""Lighthouse tools: stub shapes, the records -> intake mapping, and the sandbox client."""

import json
from datetime import date

import httpx
import pytest

from agent.lighthouse import LighthouseError, SandboxLighthouse, StubLighthouse
from agent.lighthouse.client import record_sandbox
from agent.lighthouse.records import VaRecords
from agent.personas import get_persona


def test_stub_uses_va_shapes_and_enums():
    p = get_persona("oth_one_of_two")
    rec = StubLighthouse().fetch_records(p.icn)
    ep = rec.service_history["data"][1]
    assert ep["type"] == "service-history-episodes"
    assert ep["attributes"]["discharge_status"] == "other-than-honorable"
    assert rec.veteran_status["data"]["attributes"]["veteran_status"] == "confirmed"
    assert [x.discharge for x in rec.service_periods()] == ["honorable", "oth"]


def test_omit_periods_models_incomplete_records():
    p = get_persona("reserve_not_in_records")
    rec = StubLighthouse().fetch_records(p.icn)
    assert len(p.truth.service_periods) == 2 and len(rec.service_periods()) == 1


def test_mapping_is_conservative():
    vet = get_persona("not_a_veteran")
    values = StubLighthouse().fetch_records(vet.icn).intake_values()
    assert "is_veteran" not in values  # "not confirmed" is asked, never assumed False
    hale = get_persona("prior_attorney")
    values = StubLighthouse().fetch_records(hale.icn).intake_values()
    assert values["prior_attorney"] is True and values["prior_attorney_name"] == "Alan Smith"
    assert values["rating_pct"] == 40 and values["filed_before"] is True
    clean = StubLighthouse().fetch_records(get_persona("baseline_clean").icn).intake_values()
    assert "prior_attorney" not in clean  # no active POA doesn't prove there was never one
    assert "receiving_va_pay" not in clean  # no rating on file settles nothing


def test_vso_does_not_count_as_a_prior_attorney():
    rec = VaRecords(
        icn="x",
        mode="stub",
        active_poa={
            "data": {
                "attributes": {
                    "representative": {
                        "service_organization": {
                            "first_name": "A",
                            "last_name": "B",
                            "organization_name": "DAV",
                        }
                    }
                }
            }
        },
    )
    assert rec.private_representative() is None


def test_unknown_icn_raises():
    with pytest.raises(LighthouseError):
        StubLighthouse().fetch_records("nope")


def test_sandbox_client_calls_the_spec_paths_and_keeps_partial_results(monkeypatch):
    monkeypatch.setenv("VA_VSHE_ACCESS_TOKEN", "t1")
    monkeypatch.setenv("VA_CLAIMS_ACCESS_TOKEN", "t2")
    monkeypatch.setenv("VA_TOKEN_ICN", "123")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["authorization"]))
        if request.url.path.endswith("/service_history"):
            return httpx.Response(200, json={"data": []})
        if request.url.path.endswith("/forms/2122/active"):
            return httpx.Response(404, json={})
        if request.url.path.endswith("/claims"):
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"data": {}})

    client = httpx.Client(
        base_url="https://sandbox-api.va.gov/services", transport=httpx.MockTransport(handler)
    )
    rec = SandboxLighthouse(client=client).fetch_records("123")
    assert ("/services/veteran_verification/v2/service_history", "Bearer t1") in seen
    assert ("/services/claims/v1/claims", "Bearer t2") in seen
    assert rec.service_history == {"data": []} and rec.active_poa is None
    assert "claims" in rec.errors and json.dumps(rec.model_dump())


def test_sandbox_needs_tokens(monkeypatch):
    monkeypatch.delenv("VA_VSHE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("VA_CLAIMS_ACCESS_TOKEN", raising=False)
    with pytest.raises(LighthouseError):
        SandboxLighthouse(client=object())


def test_stub_status_uses_the_spec_value_and_still_parses():
    rec = StubLighthouse().fetch_records(get_persona("not_a_veteran").icn)
    assert rec.veteran_status["data"]["attributes"]["veteran_status"] == "not_confirmed"
    assert rec.confirmed_veteran() is None


def test_stub_itf_uses_va_datetimes_and_is_normalized():
    lh = StubLighthouse()
    icn = get_persona("baseline_clean").icn
    itf = lh.submit_intent_to_file(icn)
    raw = itf["raw"]["data"]["attributes"]["creation_date"]
    assert "T" in raw and raw[-6] in "+-"  # "2025-02-07T09:17:18-06:00", like VA
    assert date.fromisoformat(itf["date"]) and date.fromisoformat(itf["expires"])
    assert itf["status"] == "active"


def test_stub_poa_is_pending_without_the_signed_pdf():
    lh = StubLighthouse()
    icn = get_persona("baseline_clean").icn
    assert lh.submit_poa(icn, {"poa_code": "A1Q"})["status"] == "pending"
    r = lh.submit_poa(icn, {"poa_code": "A1Q"}, signed_pdf=b"%PDF-1.4")
    assert r["status"] == "submitted" and r["signed_pdf_uploaded"] and r["id"]
    assert lh.submissions[-1]["endpoint"] == f"PUT /forms/2122/{r['id']}"


def _sandbox(monkeypatch, handler, icn="1012667145V762142"):
    monkeypatch.setenv("VA_CLAIMS_ACCESS_TOKEN", "t2")
    monkeypatch.setenv("VA_TOKEN_ICN", icn)
    client = httpx.Client(
        base_url="https://sandbox-api.va.gov/services", transport=httpx.MockTransport(handler)
    )
    return SandboxLighthouse(client=client)


def _poa_resp(status, poa_id="poa-1"):
    return {"data": {"id": poa_id, "type": "claims_api_power_of_attorneys", "attributes": {
        "status": status, "date_request_accepted": "2024-01-01", "previous_poa": None,
        "representative": {"service_organization": {"poa_code": "A1Q"}}}}}  # fmt: skip


def test_sandbox_poa_posts_then_puts_the_signed_pdf(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("content-type", "")))
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["data"]["attributes"]["serviceOrganization"]["poaCode"] == "A1Q"
            return httpx.Response(200, json=_poa_resp("pending"))
        assert b"%PDF-1.4" in request.content and b'name="attachment"' in request.content
        return httpx.Response(200, json=_poa_resp("submitted"))

    lh = _sandbox(monkeypatch, handler)
    r = lh.submit_poa("1012667145V762142", {"poa_code": "A1Q"}, signed_pdf=b"%PDF-1.4 x")
    assert [s[:2] for s in seen] == [
        ("POST", "/services/claims/v1/forms/2122"),
        ("PUT", "/services/claims/v1/forms/2122/poa-1"),
    ]
    assert seen[1][2].startswith("multipart/form-data")
    assert r["status"] == "submitted" and r["id"] == "poa-1" and r["raw"]["data"]["id"] == "poa-1"


def test_sandbox_poa_keeps_the_post_when_the_upload_fails(monkeypatch):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json=_poa_resp("pending"))
        return httpx.Response(400, json={"errors": [{"title": "Missing parameter",
                              "detail": "Must include attachment", "code": "108", "status": "400"}]})  # fmt: skip

    r = _sandbox(monkeypatch, handler).submit_poa("1012667145V762142", {"poa_code": "A1Q"}, b"x")
    assert r["status"] == "pending" and not r["signed_pdf_uploaded"]
    assert "Must include attachment" in r["upload_error"]


def test_sandbox_poa_refuses_without_a_poa_code(monkeypatch):
    lh = _sandbox(monkeypatch, lambda r: pytest.fail("must not call VA"))
    with pytest.raises(LighthouseError, match="poa_code"):
        lh.submit_poa("1012667145V762142", {"poa_code": ""}, b"%PDF")


def test_sandbox_refuses_a_case_icn_that_is_not_the_token_user(monkeypatch):
    lh = _sandbox(monkeypatch, lambda r: pytest.fail("must not call VA"))
    for call in (
        lambda: lh.fetch_records("999"),
        lambda: lh.submit_intent_to_file("999"),
        lambda: lh.submit_poa("999", {"poa_code": "A1Q"}),
    ):
        with pytest.raises(LighthouseError, match="not the access tokens' user"):
            call()
    monkeypatch.delenv("VA_TOKEN_ICN")
    with pytest.raises(LighthouseError, match="VA_TOKEN_ICN"):
        SandboxLighthouse(client=object()).fetch_records("999")


def test_record_sandbox_saves_nothing_for_another_icn(monkeypatch, tmp_path):
    monkeypatch.setenv("VA_VSHE_ACCESS_TOKEN", "t1")
    monkeypatch.setenv("VA_TOKEN_ICN", "1012667145V762142")
    with pytest.raises(LighthouseError):
        record_sandbox("999", "x", directory=tmp_path)
    assert not any(tmp_path.iterdir())


def test_sandbox_refuses_records_echoing_another_icn(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": {"id": "OTHER", "attributes": {}}})

    monkeypatch.setenv("VA_VSHE_ACCESS_TOKEN", "t1")
    with pytest.raises(LighthouseError, match="OTHER"):
        _sandbox(monkeypatch, handler).fetch_records("1012667145V762142")


def test_sandbox_itf_normalizes_the_spec_response(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": {"id": "294045", "type": "intent_to_file",
            "attributes": {"creation_date": "2025-02-07T09:17:18-06:00",
                           "expiration_date": "2026-02-07T07:12:40-06:00",
                           "type": "compensation", "status": "duplicate"}}})  # fmt: skip

    itf = _sandbox(monkeypatch, handler).submit_intent_to_file("1012667145V762142")
    assert itf["date"] == "2025-02-07" and itf["expires"] == "2026-02-07"
    assert itf["status"] == "duplicate" and itf["raw"]["data"]["id"] == "294045"


def test_sandbox_errors_carry_vas_error_details(monkeypatch):
    def handler(request):
        return httpx.Response(422, json={"errors": [{"status": 422, "source": "/type",
                              "detail": "The property /type did not match"}]})  # fmt: skip

    match = r"HTTP 422: The property /type did not match \(/type\)"
    with pytest.raises(LighthouseError, match=match):
        _sandbox(monkeypatch, handler).submit_intent_to_file("1012667145V762142")
