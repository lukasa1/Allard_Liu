"""Run one synthetic veteran through a whole case (the same CaseSession the demo uses).

The simulated veteran answers chat messages and also "uses" the cards the way a person would:
signs in with VA (or skips, in the ask-only condition), fills the secure form from the persona's
synthetic identity, draws a signature, and clicks Sign. Card actions go straight to PoaService,
exactly like the web host, so the eval exercises the real POA skill path.
"""

from __future__ import annotations

import base64
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from agent.intake.controller import AgentConfig
from agent.lighthouse import StubLighthouse
from agent.personas import Persona
from agent.session import UNAVAILABLE, CaseSession, SessionTurn
from poa_skill.service import WorkflowError

MAX_STEPS = 400
AS_OF = date(2026, 11, 3)  # fixed "today" so face-note deadlines are reproducible

# How the case's records are used by intake: VA's records (veteran signs in with VA, pass 1) and
# the C-file (claims prep, before pass 2). The C-file is always read for the face note.
CONDITIONS: dict[str, AgentConfig] = {
    "ask_no_probes": AgentConfig(records_mode="ask", verification_probes=False, cfile_mode="off"),
    "ask": AgentConfig(records_mode="ask", cfile_mode="off"),  # every question in chat
    "cfile": AgentConfig(records_mode="ask", cfile_mode="confirm"),  # no VA sign-in, C-file only
    "fetch": AgentConfig(records_mode="fetch", cfile_mode="fetch"),  # trust both
    "fetch_confirm": AgentConfig(records_mode="fetch_confirm", cfile_mode="confirm"),  # both, confirmed
}

VAULT_BRANCH = {
    "army": "army", "navy": "navy", "air force": "air_force", "marine corps": "marine_corps",
    "coast guard": "coast_guard", "space force": "space_force",
}  # fmt: skip


def signature_png() -> str:
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).line(
        [(40, 150), (200, 40), (360, 150), (560, 60)], fill=(19, 36, 70, 255), width=6
    )
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def secure_form_values(p: Persona, fields: list[str]) -> dict[str, str]:
    t = p.truth
    first = t.service_periods[0].branch if t.service_periods else None
    values = {
        "first_name": t.first_name or "",
        "middle_initial": p.identity.get("middle_initial", ""),
        "last_name": t.last_name or "",
        "ssn": p.identity["ssn"],
        "date_of_birth": p.identity.get("dob_typed") or p.identity["dob"],
        "branch": VAULT_BRANCH.get(first or "", ""),
        "address.line1": t.street or "",
        "address.city": t.city or "",
        "address.state": t.state or "",
        "address.zip": t.zip or "",
        "phone": t.cell_phone or "",
        "email": t.email or "",
        "va_file_number": "",
        "service_number": "",
    }
    return {f: values.get(f, "") for f in fields}


ACTIONABLE_CARDS = ("va_sign_in", "secure_form", "signature_pad", "sign_button", "attorney_signoff")
CARD_PHASE = {"va_sign_in": "va_sign_in", "attorney_signoff": "attorney_signoff"}  # default: poa
# A newer card of one of these types replaces the older one (e.g. a Sign button for a superseded draft).
SUPERSEDED_BY_NEWER = ("sign_button", "secure_form", "signature_pad", "document_preview")


def queue_cards(queue: list[dict], new: list[dict]) -> list[dict]:
    """Append `new` to `queue`, dropping older cards of a type a newer card replaces."""
    replaced = {c.get("type") for c in new} & set(SUPERSEDED_BY_NEWER)
    return [c for c in queue if c.get("type") not in replaced] + list(new)


def act_on_card(
    session: CaseSession, persona: Persona, card: dict, records_mode: str
) -> tuple[SessionTurn | None, str]:
    """Do what a veteran would do with one card. Returns (the session's response, a log line).

    Card actions go straight to PoaService, like the web host: secure-form values and the
    signature never pass through the session or a model.
    """
    kind = card.get("type")
    phase = session.case.phase
    needed = CARD_PHASE.get(kind, "poa")
    if kind in ACTIONABLE_CARDS and phase != needed:  # e.g. a Sign card left open after a hand-off
        return None, f"[{kind} card ignored: the case is now in {phase}]"
    try:
        return _act(session, persona, card, records_mode)
    except WorkflowError as e:  # e.g. a Sign card for a draft that was superseded
        return None, f"[{kind} card no longer valid: {e}]"


def _act(
    session: CaseSession, persona: Persona, card: dict, records_mode: str
) -> tuple[SessionTurn | None, str]:
    svc = session.svc
    kind = card.get("type")
    if kind == "va_sign_in":
        if records_mode == "ask":
            return session.ui_event("va_sign_in_declined"), "[veteran skips VA sign-in]"
        return session.ui_event("va_sign_in", icn=persona.icn), "[veteran signs in with VA]"
    if kind == "secure_form":
        values = secure_form_values(persona, [f["name"] for f in card["fields"]])
        errors = svc.complete_capture_request(card["request_id"], values)
        note = f"[veteran fills the secure form: {', '.join(sorted(values))}; errors: {errors or 'none'}]"
        return session.ui_event("secure_form_submitted"), note
    if kind == "signature_pad":
        svc.save_signature(signature_png())
        return session.ui_event("signature_saved"), "[veteran draws and saves a signature]"
    if kind == "attorney_signoff":  # staff, not the veteran: the simulated attorney approves
        return session.ui_event("attorney_countersigned", by="simulated attorney"), "[attorney countersigns the 21-22a (simulated staff)]"
    if kind == "sign_button":
        svc.sign(
            card["document_id"],
            consent_text=card["consent_text"],
            ip="127.0.0.1",
            user_agent="simulator",
        )
        return session.ui_event("signed"), "[veteran clicks Sign]"
    return None, ""  # document_preview: the veteran reviews it in chat


@dataclass
class CaseRun:
    persona_id: str
    condition: str
    session: CaseSession
    transcript: list[dict[str, str]] = field(default_factory=list)
    agent_messages: int = 0
    steps: int = 0
    hit_step_limit: bool = False
    model_failures: int = 0  # agent "unavailable" replies + simulator errors
    poa_chat_turns: int = 0  # veteran chat messages while the case was in the 21-22a step
    turns_to_signed_poa: int | None = None  # veteran actions (messages + card uses) until signed
    veteran_actions: int = 0
    gave_up: bool = False  # stopped after repeated model failures
    error: str = ""  # traceback if the run crashed

    @property
    def crashed(self) -> bool:
        return bool(self.error)

    @property
    def case(self):
        return self.session.case


def run_case(
    persona: Persona,
    condition: str = "fetch_confirm",
    provider: str = "offline",
    simulator: Any = None,
    lm: Any = None,
    data_dir: Path | None = None,
    restart_every_turn: bool = False,
) -> CaseRun:
    """`restart_every_turn`: rebuild the session from disk (CaseSession.resume) after every step, as
    if the server restarted each time. A memory test: the case must end exactly as without it."""
    from intake_eval.simulator import OfflineSimulator

    session = CaseSession(
        provider=provider,
        persona=persona,
        lighthouse=StubLighthouse(),
        agent_config=CONDITIONS[condition],
        data_dir=data_dir or Path(tempfile.mkdtemp(prefix="eval-")),
        as_of=AS_OF,
        lm=lm,
    )
    sim = simulator or OfflineSimulator(persona)
    run = CaseRun(persona_id=persona.id, condition=condition, session=session)

    def record(turn: SessionTurn) -> None:
        for m in turn.messages:
            run.transcript.append({"role": "agent", "text": m})
            run.agent_messages += 1
        if UNAVAILABLE in turn.messages:
            run.model_failures += 1

    def use_card(card: dict) -> SessionTurn | None:
        turn, note = act_on_card(run.session, persona, card, CONDITIONS[condition].records_mode)
        if note:
            run.transcript.append({"role": "app", "text": note})
        if turn is not None and card.get("type") != "attorney_signoff":
            _count_action(run)
        return turn

    def restart() -> None:
        if restart_every_turn:
            s = run.session
            run.session = CaseSession.resume(s.case.case_id, data_dir=s.data_dir, lighthouse=StubLighthouse(), lm=lm)

    try:
        _drive(run, sim, record, use_card, restart)
    except Exception as exc:  # keep the partial transcript; the score counts it as a crash
        run.error = traceback.format_exc()
        run.transcript.append(
            {"role": "app", "text": f"[run crashed: {type(exc).__name__}: {exc}]"}
        )
    return run


def _count_action(run: CaseRun) -> None:
    run.veteran_actions += 1
    if run.turns_to_signed_poa is None and run.session.case.poa_signed:
        run.turns_to_signed_poa = run.veteran_actions


def _drive(run: CaseRun, sim: Any, record, use_card, restart=lambda: None) -> None:
    turn = run.session.start()
    record(turn)
    failures = 0  # consecutive model failures: give up rather than loop
    pending_cards = list(turn.cards)
    while run.steps < MAX_STEPS:
        run.steps += 1
        restart()
        session = run.session
        if pending_cards:
            new = use_card(pending_cards.pop(0))
            if new is not None:
                record(new)
                pending_cards = queue_cards(pending_cards, new.cards)
            continue
        if not session.waiting_for_chat:
            break
        since: list[str] = []  # every agent message since the veteran last spoke
        for t in reversed(run.transcript):
            if t["role"] == "veteran":
                break
            if t["role"] == "agent":
                since.insert(0, t["text"])
        last = "\n\n".join(since)
        try:
            reply = sim.respond(last, session.pending)
        except Exception as exc:  # a refusal, unparseable output, a 429 after retries
            run.model_failures += 1
            failures += 1
            run.transcript.append(
                {"role": "app", "text": f"[simulator failed: {type(exc).__name__}]"}
            )
            if failures >= 3:
                run.gave_up = True
                break
            continue
        run.transcript.append({"role": "veteran", "text": reply})
        if session.case.phase == "poa":
            run.poa_chat_turns += 1
        turn = session.message(reply)
        _count_action(run)
        record(turn)
        pending_cards = queue_cards(pending_cards, turn.cards)
        failures = failures + 1 if UNAVAILABLE in turn.messages else 0
        if failures >= 3:
            run.gave_up = True
            break
    else:
        run.hit_step_limit = True
