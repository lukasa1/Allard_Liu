"""Full-flow demo: orchestrator + intake subagent + POA skill + Lighthouse + face note.

Run:  uv run intake serve        then open http://localhost:8000
(or:  uv run uvicorn demo.app:app --port 8000)

Pick a synthetic test veteran and how VA's records are used, then either chat as the veteran or
press "Auto-play" to let a simulated veteran answer, fill the secure form, sign in with VA (stub),
draw a signature and click Sign, one step at a time. With no API key everything runs offline
(rule-based agent: give plain, direct answers, or use "Suggest a reply").

This is the trusted host: it alone touches raw PII (secure form -> vault) and signing (the
user's click -> PoaService.sign). SYNTHETIC DATA ONLY. The original POA-only demo is still at
demo/server.py.

Restarts: every turn saves the case with its subagents' memory and this host's open cards, so after
a server restart the page's next request resumes the case (CaseSession.resume), for the same
browser only. The simulated veteran starts fresh; it only needs the latest agent messages.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import config
from agent.intake.controller import RECORDS_MODES, AgentConfig
from agent.personas import Persona, get_persona, load_personas
from agent.session import CaseSession, SessionTurn, redact_chat
from intake_eval.runner import ACTIONABLE_CARDS, act_on_card, queue_cards
from poa_skill.service import WorkflowError

config.load_env()
app = FastAPI(title="Veteran intake agent demo")
STATIC = Path(__file__).parent / "static"
COOKIE = "intake_demo"


@dataclass
class DemoCase:
    session: CaseSession
    persona: Persona
    records_mode: str
    simulator: Any
    owner: str  # sha256 of the browser's cookie: only that browser may resume the case
    open_cards: list[dict] = field(default_factory=list)  # cards the veteran hasn't acted on yet
    transcript: list[dict[str, str]] = field(default_factory=list)  # what the simulator has seen
    lock: threading.Lock = field(default_factory=threading.Lock)


_cases: dict[str, DemoCase] = {}
_resume_lock = threading.Lock()
TRANSCRIPT_KEPT = 60  # agent/veteran lines kept for the simulated veteran after a restart


def _owner(cookie: str) -> str:
    return hashlib.sha256(cookie.encode()).hexdigest()


def _make_simulator(persona: Persona):
    if _provider() == "dspy":
        from intake_eval.simulator import DSPySimulator

        return DSPySimulator(persona, config.make_lm(role="simulator"))
    from intake_eval.simulator import OfflineSimulator

    return OfflineSimulator(persona)


def _resume(sid: str, case_id: str) -> DemoCase:
    """After a server restart: rebuild this browser's case from disk, or refuse."""
    with _resume_lock:
        if sid in _cases:  # another request resumed it first
            return _cases[sid]
        try:
            session = CaseSession.resume(case_id)
        except (KeyError, ValueError):  # unknown id, or an unreadable / older-version case file
            raise HTTPException(409, "no case yet: press Start") from None
        if sid in _cases:  # a new case was started while this one was loading: keep the new one
            return _cases[sid]
        host = session.host_state.get("demo") or {}
        if session.persona is None or host.get("owner") != _owner(sid):
            raise HTTPException(409, "no case yet: press Start")
        dc = DemoCase(
            session=session, persona=session.persona, records_mode=session.agent_config.records_mode,
            simulator=_make_simulator(session.persona), owner=host["owner"],
            open_cards=list(host.get("open_cards", [])), transcript=list(host.get("transcript", [])),
        )  # fmt: skip
        _cases[sid] = dc
        return dc


def _va_sign_in() -> bool:
    """VA sign-in before representation is off unless the firm turns it on (INTAKE_VA_SIGN_IN=1):
    collecting VA records before the veteran signs needs the firm's approval and VA's."""
    return os.environ.get("INTAKE_VA_SIGN_IN", "") == "1"


def _provider() -> str:
    return config.default_provider()


def _case(sid: str | None, request: Request) -> DemoCase:
    if not sid:
        raise HTTPException(409, "no case yet: press Start")
    # The page sends the id of the case it is showing (header, or ?case= for the PDF iframe); a
    # request from before "Start case" must not act on the new case (e.g. an auto-play step still
    # in flight), and one without an id can't be checked, so it's refused too.
    shown = request.headers.get("x-case-id") or request.query_params.get("case")
    if sid not in _cases:
        if not shown:
            raise HTTPException(409, "no case yet: press Start")
        dc = _resume(sid, shown)
    else:
        dc = _cases[sid]
    if not shown:
        raise HTTPException(409, "missing case id: reload the page")
    if shown != dc.session.case.case_id:
        raise HTTPException(409, "stale request from an earlier case")
    return dc


def _require_poa(dc: DemoCase) -> None:
    """The secure form, signature and Sign only work while the case is in the 21-22a step."""
    if dc.session.case.phase != "poa":
        raise HTTPException(
            409, "This case has moved past the 21-22a step; the form can't be changed here."
        )


def _respond(dc: DemoCase, turn: SessionTurn, **extra: Any) -> dict:
    dc.transcript += [{"role": "agent", "text": m} for m in turn.messages]
    dc.open_cards = queue_cards(
        [c for c in dc.open_cards if c.get("type") in ACTIONABLE_CARDS],
        [c for c in turn.cards if c.get("type") in ACTIONABLE_CARDS],
    )
    _save_host_state(dc)
    return {**turn.to_dict(), "waiting_for_chat": dc.session.waiting_for_chat, **extra}


def _save_host_state(dc: DemoCase) -> None:
    """This host's memory, saved with the case. Veteran lines are redacted like the chat itself."""
    kept = [
        t if t["role"] != "veteran" else {**t, "text": redact_chat(t["text"])[0]}
        for t in dc.transcript[-TRANSCRIPT_KEPT:]
    ]
    dc.session.host_state["demo"] = {"owner": dc.owner, "open_cards": dc.open_cards, "transcript": kept}
    dc.session.save()


def _drop_card(dc: DemoCase, kind: str, key: str | None = None) -> None:
    def match(c: dict) -> bool:
        if c.get("type") != kind:
            return False
        return key is None or key in (c.get("request_id"), c.get("document_id"))

    dc.open_cards = [c for c in dc.open_cards if not match(c)]


@app.get("/")
def index(intake_demo: str | None = Cookie(None)):
    resp = FileResponse(STATIC / "app.html")
    if not intake_demo:
        resp.set_cookie(COOKIE, secrets.token_urlsafe(18), httponly=True, samesite="strict")
    return resp


@app.get("/api/config")
def get_config():
    return {
        "provider": _provider(),
        "lighthouse_mode": os.environ.get("LIGHTHOUSE_MODE", "stub"),
        "records_modes": list(RECORDS_MODES) if _va_sign_in() else ["ask"],
        "va_sign_in": _va_sign_in(),
        "personas": [
            {
                "id": p.id,
                "name": p.display_name,
                "summary": p.summary,
                "expected": p.expected_decision,
            }
            for p in load_personas()
        ],
    }


class NewCase(BaseModel):
    persona_id: str
    records_mode: str = "ask"


@app.post("/api/case/new")
def new_case(body: NewCase, intake_demo: str | None = Cookie(None)):
    if not intake_demo:
        raise HTTPException(401, "reload the page")
    if body.records_mode not in RECORDS_MODES:
        raise HTTPException(400, f"records_mode must be one of {RECORDS_MODES}")
    if body.records_mode != "ask" and not _va_sign_in():
        raise HTTPException(400, "VA sign-in is off (set INTAKE_VA_SIGN_IN=1 to offer it)")
    known = {p.id for p in load_personas()}
    if body.persona_id not in known:
        raise HTTPException(404, f"unknown test veteran {body.persona_id!r}")
    persona = get_persona(body.persona_id)
    session = CaseSession(
        provider=_provider(), persona=persona, agent_config=AgentConfig(records_mode=body.records_mode)
    )
    dc = DemoCase(
        session=session, persona=persona, records_mode=body.records_mode,
        simulator=_make_simulator(persona), owner=_owner(intake_demo),
    )  # fmt: skip
    with _resume_lock:  # a resume of the old case running now must not overwrite this one
        _cases[intake_demo] = dc
    with dc.lock:
        return _respond(dc, session.start())


@app.get("/api/case")
def get_case(request: Request, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    return {"case": dc.session.case_view(), "waiting_for_chat": dc.session.waiting_for_chat}


class Chat(BaseModel):
    text: str


@app.post("/api/chat")
def chat(request: Request, body: Chat, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    with dc.lock:
        dc.transcript.append({"role": "veteran", "text": body.text})
        return _respond(dc, dc.session.message(body.text))


@app.post("/api/suggest")
def suggest(request: Request, intake_demo: str | None = Cookie(None)):
    """What the test veteran would say now (fills the input box; nothing is sent)."""
    dc = _case(intake_demo, request)
    if not dc.session.waiting_for_chat:
        return {"text": ""}
    from intake_eval.simulator import OfflineSimulator

    return {"text": OfflineSimulator(dc.persona).respond("", dc.session.pending)}


@app.post("/api/autoplay")
def autoplay(request: Request, intake_demo: str | None = Cookie(None)):
    """One step as the simulated veteran: use the oldest open card, or answer in chat."""
    dc = _case(intake_demo, request)
    with dc.lock:
        if dc.open_cards:
            card = dc.open_cards.pop(0)
            turn, note = act_on_card(dc.session, dc.persona, card, dc.records_mode)
            if turn is not None:
                return _respond(dc, turn, veteran_action=note, card_done=card)
            if note:  # ignored or no longer valid: say so, the next step goes on
                _save_host_state(dc)  # the card is gone: don't bring it back after a restart
                return {"messages": [], "cards": [], "case": dc.session.case_view(),
                        "waiting_for_chat": dc.session.waiting_for_chat, "veteran_action": note,
                        "card_invalid": card}  # fmt: skip
        if dc.session.waiting_for_chat:
            since: list[str] = []  # every agent message since the veteran last spoke
            for t in reversed(dc.transcript):
                if t["role"] == "veteran":
                    break
                since.insert(0, t["text"])
            try:
                reply = dc.simulator.respond("\n\n".join(since), dc.session.pending)
            except Exception as e:  # a refusal, unparseable output, a 429 after retries
                raise HTTPException(
                    503,
                    f"The simulated veteran's model failed ({type(e).__name__}). Try again, or type a reply.",
                ) from e
            dc.transcript.append({"role": "veteran", "text": reply})
            return _respond(dc, dc.session.message(reply), veteran_text=reply)
        return {
            "messages": [],
            "cards": [],
            "case": dc.session.case_view(),
            "waiting_for_chat": False,
            "done": True,
        }


class SignIn(BaseModel):
    icn: str | None = None


@app.post("/api/va/sign-in")
def va_sign_in(request: Request, body: SignIn, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    with dc.lock:
        _drop_card(dc, "va_sign_in")
        return _respond(dc, dc.session.ui_event("va_sign_in", icn=body.icn or dc.persona.icn))


@app.post("/api/va/skip")
def va_skip(request: Request, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    with dc.lock:
        _drop_card(dc, "va_sign_in")
        return _respond(dc, dc.session.ui_event("va_sign_in_declined"))


@app.post("/api/attorney/countersign")
def attorney_countersign(request: Request, intake_demo: str | None = Cookie(None)):
    """Staff action played by the presenter: the attorney approves filing the 21-22a."""
    dc = _case(intake_demo, request)
    with dc.lock:
        if dc.session.case.phase != "attorney_signoff":
            raise HTTPException(409, "Nothing is waiting for the attorney's countersignature.")
        _drop_card(dc, "attorney_signoff")
        return _respond(dc, dc.session.ui_event("attorney_countersigned", by="attorney (demo)"))


class SecureForm(BaseModel):
    values: dict[str, str]


@app.post("/api/secure/{request_id}")
def secure_submit(
    request: Request, request_id: str, body: SecureForm, intake_demo: str | None = Cookie(None)
):
    dc = _case(intake_demo, request)
    with dc.lock:
        _require_poa(dc)
        try:
            errors = dc.session.svc.complete_capture_request(request_id, body.values)
        except WorkflowError as e:
            raise HTTPException(400, str(e)) from e
        if errors:
            return {"errors": errors}
        _drop_card(dc, "secure_form", request_id)
        return {"errors": {}, **_respond(dc, dc.session.ui_event("secure_form_submitted"))}


class Signature(BaseModel):
    data_uri: str


PNG_PREFIX = "data:image/png;base64,"


def _check_png(data_uri: str) -> None:
    """Reject anything but a real PNG now, not with a 500 when Sign places it."""
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    if not data_uri.startswith(PNG_PREFIX):
        raise HTTPException(400, "signature must be a PNG data URI")
    try:
        raw = base64.b64decode(data_uri[len(PNG_PREFIX) :], validate=True)
        with Image.open(BytesIO(raw)) as img:
            if img.format != "PNG":
                raise ValueError(img.format)
            img.verify()
    except (binascii.Error, UnidentifiedImageError, ValueError, OSError, SyntaxError) as e:
        raise HTTPException(400, "signature is not a valid PNG image") from e


@app.post("/api/signature")
def signature(request: Request, body: Signature, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    with dc.lock:
        _require_poa(dc)
        _check_png(body.data_uri)
        try:
            dc.session.svc.save_signature(body.data_uri)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        _drop_card(dc, "signature_pad")
        return _respond(dc, dc.session.ui_event("signature_saved"))


class Edit(BaseModel):
    changes: dict


@app.post("/api/documents/{doc_id}/edit")
def edit(request: Request, doc_id: str, body: Edit, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    with dc.lock:
        _require_poa(dc)
        svc = dc.session.svc
        try:
            doc = svc.edit(doc_id, body.changes, actor="user")
        except WorkflowError as e:
            raise HTTPException(400, str(e)) from e
        _drop_card(dc, "sign_button", doc_id)  # an edited draft needs a fresh review before Sign
        out = _respond(dc, dc.session.ui_event("draft_edited"))
        return {"document": svc.describe(doc), "captured": svc.vault.masked(), **out}


class SignClick(BaseModel):
    consent_text: str


@app.post("/api/documents/{doc_id}/sign")
def sign(doc_id: str, body: SignClick, request: Request, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    with dc.lock:
        _require_poa(dc)
        # Only a Sign card that is still open signs: an edit after it was shown drops it until the
        # veteran re-reviews. The offline step also says what it waits for; the DSPy step only
        # sets "done" (or None), so None is allowed there and the open card carries the rule.
        waiting = getattr(dc.session.poa, "waiting_for", None)
        open_sign = any(
            c.get("type") == "sign_button" and c.get("document_id") == doc_id for c in dc.open_cards
        )
        if not open_sign or waiting not in (None, "sign"):
            msg = "This Sign button is no longer valid: the form changed after it was shown. Review it in chat first."
            raise HTTPException(409, msg)
        svc = dc.session.svc
        try:
            doc = svc.sign(
                doc_id,
                consent_text=body.consent_text,
                ip=request.client.host if request.client else "",
                user_agent=request.headers.get("user-agent", ""),
            )
        except WorkflowError as e:
            raise HTTPException(400, str(e)) from e
        _drop_card(dc, "sign_button", doc_id)
        return {"document": svc.describe(doc), **_respond(dc, dc.session.ui_event("signed"))}


@app.get("/api/documents/{doc_id}/pdf")
def pdf(request: Request, doc_id: str, intake_demo: str | None = Cookie(None)):
    dc = _case(intake_demo, request)
    try:
        data = dc.session.svc.document_pdf(doc_id)
    except WorkflowError as e:
        raise HTTPException(404, str(e)) from e
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{doc_id}.pdf"',
        },
    )
