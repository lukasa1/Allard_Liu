"""Demo host app: chat + secure form + signature pad + PDF preview + Sign button.

Run:  uv run uvicorn demo.server:app --port 8000   then open http://localhost:8000
With OPENROUTER_API_KEY set, an example host agent (demo/host_agent.py) that mounts the skill
drives the conversation. Without it, the page offers a
"drive the tools yourself" panel that calls the same tools the agent would.

This is the trusted side. It is the only code that touches raw PII (secure form -> vault) and the
only path to signing (the user's click -> PoaService.sign). SYNTHETIC DATA ONLY in this demo.
"""

import os
import secrets
from pathlib import Path

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from poa_skill.service import PoaService, WorkflowError
from poa_skill.tools import run_tool

app = FastAPI(title="21-22a intake demo")
STATIC = Path(__file__).parent / "static"
AGENT_ENABLED = bool(os.environ.get("OPENROUTER_API_KEY"))
_agents: dict = {}


def _svc(sid: str | None) -> PoaService:
    if not sid:
        raise HTTPException(401, "no session")
    try:
        return PoaService(sid)
    except ValueError as e:
        raise HTTPException(401, "bad session") from e


def _agent(sid: str):
    if not AGENT_ENABLED:
        return None
    if sid not in _agents:
        from demo.host_agent import HostAgent

        _agents[sid] = HostAgent(_svc(sid))
    return _agents[sid]


def _notify(sid: str, event: str) -> dict:
    agent = _agent(sid)
    return agent.notify(event) if agent else {"reply": "", "cards": []}


@app.get("/")
def index(response: Response, poa_session: str | None = Cookie(None)):
    resp = FileResponse(STATIC / "index.html")
    if not poa_session:
        resp.set_cookie("poa_session", secrets.token_urlsafe(18), httponly=True, samesite="strict")
    return resp


@app.get("/api/config")
def config():
    return {"agent_enabled": AGENT_ENABLED}


@app.get("/api/status")
def status(poa_session: str | None = Cookie(None)):
    return _svc(poa_session).status()


class Chat(BaseModel):
    text: str


@app.post("/api/chat")
def chat(body: Chat, poa_session: str | None = Cookie(None)):
    agent = _agent(poa_session or "")
    if agent is None:
        raise HTTPException(503, "agent offline: set OPENROUTER_API_KEY")
    return agent.send(body.text)


class ToolCall(BaseModel):
    name: str
    args: dict = {}


@app.post("/api/tool")
def tool(body: ToolCall, poa_session: str | None = Cookie(None)):
    """Manual mode: the same tools the agent has, for running the demo without an API key."""
    out = run_tool(_svc(poa_session), body.name, body.args)
    return {"result": out.result, "cards": out.cards, "is_error": out.is_error}


class SecureForm(BaseModel):
    values: dict[str, str]


@app.post("/api/secure/{request_id}")
def secure_submit(request_id: str, body: SecureForm, poa_session: str | None = Cookie(None)):
    svc = _svc(poa_session)
    try:
        errors = svc.complete_capture_request(request_id, body.values)
    except WorkflowError as e:
        raise HTTPException(400, str(e)) from e
    if errors:
        return {"errors": errors}
    stored = sorted(k for k, v in body.values.items() if v.strip())
    return {
        "errors": {},
        **_notify(
            poa_session, f"The user submitted the secure form ({request_id}); stored: {stored}."
        ),
    }


class Signature(BaseModel):
    data_uri: str


@app.post("/api/signature")
def signature(body: Signature, poa_session: str | None = Cookie(None)):
    try:
        _svc(poa_session).save_signature(body.data_uri)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _notify(poa_session, "The user drew and saved their signature.")


class Edit(BaseModel):
    changes: dict


@app.post("/api/documents/{doc_id}/edit")
def edit(doc_id: str, body: Edit, poa_session: str | None = Cookie(None)):
    svc = _svc(poa_session)
    try:
        doc = svc.edit(doc_id, body.changes, actor="user")
    except WorkflowError as e:
        raise HTTPException(400, str(e)) from e
    note = _notify(
        poa_session, f"The user edited the draft {doc_id} themselves: {sorted(body.changes)}."
    )
    return {"document": svc.describe(doc), **note}


class SignClick(BaseModel):
    consent_text: str


@app.post("/api/documents/{doc_id}/sign")
def sign(doc_id: str, body: SignClick, request: Request, poa_session: str | None = Cookie(None)):
    svc = _svc(poa_session)
    try:
        doc = svc.sign(
            doc_id,
            consent_text=body.consent_text,
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
        )
    except WorkflowError as e:
        raise HTTPException(400, str(e)) from e
    note = _notify(poa_session, f"The user clicked Sign. Document {doc_id} is signed.")
    return {"document": svc.describe(doc), **note}


@app.get("/api/documents/{doc_id}/pdf")
def pdf(doc_id: str, poa_session: str | None = Cookie(None)):
    try:
        data = _svc(poa_session).document_pdf(doc_id)
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
