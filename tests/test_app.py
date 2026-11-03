"""The full-flow web demo (demo/app.py), offline: what a tester clicks through."""

from fastapi.testclient import TestClient

import pytest

from demo.app import _cases, app


@pytest.fixture(autouse=True)
def _va_sign_in_on(monkeypatch):
    """Most tests here exercise the VA sign-in path, which is off by default."""
    monkeypatch.setenv("INTAKE_VA_SIGN_IN", "1")


class _Client(TestClient):
    """Sends X-Case-Id for the case it last started, like the page does."""

    case_id: str | None = None

    def request(self, method, url, **kw):
        new = str(url).startswith("/api/case/new")
        if self.case_id and not new:
            kw["headers"] = {"X-Case-Id": self.case_id, **(kw.get("headers") or {})}
        r = super().request(method, url, **kw)
        if new and r.status_code == 200:
            self.case_id = r.json()["case"]["case_id"]
        return r


def _client():
    c = _Client(app)
    assert c.get("/").status_code == 200
    return c


def test_config_lists_test_veterans_and_modes():
    cfg = _client().get("/api/config").json()
    assert cfg["provider"] == "offline" and cfg["lighthouse_mode"] == "stub"
    assert len(cfg["personas"]) >= 14 and "fetch_confirm" in cfg["records_modes"]


def test_autoplay_runs_a_case_to_attorney_review():
    c = _client()
    r = c.post(
        "/api/case/new", json={"persona_id": "recent_decision", "records_mode": "fetch_confirm"}
    ).json()
    assert [x["type"] for x in r["cards"]] == ["va_sign_in"]
    for _ in range(200):
        r = c.post("/api/autoplay").json()
        if r.get("done") or r["case"]["phase"] in ("attorney_review", "closed", "human_handoff"):
            break
    case = c.get("/api/case").json()["case"]
    assert case["phase"] == "attorney_review" and case["face_note"].startswith("FA 30%")
    pdf = c.get(f"/api/documents/{case['poa_document_id']}/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_manual_cards_by_hand(signature_uri):
    from conftest import VETERAN

    c = _client()
    c.post("/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "fetch"})
    r = c.post("/api/va/sign-in", json={}).json()
    assert "attorney or law firm" in r["messages"][-1]
    r = c.post("/api/chat", json={"text": "No."}).json()
    form = next(x for x in r["cards"] if x["type"] == "secure_form")
    values = {f["name"]: VETERAN.get(f["name"], "") for f in form["fields"]}
    bad = c.post(
        f"/api/secure/{form['request_id']}", json={"values": {**values, "ssn": "12"}}
    ).json()
    assert "ssn" in bad["errors"]
    form2 = c.get("/api/case").json()  # the request is still pending after a validation error
    assert form2["case"]["phase"] == "poa"
    r = c.post(f"/api/secure/{form['request_id']}", json={"values": values}).json()
    assert r["errors"] == {} and "drug or alcohol" in r["messages"][-1]
    c.post("/api/chat", json={"text": "No."})
    r = c.post("/api/chat", json={"text": "Yes."}).json()
    doc = next(x for x in r["cards"] if x["type"] == "document_preview")["document_id"]
    r = c.post(f"/api/documents/{doc}/edit", json={"changes": {"address.city": "Waukesha"}}).json()
    assert r["document"]["version"] == 2 and r["captured"]["address.city"] == "Waukesha"
    r = c.post("/api/chat", json={"text": "Looks good"}).json()
    assert any(x["type"] == "signature_pad" for x in r["cards"])
    r = c.post("/api/signature", json={"data_uri": signature_uri}).json()
    button = next(x for x in r["cards"] if x["type"] == "sign_button")
    r = c.post(f"/api/documents/{doc}/sign", json={"consent_text": button["consent_text"]}).json()
    assert r["document"]["status"] == "signed" and r["case"]["phase"] == "attorney_signoff"
    assert not r["case"]["poa_submitted"]  # nothing is filed before the attorney countersigns
    assert any(x["type"] == "attorney_signoff" for x in r["cards"])
    r = c.post("/api/attorney/countersign", json={}).json()
    assert r["case"]["poa_submitted"] and r["case"]["intent_to_file"] and r["case"]["phase"] == "intake"


def test_suggest_and_errors():
    c = _client()
    assert c.post("/api/chat", json={"text": "hi"}).status_code in (409, 200)
    c.post("/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "ask"})
    c.post("/api/va/skip")
    assert c.post("/api/suggest").json()["text"] == "Yes."
    assert (
        c.post(
            "/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "nope"}
        ).status_code
        == 400
    )


def test_stale_requests_and_forms_after_a_hand_off_are_refused():
    c = _client()
    old = c.post(
        "/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "ask"}
    ).json()
    new = c.post("/api/case/new", json={"persona_id": "rated_100", "records_mode": "ask"}).json()
    assert c.post("/api/autoplay", headers={"X-Case-Id": old["case"]["case_id"]}).status_code == 409
    assert c.post("/api/autoplay", headers={"X-Case-Id": new["case"]["case_id"]}).status_code == 200
    # a form action outside the 21-22a step (here: still at VA sign-in) is refused
    assert c.post("/api/signature", json={"data_uri": "data:image/png;base64,x"}).status_code == 409


def _dc(c):
    return next(d for d in _cases.values() if d.session.case.case_id == c.case_id)


def _to_sign_card(c, signature_uri, persona="baseline_clean"):
    """Drive a case by hand up to the Sign card; returns (document id, sign card)."""
    from conftest import VETERAN

    c.post("/api/case/new", json={"persona_id": persona, "records_mode": "fetch"})
    c.post("/api/va/sign-in", json={})
    r = c.post("/api/chat", json={"text": "No."}).json()
    form = next(x for x in r["cards"] if x["type"] == "secure_form")
    values = {f["name"]: VETERAN.get(f["name"], "") for f in form["fields"]}
    c.post(f"/api/secure/{form['request_id']}", json={"values": values})
    c.post("/api/chat", json={"text": "No."})
    r = c.post("/api/chat", json={"text": "Yes."}).json()
    doc = next(x for x in r["cards"] if x["type"] == "document_preview")["document_id"]
    c.post("/api/chat", json={"text": "Looks good"})
    r = c.post("/api/signature", json={"data_uri": signature_uri}).json()
    return doc, next(x for x in r["cards"] if x["type"] == "sign_button")


def test_case_id_is_required():
    c = _client()
    r = c.post("/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "ask"}).json()
    bare = TestClient(app, cookies=dict(c.cookies))
    assert bare.post("/api/autoplay").status_code == 409
    assert bare.get("/api/case").status_code == 409
    assert bare.get("/api/config").status_code == 200
    ok = bare.get("/api/case", params={"case": r["case"]["case_id"]})  # the PDF iframe's way
    assert ok.status_code == 200


def test_edit_after_sign_card_needs_a_fresh_review(signature_uri):
    c = _client()
    doc, button = _to_sign_card(c, signature_uri)
    r = c.post(f"/api/documents/{doc}/edit", json={"changes": {"address.city": "Waukesha"}}).json()
    assert r["document"]["version"] == 2

    def sign():
        return c.post(f"/api/documents/{doc}/sign", json={"consent_text": button["consent_text"]})

    assert sign().status_code == 409  # the old card is gone
    # auto-play must not sign the edited draft either: it answers the review question instead
    r = c.post("/api/autoplay").json()
    assert r.get("veteran_text") and r["case"]["poa_document_id"] is None
    assert any(x["type"] == "sign_button" for x in r["cards"])  # re-reviewed: a new Sign card
    assert sign().status_code == 200


def test_signature_must_be_a_real_png(signature_uri):
    c = _client()
    _to_sign_card(c, signature_uri)
    for bad in (
        "data:image/png;base64,x",
        "data:image/png;base64,aGVsbG8=",
        "data:image/gif;base64,R0lG",
    ):
        assert c.post("/api/signature", json={"data_uri": bad}).status_code == 400


def test_superseded_sign_card_is_dropped_and_harmless(signature_uri):
    from intake_eval.runner import act_on_card, queue_cards

    c = _client()
    _, button = _to_sign_card(c, signature_uri)
    dc = _dc(c)
    dc.session.svc.prepare(
        {"authorize_7332_records": False, "authorize_address_change": False}
    )  # supersedes doc
    turn, note = act_on_card(dc.session, dc.persona, button, dc.records_mode)
    assert turn is None and "no longer valid" in note
    newer = {**button, "document_id": "other"}
    assert queue_cards([button, {"type": "va_sign_in"}], [newer]) == [{"type": "va_sign_in"}, newer]


def test_simulator_failure_is_a_clean_error():
    class Broken:
        def respond(self, *_):
            raise RuntimeError("refused")

    c = _client()
    c.post("/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "ask"})
    c.post("/api/va/skip")
    _dc(c).simulator = Broken()
    r = c.post("/api/autoplay")
    assert r.status_code == 503 and "RuntimeError" in r.json()["detail"]


def test_a_server_restart_resumes_the_case_for_the_same_browser_only():
    c = _client()
    c.post("/api/case/new", json={"persona_id": "recent_decision", "records_mode": "fetch_confirm"})
    for _ in range(8):  # into the 21-22a step, with cards open
        r = c.post("/api/autoplay").json()
    phase = r["case"]["phase"]
    assert phase == "poa"
    _cases.clear()  # the server restarts: nothing in memory

    other = _Client(app)
    other.get("/")
    other.case_id = c.case_id  # another browser that knows the case id
    assert other.get("/api/case").status_code == 409

    assert c.get("/api/case").json()["case"]["phase"] == phase  # resumed from disk
    for _ in range(200):
        r = c.post("/api/autoplay").json()
        if r.get("done") or r["case"]["phase"] in ("attorney_review", "closed", "human_handoff"):
            break
    assert c.get("/api/case").json()["case"]["phase"] == "attorney_review"


def test_va_sign_in_is_off_by_default(monkeypatch):
    monkeypatch.delenv("INTAKE_VA_SIGN_IN", raising=False)
    c = _client()
    assert c.get("/api/config").json()["records_modes"] == ["ask"]
    assert c.post("/api/case/new", json={"persona_id": "baseline_clean", "records_mode": "fetch"}).status_code == 400
    r = c.post("/api/case/new", json={"persona_id": "baseline_clean"}).json()
    assert not any(x["type"] == "va_sign_in" for x in r["cards"])  # pass 1 starts asking
    assert r["case"]["phase"] == "screening" and r["case"]["va_consent"] == "not_offered"
