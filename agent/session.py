"""One case, end to end: the orchestrator, the intake subagent and every tool, wired together.

The web demo, the CLI and the eval all drive a case through this class, so what the eval
measures is exactly what the demo shows. Three kinds of input:

  start()                    open the case (the orchestrator takes over)
  message(text)              the veteran typed something (redacted before any model sees it)
  ui_event(kind, **data)     the veteran used a card: va_sign_in / va_sign_in_declined /
                             secure_form_submitted / signature_saved / draft_edited / signed;
                             or staff did: attorney_countersigned (the attorney approves filing)

Who answers a message: the intake subagent or the POA step while one of them is working the case
(each answers questions itself); once the case is parked, the read-only support subagent.

Memory: after every turn the case file is saved together with the subagents' working memory, so
CaseSession.resume(case_id) continues a case after a restart, mid-conversation.

Each returns a SessionTurn: the agent's messages, cards for the UI, and the case summary.
The host (demo/app.py) posts card data to PoaService itself (secure form values, signature,
Sign click) before calling ui_event, so PII and signing never pass through here or a model.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from agent import config
from agent.case import CHAT_PHASES, TERMINAL_PHASES, CaseEvent, CaseState, CaseStore, HumanTask, SubagentResult, now
from agent.cfile import DocumentsStub, OfflineExtractor, extract_cfile, make_dspy_extractor, render
from agent.cfile.reconcile import apply as apply_cfile
from agent.cfile.reconcile import cfile_intake_values, reconcile, without_firm
from agent.ingest import _WANTS_HUMAN, HIDDEN, detect_crisis, redact_chat
from agent.intake import rules
from agent.intake.brains import split_question
from agent.intake.controller import (
    CRISIS_MESSAGE,
    GREETING,
    HANDOFF_MESSAGE,
    AgentConfig,
    BrainError,
    IntakeAgent,
    Turn,
)
from agent.intake.schema import Outcome
from agent.lighthouse import Lighthouse, LighthouseError, make_lighthouse
from agent.legacy_orchestrator import DSPyPolicy, OfflinePolicy, Orchestrator
from agent.personas import Persona, get_persona
from agent.poa import OfflinePoaStep, PoaTurn, is_signed, make_dspy_poa_step, signed_document_id
from agent.qa import make_qa
from agent.support import ACK, SupportAgent, find_flags, snapshot
from poa_skill import PoaService
from poa_skill.service import WorkflowError, load_representative

# Declining the 21-22a in the POA step: a person follows up (the case must not wait forever).
_DECLINE_POA = re.compile(  # only about signing: "No, I don't want this shared" answers Item 20
    r"\b((don'?t|do not) want to sign|won'?t sign|will not sign|not (going to|gonna) sign|"
    r"refuse to sign|not signing|(don'?t|do not) want (you|the firm|an attorney|anyone) to represent me|"
    r"(don'?t|do not) want (a|an|the) (lawyer|attorney|representative))\b",
    re.IGNORECASE,
)

VAULT_TO_INTAKE = {
    "first_name": "first_name",
    "last_name": "last_name",
    "address.line1": "street",
    "address.city": "city",
    "address.state": "state",
    "address.zip": "zip",
    "phone": "cell_phone",
    "email": "email",
}
VA_BRANCH_TO_VAULT = {
    "army": "army", "navy": "navy", "air force": "air_force", "marine corps": "marine_corps",
    "coast guard": "coast_guard", "space force": "space_force",
}  # fmt: skip
SIGN_IN_TEXT = (
    "To save you a lot of questions, you can sign in with VA.gov and let us read your service "
    "history, disability ratings and claims from VA's records. Or skip it and just answer my questions."
)
PRIVACY_NOTE = (
    "Thanks. I've hidden that number for your privacy. Please don't type ID numbers in the chat; "
    "you'll enter them in a secure form when we get to the paperwork."
)
UNAVAILABLE = "Sorry, I'm having trouble reaching my language model right now. Please send that again in a moment."
_CASE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
STATE_VERSION = 1
# Flags from support that need a person soon (handoff); the rest are reviewed with the case.
_URGENT_FLAGS = ("withdraw", "complaint", "wants_human")


@dataclass
class SessionTurn:
    messages: list[str] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    redacted: bool = False
    case: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "cards": self.cards,
            "redacted": self.redacted,
            "case": self.case,
        }


class CaseSession:
    def __init__(
        self,
        *,
        provider: str = "offline",
        persona: Persona | None = None,
        lighthouse: Lighthouse | None = None,
        agent_config: AgentConfig | None = None,
        data_dir: Path | None = None,
        session_id: str | None = None,
        as_of: date | None = None,
        lm=None,
    ) -> None:
        self.provider = provider
        self.persona = persona
        self.data_dir = data_dir or config.data_dir()
        self.session_id = session_id or ("case_" + secrets.token_hex(6))
        self.as_of = as_of
        self.lighthouse = lighthouse or make_lighthouse()
        self.store = CaseStore(self.data_dir / "cases")
        self.case = CaseState(case_id=self.session_id, persona_id=persona.id if persona else None)
        self.svc = PoaService(self.session_id, data_dir=self.data_dir)
        self.rep = load_representative()

        if not _CASE_ID.fullmatch(self.session_id):
            raise ValueError("session_id may only contain letters, digits, '_' and '-'")
        self.agent_config = agent_config or AgentConfig()
        self.host_state: dict[str, Any] = {}  # the host's own memory (e.g. the demo's open cards)
        if self.agent_config.records_mode == "ask":
            # VA sign-in is off unless VA's records are wanted (the firm must approve collecting
            # them before representation): pass 1 simply asks.
            self.case.va_consent = "not_offered"

        self.lm = lm
        if provider == "dspy" and self.lm is None:
            self.lm = config.make_lm()
        policy = DSPyPolicy(self.lm) if provider == "dspy" else OfflinePolicy()
        self.orchestrator = Orchestrator(policy, self._execute)

        if provider == "dspy":
            from agent.intake.dspy_brain import DSPyBrain

            brain = DSPyBrain(self.lm)
        else:
            from agent.intake.brains import OfflineBrain

            brain = OfflineBrain()
        raw_qa = make_qa(provider)
        self._qa_usage: list[dict[str, Any]] = []

        def qa(question: str):  # the same QA tool for intake and support, with its cost traced
            result = raw_qa(question)
            if getattr(result, "usage", None):
                self._qa_usage.append(result.usage)
            return result

        self.intake = IntakeAgent(brain, config=self.agent_config, qa=qa)
        self.support = SupportAgent(qa)
        self.poa = (
            make_dspy_poa_step(self.svc, self.lm)
            if provider == "dspy"
            else OfflinePoaStep(self.svc)
        )
        self.documents = DocumentsStub(self.data_dir / "cfiles")

        self._out: SessionTurn = SessionTurn()
        self._queue: list[tuple[str, Any]] = []
        self._last_poa_text = ""
        self._handling = False

    # ------------------------------------------------------------------ memory

    @classmethod
    def resume(
        cls,
        case_id: str,
        *,
        data_dir: Path | None = None,
        lighthouse: Lighthouse | None = None,
        lm=None,
    ) -> CaseSession:
        """Rebuild a saved case and its subagents exactly where they stopped (e.g. after a restart).
        The provider and the intake settings come from the saved case, so a case started offline
        continues offline. Raises KeyError if there is no saved case with this id."""
        if not _CASE_ID.fullmatch(case_id or ""):
            raise KeyError(case_id)
        data_dir = data_dir or config.data_dir()
        store = CaseStore(data_dir / "cases")
        if not store.exists(case_id):
            raise KeyError(case_id)
        case = store.load(case_id)
        state = case.subagents
        if state.get("version") != STATE_VERSION:
            raise ValueError(f"case {case_id} has no resumable state (version {state.get('version')!r})")
        persona = get_persona(case.persona_id) if case.persona_id else None
        session = cls(
            provider=state["provider"],
            persona=persona,
            lighthouse=lighthouse,
            agent_config=AgentConfig(**state["agent_config"]),
            data_dir=data_dir,
            session_id=case_id,
            as_of=date.fromisoformat(state["as_of"]) if state.get("as_of") else None,
            lm=lm,
        )
        session.case = case
        session.intake.load_state(state["intake"])
        session.poa.load_state(state["poa"])
        session._last_poa_text = state.get("last_poa_text", "")
        session.host_state = dict(state.get("host", {}))
        return session

    def save(self) -> None:
        """Save the case and every subagent's working memory (done after every turn)."""
        self._sync_case()
        self.store.save(self.case)

    def _working_memory(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "provider": self.provider,
            "agent_config": dict(self.agent_config.__dict__),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "intake": self.intake.to_state(),
            "poa": self.poa.to_state(),
            "last_poa_text": self._last_poa_text,
            "host": self.host_state,
        }

    # ------------------------------------------------------------------ public API

    def start(self) -> SessionTurn:
        return self._run(lambda: self._event("case_opened"), {"kind": "start"})

    def message(self, text: str) -> SessionTurn:
        clean, redacted = redact_chat(text)
        if redacted:  # the placeholder itself ("[number hidden ...]") tells the model what happened
            self.svc.docs.audit("chat_pii_redacted")

        def go() -> None:
            nonlocal clean
            self._out.redacted = redacted
            if redacted:
                self._say(PRIVACY_NOTE)
            phase = self.case.phase
            if detect_crisis(clean) and not (
                phase in ("screening", "intake") and self.intake.pending is not None
            ):
                # The intake controller checks this itself; every other phase is checked here.
                self.case.escalation = "possible crisis or risk of self-harm"
                self.case.awaiting_veteran = False
                if self.case.intake_outcome is None:
                    self.case.intake_outcome = Outcome(decision="escalated", reasons=[self.case.escalation])
                self._say(CRISIS_MESSAGE)
                if self.case.phase not in ("closed", "human_handoff", "attorney_review"):
                    self._event("escalated")
                else:
                    self.case.tasks.append(
                        HumanTask(
                            kind="handoff",
                            text="Crisis disclosure after the case was parked: call the veteran now.",
                        )
                    )
                return
            answer_part, asked = split_question(clean)
            if redacted and not answer_part.replace(HIDDEN, "").strip(" .,!") and not asked:
                # The reply was only an ID number: don't store the placeholder as an answer.
                if phase in ("screening", "intake") and self.intake.pending is not None:
                    self._say(self.intake.pending.text)
                return
            if phase in CHAT_PHASES and "withdraw" in find_flags(clean) and self.case.poa_signed:
                # Ending the representation mid-conversation (e.g. a reopened intake): a person
                # talks with the veteran before anything else happens. Never stored as an answer.
                self.case.escalation = "the veteran asked to withdraw the representation"
                self.case.awaiting_veteran = False
                self._say(ACK["withdraw"])
                self._event("escalated")
                return
            declined_poa = phase == "poa" and not is_signed(self.svc) and _DECLINE_POA.search(clean)
            if (phase in ("poa", "va_sign_in") and _WANTS_HUMAN.search(clean)) or declined_poa:
                self.case.escalation = (
                    "the veteran declined to sign the 21-22a"
                    if declined_poa
                    else "the veteran asked to speak with a person"
                )
                self.case.awaiting_veteran = False
                if self.case.intake_outcome is None:
                    self.case.intake_outcome = Outcome(decision="escalated", reasons=[self.case.escalation])
                self._say(
                    "That's completely fine; nothing has been signed. Someone from our team will reach "
                    "out to answer any questions, and you can pick this up again whenever you like."
                    if declined_poa
                    else HANDOFF_MESSAGE
                )
                self._event("escalated")
                return
            if phase in ("poa", "va_sign_in") and asked:
                self._say(self.intake.answer_question(asked))  # QA works in every phase
                if not answer_part:
                    if phase == "poa" and self._last_poa_text:
                        self._say(f"Back to the form: {self._last_poa_text}")
                    elif phase == "va_sign_in":
                        self._say("Whenever you're ready, use the VA sign-in card above, or Skip.")
                    return
                clean = answer_part
            if phase in ("screening", "intake") and self.intake.pending is not None:
                try:
                    turn = self.intake.reply(clean)
                except BrainError:
                    self._say(UNAVAILABLE)
                    return
                self._intake_turn(turn)
            elif phase == "poa":
                self._poa_turn(self._poa_call(self.poa.message, clean))
            elif phase == "va_sign_in":
                self._say(
                    "Please use the VA sign-in card above, or choose Skip to answer questions instead."
                )
            else:
                self._support(clean)

        return self._run(go, {"kind": "message", "text": clean[:500], "phase": self.case.phase})

    def ui_event(self, kind: str, **data: Any) -> SessionTurn:
        def go() -> None:
            if kind == "va_sign_in" and self.case.phase == "va_sign_in":
                offered = [v["icn"] for v in self.lighthouse.test_veterans()]
                icn = data.get("icn") or (self.persona.icn if self.persona else None)
                if self.lighthouse.mode == "stub" and self.persona is not None:
                    icn = self.persona.icn  # the stub serves the persona being played
                elif offered and icn not in offered:
                    self._say("That VA test account isn't available. Please pick one from the card.")
                    return
                self.case.va_consent = "granted"
                self.case.icn = icn
                self._event("va_sign_in_completed", icn=self.case.icn)
            elif kind == "va_sign_in_declined" and self.case.phase == "va_sign_in":
                self.case.va_consent = "declined"
                self._event("va_sign_in_declined")
            elif (
                kind in ("secure_form_submitted", "signature_saved", "draft_edited", "signed")
                and self.case.phase == "poa"
            ):
                self._poa_turn(self._poa_call(self.poa.event, kind))
            elif kind == "attorney_countersigned" and self.case.phase == "attorney_signoff":
                # Staff action (the demo's attorney panel, or the eval's simulated attorney).
                self.case.poa_countersigned_at = now()
                self.case.poa_countersigned_by = str(data.get("by") or "attorney")
                for t in self.case.tasks:
                    if t.kind == "approval" and t.done_at is None:
                        t.done_at = self.case.poa_countersigned_at
                self._event("attorney_countersigned", by=self.case.poa_countersigned_by)
            else:
                self._say("")  # an event for another phase (e.g. a stale card): ignore it

        return self._run(go, {"kind": "ui_event", "event": kind, "phase": self.case.phase})

    @property
    def waiting_for_chat(self) -> bool:
        if self.case.phase in ("screening", "intake"):
            return self.intake.pending is not None
        if self.case.phase == "poa":
            return getattr(self.poa, "waiting_for", None) in (None, "item20", "item22", "review")
        return False

    @property
    def pending(self):
        if self.case.phase in ("screening", "intake"):
            return self.intake.pending
        if self.case.phase == "poa":
            return getattr(self.poa, "waiting_for", None)
        return None

    # ------------------------------------------------------------------ plumbing

    def _run(self, fn, trace_input: dict[str, Any] | None = None) -> SessionTurn:
        self._out = SessionTurn()
        n_decisions, n_events = len(self.case.decisions), len(self.case.events)
        n_lm = len(getattr(self.lm, "history", None) or [])
        self._qa_usage = []
        try:
            fn()
        finally:  # even if an action raised: keep what happened so far
            self._out.messages = [m for m in self._out.messages if m]
            usage = self._turn_usage(n_lm)
            self._add_usage(usage)
            self.save()
            self._trace(trace_input or {}, n_decisions, n_events, usage)
        self._out.case = self.case_view()
        return self._out

    def _turn_usage(self, n_lm: int) -> dict[str, Any]:
        """Model calls this turn: the agents' DSPy LM history plus the QA tool's calls."""
        calls = list((getattr(self.lm, "history", None) or [])[n_lm:])
        out = {"lm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        for h in calls:
            u = h.get("usage") or {}
            out["lm_calls"] += 1
            out["input_tokens"] += int(u.get("prompt_tokens") or 0)
            out["output_tokens"] += int(u.get("completion_tokens") or 0)
            out["cost_usd"] += float(h.get("cost") or 0.0)
        for u in self._qa_usage:
            out["lm_calls"] += 1
            out["input_tokens"] += int(u.get("prompt_tokens") or 0)
            out["output_tokens"] += int(u.get("completion_tokens") or 0)
            out["cost_usd"] += float(u.get("cost") or 0.0)
        return out

    def _add_usage(self, usage: dict[str, Any]) -> None:
        total = self.case.usage
        for k, v in usage.items():
            total[k] = total.get(k, 0) + v

    def _trace(self, trace_input: dict[str, Any], n_decisions: int, n_events: int, usage: dict[str, Any]) -> None:
        """The trace log: one JSON line per turn (input, what ran, what it decided, cost). Inputs
        are already redacted; card data (secure form values, signatures) never reaches here."""
        line = {
            "at": now(),
            "input": trace_input,
            "phase": self.case.phase,
            "messages": self._out.messages,
            "cards": [c.get("type") for c in self._out.cards],
            "decisions": [d.model_dump(mode="json") for d in self.case.decisions[n_decisions:]],
            "events": [e.model_dump(mode="json") for e in self.case.events[n_events:]],
            "usage": usage,
        }
        folder = self.data_dir / "traces"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{self.session_id}.jsonl").open("a") as f:
            f.write(json.dumps(line, default=str) + "\n")

    def _say(self, text: str, cards: list[dict] | None = None) -> None:
        if text:
            self._out.messages.append(text)
        if cards:
            self._out.cards.extend(cards)

    def _event(self, kind: str, *, arrive=None, **data: Any) -> None:
        """Record an event and wake the orchestrator on it. Each event is one wake. Events raised
        while the orchestrator is mid-action are queued and handled after it, not re-entrantly.
        `arrive` runs just before its wake: what the event brings (e.g. the C-file) appears then."""
        self.case.events.append(CaseEvent(type=kind, data=data))
        self._queue.append((kind, arrive))
        if self._handling:
            return
        self._handling = True
        try:
            while self._queue:
                kind_, arrive_ = self._queue.pop(0)
                if arrive_ is not None:
                    arrive_()
                self.orchestrator.handle(self.case, kind_)
        finally:
            self._handling = False
            self._queue.clear()  # after an exception, don't replay stale events on the next call

    def _sync_case(self) -> None:
        self.case.intake = self.intake.record
        self.case.subagents = self._working_memory()

    def _support(self, text: str) -> None:
        """A parked case (with the attorney, handed off, closed): the support subagent answers from
        a read-only snapshot; what it flags becomes a staff task here, so its promise is true."""
        phase = self.case.phase
        result = self.support.handle(snapshot(self.case), text)
        self._say(result.text)
        for flag in result.flags:
            if flag in ("withdraw", "wants_human") and phase not in TERMINAL_PHASES:
                # By rule, not a choice: nothing more is filed or asked until a person has talked
                # with the veteran (e.g. "cancel my power of attorney" before the countersign).
                self.case.escalation = (
                    "the veteran asked to withdraw the representation" if flag == "withdraw"
                    else "the veteran asked to speak with a person"
                )
                self.case.awaiting_veteran = False
            elif flag in ("withdraw", "wants_human"):  # parked: a person already has the case
                self.case.tasks.append(HumanTask(kind="handoff", text=f"Support flag '{flag}' ({phase}): {text[:300]}"))
            else:  # the orchestrator decides what it means for the case
                self.case.open_flags.append({"kind": flag, "text": text[:300], "at": now(), "phase": phase})
        if result.for_a_person or (phase == "human_handoff" and not result.flags):
            # Unanswered, or a person already owns the case: they should see every message.
            unanswered = f" Unanswered: {' / '.join(result.unanswered)[:300]}" if result.unanswered else ""
            self.case.tasks.append(HumanTask(
                kind="handoff" if phase == "human_handoff" else "review",
                text=f"Message from the veteran ({phase}): {text[:300]}.{unanswered}",
            ))  # fmt: skip
        res = SubagentResult(
            agent="support", status="needs_person" if (result.flags or result.for_a_person) else "answered",
            event="support_message", wrote=["tasks"] if (result.flags or result.for_a_person) else [],
            needs=[f"staff: {f}" for f in result.flags] + (["staff: read the message"] if result.for_a_person else []),
            flags=list(result.flags),
        )  # fmt: skip
        # The event log is support's memory: what was asked and answered (already redacted).
        self._event("support_message", question=text[:300], answer=result.text[:600],
                    answered=result.answered, flags=result.flags, result=res.model_dump())  # fmt: skip

    def _poa_call(self, fn, arg) -> PoaTurn:
        try:
            return fn(arg)
        except Exception:  # a failed model call leaves the skill's state unchanged: retry is safe
            return PoaTurn(UNAVAILABLE)

    # ------------------------------------------------------------------ subagent results

    def _intake_turn(self, turn: Turn) -> None:
        self._say(turn.text)
        self.case.awaiting_veteran = self.intake.pending is not None
        if turn.event == "stage_complete":
            self.case.screening_done = True
            res = SubagentResult(agent="intake", status="done", event="screening_complete",
                                 wrote=["intake", "screening_done"], needs=["the veteran signs the 21-22a"])  # fmt: skip
            self._event("screening_complete", result=res.model_dump())
        elif turn.event in ("stopped", "complete", "escalated"):
            self.case.intake_outcome = o = self.intake.outcome()
            if turn.event == "escalated":
                self.case.escalation = self.intake.escalation
            res = SubagentResult(
                agent="intake", status={"complete": "done"}.get(turn.event, turn.event),
                event=f"intake_{turn.event}", wrote=["intake", "intake_outcome"],
                needs=list(o.reasons) if o.decision != "eligible" else [], flags=list(o.flags),
            )  # fmt: skip
            self._event(f"intake_{turn.event}", decision=o.decision, result=res.model_dump())

    def _poa_turn(self, turn: PoaTurn) -> None:
        if turn.failed:  # tools may have run before the model failed: show their cards anyway
            turn = PoaTurn(UNAVAILABLE, turn.cards)
        self._say(turn.text, turn.cards)
        if turn.text and turn.text != UNAVAILABLE:
            self._last_poa_text = turn.text
        self.case.awaiting_veteran = not is_signed(self.svc)
        if self.case.poa_document_id is None and is_signed(self.svc):
            self.case.poa_document_id = signed_document_id(self.svc)
            res = SubagentResult(agent="poa", status="done", event="poa_signed", wrote=["poa_document_id"],
                                 needs=["the attorney countersigns the 21-22a"])  # fmt: skip
            self._event("poa_signed", document_id=self.case.poa_document_id, result=res.model_dump())

    # ------------------------------------------------------------------ actions (the orchestrator's tools)

    def _execute(self, action: str, case: CaseState) -> None:
        getattr(self, f"_do_{action}")()

    def _do_request_va_sign_in(self) -> None:
        self.case.phase = "va_sign_in"
        self.case.va_consent = "pending"
        vets = self.lighthouse.test_veterans()
        if self.persona is not None:
            vets = [v for v in vets if v.get("icn") == self.persona.icn] or vets
        self.intake.mark_greeted()
        self._say(
            f"{GREETING}\n\n{SIGN_IN_TEXT}",
            [{"type": "va_sign_in", "mode": self.lighthouse.mode, "test_veterans": vets}],
        )

    def _do_fetch_va_records(self) -> None:
        icn = self.case.icn
        try:
            records = self.lighthouse.fetch_records(icn or "")
        except LighthouseError as exc:
            self.case.va_consent = "declined"  # carry on with questions instead
            self.case.tasks.append(
                HumanTask(kind="review", text=f"VA records could not be fetched: {exc}")
            )
            self._say("I couldn't reach VA's records just now, so I'll ask you instead.")
            return
        self.case.va_records = records
        values = records.intake_values()
        self.case.records_prefilled = self.intake.prefill_from_records(
            values, records.service_text()
        )
        self._prefill_vault_from_records(records)
        if self.case.records_prefilled:
            self._say(
                "Thanks. I have your service history, ratings and claims from VA's records, so I can skip those questions."
            )

    def _prefill_vault_from_records(self, records) -> None:
        """Collect once: names and branch from VA go into the POA skill's vault (host side)."""
        eps = (records.service_history or {}).get("data", [])
        if not eps:
            return
        a = eps[-1].get("attributes", {})
        values = {"first_name": a.get("first_name") or "", "last_name": a.get("last_name") or ""}
        branch = VA_BRANCH_TO_VAULT.get(str(a.get("branch_of_service", "")).lower())
        if branch:
            values["branch"] = branch
        self.svc.vault.put({k: v for k, v in values.items() if v})

    def _do_start_screening(self) -> None:
        self.case.phase = "screening"
        self._intake_turn(self.intake.start("screen"))

    def _do_start_poa(self) -> None:
        self.case.phase = "poa"
        self._poa_turn(self._poa_call(lambda _: self.poa.start(), None))

    def _do_submit_poa_to_va(self) -> None:
        rep = {
            "poa_code": self.rep.get("poa_code", ""),
            "name": f"{self.rep['first_name']} {self.rep['last_name']}",
        }
        if self.case.icn:
            try:
                try:
                    pdf = self.svc.document_pdf(self.case.poa_document_id)
                except WorkflowError:  # no PDF to attach: VA keeps the request pending (task below)
                    pdf = None
                resp = self.lighthouse.submit_poa(self.case.icn, rep, signed_pdf=pdf)
                self.case.poa_submission = {
                    "method": f"lighthouse_{self.lighthouse.mode}",
                    "status": resp["status"],
                    "id": resp.get("id"),
                    "response": resp.get("raw"),
                }
                if resp["status"] != "submitted" or resp.get("upload_error"):
                    # VA has the request but not the signed form: a person finishes it. Never POST
                    # again (that would create a second request).
                    self.case.tasks.append(HumanTask(
                        kind="manual_filing",
                        text=f"VA holds POA request {resp.get('id')} as '{resp['status']}': upload the "
                        f"signed 21-22a to it{' (' + resp['upload_error'] + ')' if resp.get('upload_error') else ''}.",
                    ))  # fmt: skip
                return
            except LighthouseError as exc:
                self.case.tasks.append(
                    HumanTask(kind="manual_filing", text=f"POA API submission failed ({exc}).")
                )
        self.case.poa_submission = {"method": "manual"}
        self.case.tasks.append(HumanTask(
            kind="manual_filing",
            text="Upload the signed and countersigned 21-22a to VA (QuickSubmit).",
        ))  # fmt: skip

    def _do_file_intent_to_file(self) -> None:
        if self.case.icn:
            try:
                resp = self.lighthouse.submit_intent_to_file(self.case.icn)
                # "duplicate": an ITF was already active; its date is the one that protects the claim
                self.case.itf = {"date": resp["date"], "expires": resp["expires"], "status": resp["status"],
                                 "method": f"lighthouse_{self.lighthouse.mode}"}  # fmt: skip
                return
            except LighthouseError as exc:
                self.case.tasks.append(
                    HumanTask(kind="manual_filing", text=f"Intent-to-file API call failed ({exc}).")
                )
        self.case.itf = {"date": None, "method": "manual"}
        self.case.tasks.append(
            HumanTask(
                kind="manual_filing", text="File VA Form 21-0966 (intent to file) for the veteran."
            )
        )

    def _do_request_attorney_signoff(self) -> None:
        self.case.phase = "attorney_signoff"
        self.case.awaiting_veteran = False
        self.case.tasks.append(HumanTask(
            kind="approval",
            text="Attorney: review the veteran's signed 21-22a and countersign it (Item 25A) so the firm can file it.",
        ))  # fmt: skip
        self._say(
            "Our attorney will now review and countersign the form, and then we file it with VA. "
            "After that we'll request your VA claims file, and I'll come back to you with a few last questions.",
            [{"type": "attorney_signoff", "document_id": self.case.poa_document_id}],
        )

    def _do_fetch_cfile(self) -> None:
        """Request the C-file. It arrives as its own event (`cfile_ready`), the next wake; in the
        stub that is right away, with VA it takes weeks (VA must first record the 21-22a)."""
        self.case.phase = "case_prep"
        persona = self.persona
        if persona is None and self.case.persona_id:
            persona = get_persona(self.case.persona_id)
        # A synthetic C-file only when the stub is serving this persona's VA records; with recorded
        # or sandbox records it would belong to a different (made-up) veteran.
        if persona is None or self.lighthouse.mode != "stub":
            self.case.cfile_manual = True  # pass 2 runs without it; staff pull it from VBMS
            self.case.tasks.append(
                HumanTask(kind="manual_filing", text="Download the C-file from VBMS for case prep.")
            )
            return
        self.documents.ensure(persona)
        listing = self.documents.search(persona.icn)

        def arrive() -> None:
            self.case.cfile_documents = listing

        self._event("cfile_ready", arrive=arrive, documents=len(listing))

    def _do_run_claims_prep(self) -> None:
        """Claims prep (the firm's claims team): read the C-file into cited facts, write the face note,
        pre-fill what pass 2 would ask, and compare the C-file with what intake already holds."""
        icn = self.persona.icn if self.persona else self.case.icn
        extractor = make_dspy_extractor(self.lm) if self.provider == "dspy" else OfflineExtractor()
        record = self.intake.record
        try:
            pdfs = [self.documents.download(icn, d["documentId"]) for d in self.case.cfile_documents]
            names = [d.get("subject") or f"document {i}" for i, d in enumerate(self.case.cfile_documents, 1)]
            facts, _, skipped = extract_cfile(pdfs, extractor, names)
            facts = without_firm(facts, self.rep)
            # Intake pass 2's head start: conflicts first (the C-file's version is applied in
            # fetch/confirm), then the answers the C-file settles.
            found = reconcile(record, facts)
            changed: list[str] = []
            if self.agent_config.cfile_mode != "off":
                changed = apply_cfile(record, facts, found)
            prefill = cfile_intake_values(facts)
        except Exception as exc:  # odd model output (e.g. an unparseable date): a person reads it
            self.case.tasks.append(HumanTask(
                kind="review", text=f"C-file pipeline failed ({type(exc).__name__}); read the C-file by hand.",
            ))  # fmt: skip
            self.case.face_note = "(face note not generated; see staff tasks)"
            res = SubagentResult(agent="claims_prep", status="needs_person", event="claims_prep_complete",
                                 wrote=["face_note", "tasks"], needs=["staff: read the C-file"])  # fmt: skip
            self._event("claims_prep_complete", result=res.model_dump())
            return
        self.case.cfile_facts = facts
        self.case.cfile_skipped = skipped
        self.case.cfile_discrepancies = [d.text for d in found]
        self.intake.note_cfile_discrepancies(self.case.cfile_discrepancies)
        self.case.cfile_prefilled = self.intake.prefill_from_cfile(prefill)
        for d in found:
            self.case.tasks.append(HumanTask(kind="review", text=f"C-file vs intake: the C-file shows {d.text}."))

        try:
            note = render(
                facts,
                fee_pct=rules.fee_pct(record),
                itf_date=(self.case.itf or {}).get("date"),
                intake_dob=self.svc.vault.veteran().get("date_of_birth"),
                firm=self.rep.get("firm_name", "Law Firm"),
                as_of=self.as_of,
            )
        except Exception as exc:
            self.case.tasks.append(HumanTask(
                kind="review", text=f"Face-note template failed ({type(exc).__name__}); write it by hand.",
            ))  # fmt: skip
            self.case.face_note = "(face note not generated; see staff tasks)"
        else:
            self.case.face_note = note.text
            self.case.face_note_flags = note.flags
            for d in note.deadlines:
                self.case.tasks.append(HumanTask(
                    kind="deadline",
                    due=d["deadline"],
                    text=f"AMA appeal deadline for the decision of {d['decision_date']}: {', '.join(d['conditions'])}.",
                ))  # fmt: skip
            for flag in note.flags:
                self.case.tasks.append(HumanTask(kind="review", text=flag))
        res = SubagentResult(
            agent="claims_prep", status="done", event="claims_prep_complete",
            wrote=["cfile_facts", "face_note", "cfile_prefilled", "cfile_discrepancies"] + [f"intake.{c}" for c in changed],
            needs=["intake pass 2"] + (["the veteran confirms what the C-file contradicts"] if record.cfile_discrepancies else []),
            flags=list(self.case.face_note_flags),
        )  # fmt: skip
        self._event("claims_prep_complete", result=res.model_dump())

    def _do_continue_intake(self) -> None:
        """Intake pass 2: only what the C-file, VA's records and the secure form didn't settle."""
        self.case.phase = "intake"
        vault = self.svc.vault.veteran()
        flat = {
            "first_name": vault.get("first_name"),
            "last_name": vault.get("last_name"),
            "address.line1": (vault.get("address") or {}).get("line1"),
            "address.city": (vault.get("address") or {}).get("city"),
            "address.state": (vault.get("address") or {}).get("state"),
            "address.zip": (vault.get("address") or {}).get("zip"),
            "phone": vault.get("phone"),
            "email": vault.get("email"),
        }
        self.intake.prefill_secure_form({VAULT_TO_INTAKE[k]: v for k, v in flat.items() if v})
        if self.case.cfile_documents:
            self._say("Thanks for your patience. We now have your VA claims file, so I only have a few questions left.")
        self._intake_turn(self.intake.start("post_poa"))

    def _do_send_to_attorney_review(self) -> None:
        self.case.phase = "attorney_review"
        self.case.tasks.append(
            HumanTask(
                kind="review",
                text="Attorney: review the intake record, the signed 21-22a and the face note.",
            )
        )
        self._say(
            "Your file is with our attorney now. Someone from our team will contact you about next steps."
        )

    def _do_pass_flags_to_staff(self) -> None:
        for f in self.case.open_flags:
            self.case.tasks.append(HumanTask(
                kind="handoff" if f["kind"] in _URGENT_FLAGS else "review",
                text=f"Veteran's {f['kind'].replace('_', ' ')} ({f['phase']}): {f['text']}",
            ))  # fmt: skip
        if any(f["kind"] == "new_condition" for f in self.case.open_flags):
            self._say("Our team will look at adding it and contact you before anything changes.")
        self.case.open_flags = []

    def _do_reopen_intake_for_new_condition(self) -> None:
        """The veteran wants to add a condition after pass 2: intake asks which one, then its
        narrative prompts; the case goes back to attorney review after that (the orchestrator)."""
        texts = [f["text"] for f in self.case.open_flags if f["kind"] == "new_condition"]
        self.case.open_flags = [f for f in self.case.open_flags if f["kind"] != "new_condition"]
        self.case.phase = "intake"
        self.case.intake_outcome = None
        self.case.tasks.append(HumanTask(kind="review", text=f"Intake reopened for a new condition: {' / '.join(texts)[:300]}"))
        self._intake_turn(self.intake.reopen_for_new_condition())

    def _do_close_case(self) -> None:
        self.case.phase = "closed"

    def _do_hand_off_to_staff(self) -> None:
        self.case.phase = "human_handoff"
        self.case.tasks.append(
            HumanTask(kind="handoff", text="; ".join(self.case.attention()) or "Needs a person.")
        )

    # ------------------------------------------------------------------ views

    def case_view(self) -> dict[str, Any]:
        c = self.case
        view = c.summary()
        view.update({
            "case_id": c.case_id,
            "provider": self.provider,
            "lighthouse_mode": self.lighthouse.mode,
            "records_mode": self.intake.config.records_mode,
            "decisions": [d.model_dump() for d in c.decisions[-30:]],
            "tasks": [t.model_dump() for t in c.tasks],
            "intake": json.loads(c.intake.model_dump_json(exclude_defaults=True)) if c.intake else None,
            "records_prefilled": c.records_prefilled,
            "va_records": c.va_records.model_dump(exclude={"icn"}) if c.va_records else None,
            "poa_document_id": c.poa_document_id,
            "poa_submission": c.poa_submission,
            "itf": c.itf,
            "face_note": c.face_note,
            "face_note_flags": c.face_note_flags,
            "cfile_documents": c.cfile_documents,
            "chat_phase": c.phase in CHAT_PHASES,
        })  # fmt: skip
        return view
