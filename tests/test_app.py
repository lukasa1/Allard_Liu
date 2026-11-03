"""The web demo (demo/app.py) through its HTTP API, on the runtime with the scripted fake LM:
the whole demo flow as a presenter clicks it, the outbox polling, and the no-key page (D7)."""

import io
import threading

import pypdf
import pytest
from conftest import VETERAN
from fastapi.testclient import TestClient
from helpers import events, until
from intake_fixtures import SCREEN_STEPS, prefill_pass2

from agent.intake import checklist
from agent.scripted.lm import call, final, pause
from agent.scripted.prep import prep_steps
from demo.app import app, get_runtime

PERSONA = "baseline_clean"


@pytest.fixture
def client(rt):
    app.dependency_overrides[get_runtime] = lambda: rt
    yield TestClient(app)
    app.dependency_overrides.clear()


class Demo:
    """The page: posts like the buttons do and reads the outbox like the poller does."""

    def __init__(self, client, rt, case_id):
        self.c, self.rt, self.id, self.seen = client, rt, case_id, []

    def post(self, path, body=None, status=200):
        r = self.c.post(f"/api/cases/{self.id}{path}", json=body or {})
        assert r.status_code == status, r.text
        self.rt.wait_until_idle()
        return r.json()

    def say(self, text):
        return self.post("/messages", {"text": text})

    def poll(self):
        since = self.seen[-1]["seq"] if self.seen else 0
        items = self.c.get(f"/api/cases/{self.id}/updates", params={"since": since}).json()["items"]
        self.seen += items
        return items

    def card(self, type):
        self.poll()
        return [o["payload"] for o in self.seen if o["kind"] == "card" and o["payload"]["type"] == type][-1]

    def panel(self):
        return self.c.get(f"/api/cases/{self.id}").json()


def test_the_demo_flow_through_the_http_api(client, rt, lm, signature_uri):
    assert client.get("/").status_code == 200
    cfg = client.get("/api/config").json()
    assert cfg["ready"] and cfg["message"] is None and PERSONA in {p["id"] for p in cfg["personas"]}

    lm.turn("orchestrator", call("run_intake", goal="Pass 1: screen, sign, file."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    cid = client.post("/api/cases", json={"persona_id": PERSONA}).json()["case_id"]
    rt.wait_until_idle()
    d = Demo(client, rt, cid)
    assert [(o["agent"], o["payload"]["text"]) for o in d.poll()] == [
        ("orchestrator", "Welcome!"), ("intake", "Have you served in the military?")]  # fmt: skip
    assert d.poll() == []  # since=<last seq>: nothing new
    d.post("/countersign", status=409)  # nothing is waiting for the attorney yet

    # Pass 1: screening, the secure form, the 21-22a and the fee agreement.
    lm.turn("intake", *SCREEN_STEPS, call("request_secure_info", fields=list(VETERAN), purpose="For the 21-22a."),
            final(reply="Please fill in the secure form."))  # fmt: skip
    d.say("Yes. Army 2004-06 to 2010-05, honorable. Never filed. No lawyer.")
    lm.turn("intake", call("fill_pdf", form="21-22a", fields={"authorize_7332_records": True,
            "authorize_address_change": False}), final(reply="Here is your 21-22a. Does it look right?"))  # fmt: skip
    assert d.post(f"/secure/{d.card('secure_form')['request_id']}", {"values": VETERAN}) == {"errors": {}}
    assert d.c.get(f"/api/cases/{cid}/documents/21-22a.pdf").content.startswith(b"%PDF")

    lm.turn("intake", call("get_signature", form="21-22a"), final(reply="Please draw your signature."))
    d.say("Yes, it's right.")
    lm.turn("intake", call("get_signature", form="21-22a"), final(reply="Click Sign when you're ready."))
    d.post("/signature", {"data_uri": "data:image/png;base64,AAAA"}, status=400)
    d.post("/signature", {"data_uri": signature_uri})
    poa = d.card("sign_button")
    lm.turn("intake", call("fill_pdf", form="fee_agreement", fields={}),
            final(reply="Here's the fee agreement: 30% of past-due benefits, only if you win. Do you agree?"))  # fmt: skip
    d.post("/sign/21-22a", {"consent_text": poa["consent_text"]})
    assert d.card("document_preview")["form"] == "fee_agreement"
    d.post("/sign/fee_agreement", {"consent_text": "x"}, status=409)  # no Sign card for it yet

    lm.turn("intake", call("get_signature", form="fee_agreement"), final(reply="Click Sign to sign it."))
    d.say("Yes, I agree.")
    lm.turn("intake", final(reply="Our attorney is reviewing both documents now."))
    d.post("/sign/fee_agreement", {"consent_text": d.card("sign_button")["consent_text"]})
    p = d.panel()
    assert (p["stage"], p["owner"], p["side_state"], p["can_countersign"]) == (2, "intake", "waiting_on_attorney", True)
    assert {f: x["status"] for f, x in p["documents"].items()} == {"21-22a": "signed", "fee_agreement": "signed"}

    # The attorney countersigns both (D6) -> intake files -> claims prep in the background.
    gate = threading.Event()
    pass1 = {"finished": "pass 1: 21-22a and ITF filed, fee agreement faxed"}
    lm.turn("intake", call("submit_va", form="21-22a"), call("submit_va", form="itf"),
            call("efax_ogc", doc="fee_agreement"), final(reply="Filed with VA!", result=pass1))  # fmt: skip
    lm.turn("orchestrator", call("run_prep", goal="Pull and read the C-file, prefill, face note."),
            final(reply="We've asked VA for your file."))  # fmt: skip
    lm.turn("claims_prep", pause(gate), *prep_steps(PERSONA), final(result={"finished": "face note verified"}))
    lm.turn("orchestrator", call("run_intake", goal="Pass 2: ask only the gaps."), final())
    lm.turn("intake", final(reply="Any other conditions besides tinnitus?"))
    client.post(f"/api/cases/{cid}/countersign").raise_for_status()
    until(lambda: any(s.agent == "claims_prep" for s in lm.seen))
    assert d.panel()["documents"]["21-22a"]["status"] == "countersigned"
    stamped = pypdf.PdfReader(io.BytesIO(d.c.get(f"/api/cases/{cid}/documents/fee_agreement.pdf").content))
    assert f"/s/ {cfg['attorney']}" in "".join(pg.extract_text() for pg in stamped.pages)
    filed = [o["payload"] for o in d.poll() if o["payload"].get("type") == "filed"]
    assert [(f["form"], f["confirmation"][:3]) for f in filed] == [("21-22a", "VA-"), ("itf", "VA-"), ("fee_agreement", "FAX")]
    assert client.post(f"/api/cases/{cid}/countersign").status_code == 409  # only in waiting_on_attorney

    # While claims prep runs, support answers the chat (D1), and polling delivers it.
    lm.turn("support", call("log_event", kind="status", text="Asked for status; told the file is being read."),
            final(reply="Our team is reading your VA file now."))  # fmt: skip
    client.post(f"/api/cases/{cid}/messages", json={"text": "What's happening with my case?"}).raise_for_status()
    until(lambda: any(o["payload"].get("text") == "Our team is reading your VA file now." for o in d.poll()))
    gate.set()
    rt.wait_until_idle()
    p = d.panel()
    assert (p["stage"], p["owner"], p["prep"]["done"], p["prep"]["verified"]) == (4, "intake", True, True)
    assert p["face_note"][0].startswith("FA 30%") and p["answers"]["mos"]["source"] == "C-file p. 1"

    # Pass 2 (its many answers are test_intake_agent's), then ready for attorney review.
    def answered(c):
        prefill_pass2(c, leave=("other_conditions",))
        checklist.refresh(c)

    rt.patch(cid, answered, actor="intake")
    lm.turn("intake", call("record_answer", q="other_conditions", a="None"),
            final(reply="Thank you, that's everything.", result={"finished": "pass 2: gaps closed"}))  # fmt: skip
    lm.turn("orchestrator", final())
    d.say("No others.")
    p = d.panel()
    assert (p["stage"], p["stage_name"], p["owner"]) == (5, "gaps closed (ready for attorney review)", None)

    # The case panel: decisions, the event log with support's events, filings, tasks and cost.
    assert [e["data"]["to"] for e in p["decisions"] if e["type"] == "handoff"] == ["intake", "claims_prep", "intake"]
    assert [e.data["to"] for e in events(rt, cid, "stage_changed")] == [2, 3, 4, 5]
    results = [e.data["result"] for e in events(rt, cid, "subagent_result")]
    assert [(r["agent"], r["finished"]) for r in results] == [
        ("intake", pass1["finished"]), ("claims_prep", "face note verified"), ("intake", "pass 2: gaps closed")]  # fmt: skip
    # The orchestrator's memory block never holds a transcript.
    assert not any("it's right" in m or "No others" in m for m in lm.prompts("orchestrator"))
    types = {e["type"] for e in p["events"]}
    assert {"countersigned", "cfile_pulled", "support_log", "subagent_result"} <= types and "message" not in types
    assert set(p["filings"]) == {"21-22a", "itf", "fee_agreement"}
    assert set(p["cost"]["by_agent"]) == {"orchestrator", "intake", "claims_prep", "support"}
    assert p["cost"]["total"] > 0
    d.poll()
    seqs = [o["seq"] for o in d.seen]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    texts = [o["payload"]["text"] for o in d.seen if o["kind"] == "message"]
    assert texts.index("Filed with VA!") < texts.index("We've asked VA for your file.") < texts.index(
        "Any other conditions besides tinnitus?") < texts.index("Thank you, that's everything.")  # fmt: skip


def test_an_ssn_typed_in_chat_is_hidden_before_it_is_shown_or_routed(client, rt, lm):
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Did you serve?"))
    cid = client.post("/api/cases", json={"persona_id": PERSONA}).json()["case_id"]
    rt.wait_until_idle()
    lm.turn("intake", final(reply="Please use the secure form for that."))
    shown = Demo(client, rt, cid).say("My SSN is 123-45-6789")["text"]
    assert "123-45-6789" not in shown and "hidden" in shown
    assert not any("123-45-6789" in s.user for s in lm.seen)


def test_unknown_cases_and_personas_are_refused(client):
    assert client.post("/api/cases", json={"persona_id": "nobody"}).status_code == 404
    assert client.get("/api/cases/nope").status_code == 404
    assert client.post("/api/cases/nope/countersign").status_code == 404


def test_with_no_key_the_page_loads_and_says_to_set_it():
    app.dependency_overrides.clear()  # the real dependency; conftest empties OPENROUTER_API_KEY
    c = TestClient(app)
    assert c.get("/").status_code == 200
    cfg = c.get("/api/config").json()
    assert not cfg["ready"] and "OPENROUTER_API_KEY" in cfg["message"] and cfg["personas"]
    r = c.post("/api/cases", json={"persona_id": PERSONA})
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]
    assert c.post("/api/cases/any/suggest").status_code == 503


def test_autoplay_suggests_the_simulated_veterans_next_reply(client, rt, lm, monkeypatch):
    from dspy.utils.dummies import DummyLM

    import demo.app as demo_app

    sim_lm = DummyLM([{"reply": "Yes, Army, 2004 to 2010."}])
    sim_lm.copy = lambda **kw: sim_lm  # keep its history readable here
    monkeypatch.setattr(demo_app, "simulator_lm", lambda: sim_lm)
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    cid = client.post("/api/cases", json={"persona_id": PERSONA}).json()["case_id"]
    rt.wait_until_idle()
    assert client.post(f"/api/cases/{cid}/suggest").json() == {"text": "Yes, Army, 2004 to 2010."}
    prompt = sim_lm.history[-1]["messages"][-1]["content"]
    assert "Welcome!" in prompt and "Have you served in the military?" in prompt
    assert rt.store.events(cid, types=("message",))[-1].data["from"] == "intake"  # nothing was sent


def test_autoplay_waits_while_an_agent_is_mid_turn(client, rt, lm, monkeypatch):
    lm.turn("orchestrator", call("run_intake", goal="Pass 1."), final(reply="Welcome!"))
    lm.turn("intake", final(reply="Have you served in the military?"))
    cid = client.post("/api/cases", json={"persona_id": PERSONA}).json()["case_id"]
    rt.wait_until_idle()
    monkeypatch.setattr(rt, "busy", lambda case_id: True)
    monkeypatch.setattr(rt, "running", lambda case_id: {"claims_prep"})
    r = client.post(f"/api/cases/{cid}/suggest")
    assert r.status_code == 409 and "claims prep is still working" in r.json()["detail"]
    monkeypatch.setattr(rt, "running", lambda case_id: set())  # a turn queued, none running yet
    r = client.post(f"/api/cases/{cid}/suggest")
    assert r.status_code == 409 and "a queued turn is still working" in r.json()["detail"]
    assert client.get(f"/api/cases/{cid}/updates").json()["busy"] is True


def test_the_scripted_demo_plays_one_case_to_attorney_review(monkeypatch, tmp_path, signature_uri):
    """`intake serve --scripted` (D26): no key, no model; Next line + Send and the cards, as the page does."""
    from agent.scripted import demo
    from demo import app as app_module

    monkeypatch.setenv("DEMO_SCRIPTED", "1")
    monkeypatch.setenv("POA_DATA_DIR", str(tmp_path))
    app_module._scripted_runtime.cache_clear()
    c = TestClient(app)
    cfg = c.get("/api/config").json()
    assert cfg["ready"] and cfg["scripted"] and [p["id"] for p in cfg["personas"]] == [demo.PERSONA]
    rt = app_module.get_runtime()
    cid = c.post("/api/cases", json={"persona_id": demo.PERSONA}).json()["case_id"]
    rt.wait_until_idle()
    d = Demo(c, rt, cid)

    def next_line():
        d.say(d.post("/suggest")["text"])

    for _ in range(4):
        next_line()
    assert d.post(
        f"/secure/{d.card('secure_form')['request_id']}", {"values": cfg["secure_sample"]}
    ) == {"errors": {}}
    next_line()
    d.post("/signature", {"data_uri": signature_uri})
    d.post("/sign/21-22a", {"consent_text": d.card("sign_button")["consent_text"]})
    next_line()
    d.post("/sign/fee_agreement", {"consent_text": d.card("sign_button")["consent_text"]})
    d.post("/countersign")
    for _ in demo.PASS2_LINES:
        next_line()
    p = d.panel()
    assert (p["stage"], p["owner"], p["prep"]["verified"]) == (5, None, True)
    assert any(
        line.startswith("   DEADLINE TO FILE AMA APPEAL 03/13/27") for line in p["face_note"]
    )
    assert rt.harness.lm.unused() == {} and p["cost"]["total"] == 0  # no model ran
    assert c.post(f"/api/cases/{cid}/suggest").status_code == 409  # the story is over
    d.say("Thank you.")  # off the script: a fixed note, not the canned failure reply
    assert d.poll()[-1]["payload"]["text"] == demo.OFF_SCRIPT
    app_module._scripted_runtime.cache_clear()
