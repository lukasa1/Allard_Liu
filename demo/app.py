"""The web demo (L33) on the runtime (agent/runtime.py): the veteran's chat and cards, the
attorney's countersign, and the case panel.

Run:  uv run intake serve        then open http://localhost:8000
(or:  uv run uvicorn demo.app:app --port 8000)

It needs OPENROUTER_API_KEY (D7: there are no offline agents). Without the key the page still
loads and says to set it; every case endpoint answers 503 with the same message.

Pick a synthetic test veteran (its synthetic C-file is what claims prep pulls) and chat as the
veteran. Agents reach the page only through the outbox, which the page polls
(GET /api/cases/<id>/updates?since=<seq>), so a reply from a background turn (the orchestrator's
wake, claims prep's return, pass 2's first question) shows up without the veteran typing.

This is the trusted host: only it captures ID numbers (secure form -> vault), signs (the veteran's
click) and countersigns (the staff panel), through agent.intake.documents. SYNTHETIC DATA ONLY.
"""

from __future__ import annotations

import base64
import binascii
import os
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import config
from agent.casefile import STAGE_NAMES, CaseFile
from agent.ingest import redact_chat
from agent.intake import documents
from agent.personas import get_persona, load_personas
from agent.runtime import Runtime, make_runtime
from poa_skill.service import FORMS, WorkflowError

config.load_env()
app = FastAPI(title="VA claims agent demo")
STATIC = Path(__file__).parent / "static"
NO_KEY = ("Set OPENROUTER_API_KEY (in your shell or the repo's .env) and restart the server: the "
          "demo's agents run on Claude Haiku 5.5 through OpenRouter.")  # fmt: skip
STAFF = "Attorney (demo staff panel)"
PNG_PREFIX = "data:image/png;base64,"
DECISION_EVENTS = ("handoff", "stage_changed", "side_state_changed", "task_created", "refused")


@lru_cache(maxsize=1)
def _live_runtime() -> Runtime:
    return make_runtime(config.data_dir() / "demo", config.make_lm())


def get_runtime() -> Runtime | None:
    """The live runtime, or None with no key. Tests override this with a scripted-LM runtime."""
    return _live_runtime() if os.environ.get("OPENROUTER_API_KEY") else None


MaybeRuntime = Annotated[Runtime | None, Depends(get_runtime)]


def runtime(rt: MaybeRuntime) -> Runtime:
    if rt is None:
        raise HTTPException(503, NO_KEY)
    return rt


Live = Annotated[Runtime, Depends(runtime)]  # 503 with NO_KEY when there is no key


def _case(rt: Runtime, case_id: str) -> CaseFile:
    if not rt.store.exists(case_id):
        raise HTTPException(404, "no such case: press Start")
    return rt.store.get_case(case_id)


def _active(case: CaseFile) -> None:
    """A card does nothing once the case is with a person or closed."""
    if case.parked:
        raise HTTPException(409, f"This case is {case.side_state.replace('_', ' ')}; the card is no longer valid.")


# ------------------------------------------------------------------------------ page and setup


@app.get("/")
def index():
    return FileResponse(STATIC / "app.html")


@app.get("/api/config")
def get_config(rt: MaybeRuntime):
    return {
        "ready": rt is not None,
        "message": None if rt else NO_KEY,
        "attorney": documents.attorney_name(),
        "personas": [{"id": p.id, "name": p.display_name, "summary": p.summary} for p in load_personas()],
    }


class NewCase(BaseModel):
    persona_id: str


@app.post("/api/cases")
def new_case(body: NewCase, rt: Live):
    if body.persona_id not in {p.id for p in load_personas()}:
        raise HTTPException(404, f"unknown test veteran {body.persona_id!r}")
    return {"case_id": rt.open_case(body.persona_id).case_id}


# ------------------------------------------------------------------------------ chat and delivery


class Chat(BaseModel):
    text: str


@app.post("/api/cases/{case_id}/messages")
def chat(case_id: str, body: Chat, rt: Live):
    """Queue the veteran's message (the runtime redacts, checks for a crisis and routes it).
    Returns the text as the agents see it: ID numbers hidden."""
    _case(rt, case_id)
    if not body.text.strip():
        raise HTTPException(400, "empty message")
    rt.message(case_id, body.text)
    return {"text": redact_chat(body.text)[0]}


@lru_cache(maxsize=1)
def simulator_lm():
    return config.make_lm(role="simulator")


@app.post("/api/cases/{case_id}/suggest")
def suggest(case_id: str, rt: Live):
    """Autoplay: the eval's simulated veteran (the case's persona, intake_eval/simulator.py) writes
    the next reply from the chat so far. The page puts it in the text box; Send sends it. Like the
    eval's runner (plan §3), it waits for idle: 409 while any turn is queued or running (claims
    prep in the background included)."""
    from intake_eval.simulator import DSPySimulator, load_chat

    case = _case(rt, case_id)
    if rt.busy(case_id):
        running = ", ".join(sorted(rt.running(case_id))).replace("_", " ") or "a queued turn"
        raise HTTPException(409, f"Wait: {running} is still working.")
    sim = DSPySimulator(get_persona(case.persona_id), simulator_lm())
    unread = load_chat(sim, [e.data for e in rt.store.events(case_id, types=("message",))])
    return {"text": sim.respond(unread or "(The assistant is waiting for you.)")}


@app.get("/api/cases/{case_id}/updates")
def updates(case_id: str, rt: Live, since: int = 0):
    """The outbox after `since`, in order: messages and cards. `running`: agents mid-turn; `busy`:
    any turn queued or running (autoplay waits for it)."""
    _case(rt, case_id)
    items = rt.updates(case_id, since)
    return {"items": [o.model_dump() for o in items], "running": sorted(rt.running(case_id)), "busy": rt.busy(case_id)}


# ------------------------------------------------------------------------------ the veteran's cards


class SecureForm(BaseModel):
    values: dict[str, str]


@app.post("/api/cases/{case_id}/secure/{request_id}")
def secure_submit(case_id: str, request_id: str, body: SecureForm, rt: Live):
    _active(_case(rt, case_id))
    try:
        return {"errors": documents.submit_secure_form(rt, case_id, request_id, body.values)}
    except WorkflowError as e:
        raise HTTPException(400, str(e)) from e


class Signature(BaseModel):
    data_uri: str


def _check_png(data_uri: str) -> None:
    """Reject anything but a real PNG now, not with a 500 when Sign places it."""
    from PIL import Image, UnidentifiedImageError

    if not data_uri.startswith(PNG_PREFIX):
        raise HTTPException(400, "signature must be a PNG data URI")
    try:
        with Image.open(BytesIO(base64.b64decode(data_uri[len(PNG_PREFIX) :], validate=True))) as img:
            if img.format != "PNG":
                raise ValueError(img.format)
            img.verify()
    except (binascii.Error, UnidentifiedImageError, ValueError, OSError, SyntaxError) as e:
        raise HTTPException(400, "signature is not a valid PNG image") from e


@app.post("/api/cases/{case_id}/signature")
def signature(case_id: str, body: Signature, rt: Live):
    _active(_case(rt, case_id))
    _check_png(body.data_uri)
    try:
        documents.save_signature(rt, case_id, body.data_uri)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"saved": True}


class SignClick(BaseModel):
    consent_text: str


@app.post("/api/cases/{case_id}/sign/{form}")
def sign(case_id: str, form: str, body: SignClick, request: Request, rt: Live):
    if form not in FORMS:
        raise HTTPException(404, f"no form {form!r}")
    _active(_case(rt, case_id))
    if not documents.sign_card_open(rt, case_id, form):
        raise HTTPException(409, "This Sign button is no longer valid: the document changed after it was shown.")
    try:
        documents.sign(rt, case_id, form, body.consent_text, ip=request.client.host if request.client else "",
                       user_agent=request.headers.get("user-agent", ""))  # fmt: skip
    except (WorkflowError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {"signed": form}


# ------------------------------------------------------------------------------ staff


@app.post("/api/cases/{case_id}/countersign")
def countersign(case_id: str, rt: Live):
    """The attorney countersigns both documents in one action (D6)."""
    if _case(rt, case_id).side_state != "waiting_on_attorney":
        raise HTTPException(409, "Nothing is waiting for the attorney's countersignature.")
    try:
        documents.countersign(rt, case_id, by=STAFF)
    except (WorkflowError, ValueError) as e:
        raise HTTPException(409, str(e)) from e
    return {"countersigned": list(FORMS)}


@app.get("/api/cases/{case_id}/documents/{form}.pdf")
def pdf(case_id: str, form: str, rt: Live):
    """The form's latest version: the draft, the veteran-signed PDF, or the countersigned one."""
    _case(rt, case_id)
    doc = documents.service(rt, case_id).live(form) if form in FORMS else None
    if doc is None:
        raise HTTPException(404, f"no {form} yet")
    data = documents.service(rt, case_id).document_pdf(doc.id)
    return Response(data, media_type="application/pdf", headers={
        "Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{form}-v{doc.version}.pdf"'})  # fmt: skip


# ------------------------------------------------------------------------------ the case panel


@app.get("/api/cases/{case_id}")
def panel(case_id: str, rt: Live):
    """Everything the case panel and the staff panel show (plan §1, step 8)."""
    case = _case(rt, case_id)
    svc = documents.service(rt, case_id)
    events = rt.store.events(case_id, exclude=("message",))
    docs = {}
    for form in FORMS:
        doc, state = svc.live(form), case.documents.get(form)
        if doc:
            docs[form] = {"status": doc.status, "version": doc.version, "terms": doc.terms,
                          "signed_at": state.signed_at if state else None,
                          "countersigned_at": state.countersigned_at if state else None,
                          "countersigned_by": state.countersigned_by if state else None}  # fmt: skip
    costs = rt.harness.traces.cost_by_agent(case_id)
    return {
        "case_id": case_id, "persona_id": case.persona_id,
        "stage": case.stage, "stage_name": STAGE_NAMES[case.stage],
        "side_state": case.side_state, "side_reason": case.side_reason,
        "owner": case.owner, "goal": case.goal, "running": sorted(rt.running(case_id)),
        "decisions": [e.model_dump() for e in events if e.type in DECISION_EVENTS
                      and (e.actor == "orchestrator" or e.data.get("actor") == "orchestrator")],
        "events": [e.model_dump() for e in events],
        "tasks": [t.model_dump() for t in case.tasks],
        "flags": [f.model_dump() for f in case.flags],
        "answers": {k: {"value": a.value, "unknown": a.unknown, "source": a.source} for k, a in case.answers.items()},
        "conflicts": [c.model_dump() for c in case.conflicts],
        "documents": docs,
        "filings": {k: f.model_dump() for k, f in case.filings.items()},
        "prep": {"pulled": case.prep.pulled, "pages_read": len(case.prep.pages_read), "facts": len(case.prep.facts),
                 "verified": case.prep.verified, "uncertain": case.prep.uncertain,
                 "prefill_done": case.prep.prefill_done, "done": case.prep.done},
        "face_note": case.prep.face_note.splitlines() if case.prep.face_note else [],
        "cost": {"by_agent": costs, "total": round(sum(costs.values()), 6)},
        "can_countersign": case.side_state == "waiting_on_attorney",
    }  # fmt: skip
