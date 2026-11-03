"""The runtime protocol (plan §3): wakes, message routing, queued turns, delivery.

  open_case / message / event   the only ways in (the web chat, card actions, staff actions)
  route (D1)                    the case's owner gets the veteran's messages (intake, including
                                while it waits on the attorney); otherwise support
  crisis (D3), person (D2)      checked in code on every message, in every state, before any
                                model: the crisis line, or a hand-off to a person, then needs_human
  wakes                         case_opened, subagent_result, support_flag, escalated and staff
                                events nobody owns wake the orchestrator; nothing else does
  executor                      one worker per case runs queued turns in order; claims prep
                                runs on a second, background worker so the chat stays live
  delivery                      every reply and card goes to the store's outbox

All case changes go through `patch`, which applies a change under the store's lock and then
re-derives the stage (agent.stages.settle).
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent import stages
from agent.casefile import CaseFile, Flag, SubagentResult, Task
from agent.harness import OWNING, AgentSpec, Harness, Turn, TurnOutcome
from agent.ingest import ingest, wants_withdraw
from agent.intake.controller import CRISIS_MESSAGE, HANDOFF_MESSAGE, QATool
from agent.store import Event, Store
from agent.traces import TraceLog

WITHDRAW_MESSAGE = (
    "I've passed your request to our team. A person will contact you to confirm before anything "
    "about your representation changes."
)
MAX_CONTINUATIONS = 3  # claims prep turns that end before the stop rule (max_iters, early) are continued
CHAT_EVENT_TYPES = ("message",)  # never in the orchestrator's memory block (no transcripts)


@dataclass
class Job:
    agent: str
    incoming: str
    kind: str  # wake | start | message | event | continue


class Runtime:
    def __init__(self, store: Store, harness: Harness, agents: dict[str, AgentSpec], kb: QATool | None = None) -> None:
        self.store = store
        self.harness = harness
        self.agents = agents
        self.kb = kb  # the kb_search engine (agent/kb.py): question -> QAResult
        self._cond = threading.Condition()
        self._queues: dict[tuple[str, str], deque[Job]] = {}
        self._active: set[tuple[str, str]] = set()
        self._pending: dict[str, int] = {}
        self._running: dict[str, set[str]] = {}
        self._turns: dict[tuple[str, str], int] = {}
        self._errors: list[BaseException] = []

    # ---------------------------------------------------------------- ways in

    def open_case(self, persona_id: str | None = None) -> CaseFile:
        case = self.store.create_case(CaseFile(case_id=uuid.uuid4().hex[:12], persona_id=persona_id))
        self._wake(case.case_id, self.store.append_event(case.case_id, "case_opened", {}, actor="host"))
        return case

    def message(self, case_id: str, text: str) -> None:
        """A chat message from the veteran: redact, crisis and person checks in code, then route."""
        msg = ingest(text)
        case = self.store.get_case(case_id)
        if msg.crisis:
            self._to_person(case_id, msg.clean, "crisis", CRISIS_MESSAGE, urgent=True)
            return
        if msg.wants_human or wants_withdraw(msg.clean):  # in every state: a person reads it
            kind = "withdraw" if wants_withdraw(msg.clean) else "wants_human"
            self._to_person(case_id, msg.clean, kind, WITHDRAW_MESSAGE if kind == "withdraw" else HANDOFF_MESSAGE)
            return
        agent = route(case)
        self._log_message(case_id, "veteran", agent, msg.clean, redacted=msg.redacted)
        if agent == case.owner:
            self.patch(case_id, lambda c: setattr(c, "awaiting_veteran", False), actor="veteran")
        self._enqueue(case_id, Job(agent, msg.clean, "message"))

    def event(self, case_id: str, type: str, data: dict | None = None, actor: str = "host",
              apply: Callable[[CaseFile], Any] | None = None) -> Event:  # fmt: skip
        """A card action or a staff action. `apply` records its effect on the case file first.
        The owner (intake) handles it in its next turn; with no owner it wakes the orchestrator."""
        if apply:
            self.patch(case_id, apply, actor=actor)
        event = self.store.append_event(case_id, type, data or {}, actor=actor)
        case = self.store.get_case(case_id)
        if case.owner == "intake" and not case.parked:
            self._enqueue(case_id, Job("intake", f"[event] {event.line()}", "event"))
        else:
            self._wake(case_id, event)
        return event

    def updates(self, case_id: str, since: int = 0):
        return self.store.outbox_since(case_id, since)

    def wait_until_idle(self, case_id: str | None = None, timeout: float = 60.0) -> None:
        """Block until no turn is queued or running (for one case, or all). Re-raises a crash."""
        with self._cond:
            done = self._cond.wait_for(
                lambda: (self._pending.get(case_id, 0) if case_id else sum(self._pending.values())) == 0,
                timeout,
            )
            errors, self._errors = self._errors, []
        if errors:
            raise RuntimeError(f"{len(errors)} turn(s) crashed") from errors[0]
        if not done:
            raise TimeoutError("turns still running")

    def running(self, case_id: str) -> set[str]:
        with self._cond:
            return set(self._running.get(case_id, ()))

    # ---------------------------------------------------------------- case changes

    def patch(self, case_id: str, fn: Callable[[CaseFile], list[dict] | None], actor: str) -> CaseFile:
        """Apply `fn` under the case's lock, then derive the stage; log the events of both.
        `fn` mutates the case and may return events of its own ({type, data})."""
        events: list[dict] = []

        def apply(case: CaseFile) -> None:
            events.extend(fn(case) or [])
            events.extend(stages.settle(case))

        case = self.store.update_case(case_id, apply)
        for e in events:
            self.store.append_event(case_id, e["type"], e["data"], actor=e["data"].get("actor", actor))
        return case

    def move(self, case_id: str, to: int | str, actor: str, reason: str | None) -> dict:
        """A guarded stage or side-state move; returns its event (`refused` with the reason)."""
        out: list[dict] = []

        def apply(case: CaseFile) -> list[dict]:
            out.append(stages.move(case, to, actor, reason))
            return out

        self.patch(case_id, apply, actor)
        return out[0]

    def flag(self, case_id: str, kind: str, text: str, turn: Turn) -> str:
        """support_flag: wakes the orchestrator after the turn, or is held while claims prep runs."""
        flag = Flag(kind=kind, text=text)

        def add(case: CaseFile) -> None:
            # Decided under the lock: claims prep's hand-back clears the owner under the same lock,
            # so a held flag is always there when its result wakes the orchestrator.
            flag.status = "held" if case.owner == "claims_prep" else "open"
            case.flags.append(flag)

        self.patch(case_id, add, actor=turn.agent)
        event = self.store.append_event(case_id, "support_flag", flag.model_dump(), actor=turn.agent)
        if flag.status == "open":
            turn.deferred.append(self.wake_job(event))
        return "held until claims prep returns" if flag.status == "held" else "passed to the orchestrator"

    def escalate(self, case_id: str, reason: str, actor: str, urgent: bool = False, detail: str | None = None) -> Event:
        """A staff task (with `detail`, e.g. the veteran's words) and an `escalated` event."""
        task = Task(kind="urgent" if urgent else "staff", text=detail or reason)
        self.patch(case_id, lambda c: c.tasks.append(task), actor=actor)
        return self.store.append_event(case_id, "escalated", {"reason": reason}, actor=actor)

    def say(self, case_id: str, agent: str, text: str) -> None:
        self.store.post(case_id, "message", {"text": text}, agent=agent)
        self._log_message(case_id, agent, "veteran", text)

    def post_card(self, case_id: str, agent: str, card: dict) -> None:
        self.store.post(case_id, "card", card, agent=agent)

    # ---------------------------------------------------------------- internals

    def _to_person(self, case_id: str, text: str, kind: str, reply: str, urgent: bool = False) -> None:
        """D2/D3: by rule, no model: reply, a staff task, needs_human, and wake the orchestrator."""
        self._log_message(case_id, "veteran", "rule", text)
        self.say(case_id, "rule", reply)
        event = self.escalate(case_id, kind, actor="rule", urgent=urgent, detail=f"{kind}: {text}")
        if not self.store.get_case(case_id).parked:
            self.move(case_id, "needs_human", "rule", kind)
        self._wake(case_id, event)

    def _log_message(self, case_id: str, sender: str, to: str, text: str, **extra: Any) -> None:
        self.store.append_event(case_id, "message", {"from": sender, "to": to, "text": text, **extra}, actor=sender)

    def wake_job(self, event: Event) -> Job:
        return Job("orchestrator", event.line(), "wake")

    def _wake(self, case_id: str, event: Event) -> None:
        self._enqueue(case_id, self.wake_job(event))

    def _enqueue(self, case_id: str, job: Job) -> None:
        lane = (case_id, "background" if job.agent == "claims_prep" else "main")
        with self._cond:
            self._queues.setdefault(lane, deque()).append(job)
            self._pending[case_id] = self._pending.get(case_id, 0) + 1
            if lane not in self._active:
                self._active.add(lane)
                threading.Thread(target=self._drain, args=lane, daemon=True).start()

    def _drain(self, case_id: str, lane: str) -> None:
        while True:
            with self._cond:
                queue = self._queues[(case_id, lane)]
                if not queue:
                    self._active.discard((case_id, lane))
                    return
                job = queue.popleft()
                self._running.setdefault(case_id, set()).add(job.agent)
            try:
                self._run(case_id, job)
            except BaseException as err:  # noqa: BLE001 - surfaced by wait_until_idle
                self._errors.append(err)
                self.store.append_event(case_id, "turn_crashed", {"agent": job.agent, "error": repr(err)})
            finally:
                with self._cond:
                    self._running[case_id].discard(job.agent)
                    self._pending[case_id] -= 1
                    self._cond.notify_all()

    def _run(self, case_id: str, job: Job) -> None:
        spec = self.agents[job.agent]
        case = self.store.get_case(case_id)
        if job.agent in OWNING and case.owner != job.agent:
            self.store.append_event(case_id, "turn_skipped", {"agent": job.agent, "reason": "not the owner"})
            return
        key = (case_id, job.agent)
        self._turns[key] = self._turns.get(key, 0) + 1
        turn = Turn(self, case_id, job.agent, job.incoming, self._turns[key],
                    owner_at_start=case.owner == job.agent, kind=job.kind)  # fmt: skip
        flags_seen = case.flags_to_decide()
        outcome = self.harness.run(spec, turn)
        if outcome.reply:
            self.say(case_id, job.agent, outcome.reply)
        if job.agent == "orchestrator":
            self._after_wake(case_id, turn, outcome, flags_seen)
        elif turn.owner_at_start:
            self._after_owner_turn(case_id, spec, turn, outcome)
        for deferred in turn.deferred:
            self._enqueue(case_id, deferred)

    def _after_wake(self, case_id: str, turn: Turn, outcome: TurnOutcome, flags_seen: list[int]) -> None:
        def handled(case: CaseFile) -> None:
            for i in flags_seen:
                case.flags[i].status = "handled"

        if flags_seen and outcome.status == "ok":
            self.patch(case_id, handled, actor="orchestrator")
        if outcome.status != "ok" and turn.handoff is None and not self.store.get_case(case_id).parked:
            self.move(case_id, "needs_human", "harness", f"orchestrator turn {outcome.status}: {outcome.detail}")

    def _after_owner_turn(self, case_id: str, spec: AgentSpec, turn: Turn, outcome: TurnOutcome) -> None:
        case = self.store.get_case(case_id)
        assert spec.stop is not None
        if spec.stop(case) or case.parked:
            result = outcome.result or SubagentResult(
                agent=spec.name, finished=f"stage {case.stage}" + (f", {case.side_state}" if case.side_state else "")
            )

            def hand_back(c: CaseFile) -> None:
                if c.owner == spec.name:
                    c.owner, c.goal = None, None
                c.awaiting_veteran = False

            self.patch(case_id, hand_back, actor=spec.name)
            event = self.store.append_event(
                case_id, "subagent_result", {"result": result.model_dump(), "stage": case.stage}, actor=spec.name
            )
            self._wake(case_id, event)
            return
        if outcome.result is not None:
            self.store.append_event(case_id, "result_ignored", {"reason": "stop rule not met"}, actor=spec.name)
        if spec.on_limit == "continue":
            # Claims prep has nobody to wait for: a turn that ends before its stop rule holds (at the
            # step limit, or early) is continued, and the new turn picks up from the case file.
            if outcome.status != "failed" and case.prep.continuations < MAX_CONTINUATIONS:
                self.patch(case_id, lambda c: setattr(c.prep, "continuations", c.prep.continuations + 1), spec.name)
                why = "hit its step limit" if outcome.status == "limit" else "ended before your stop rule held"
                note = f"[continue] Your last turn {why}; pick up where it stopped. Goal: {case.goal}"
                turn.deferred.append(Job(spec.name, note, "continue"))
            else:
                detail = outcome.detail or f"stop rule not met after {MAX_CONTINUATIONS} continuations"
                self.move(case_id, "needs_human", "harness", f"{spec.name} turn {outcome.status}: {detail}")
            return
        if outcome.reply:
            self.patch(case_id, lambda c: setattr(c, "awaiting_veteran", True), actor=spec.name)


def make_runtime(data_dir: Path, lm, kb: QATool | None = None) -> Runtime:
    """The runtime with the orchestrator, intake, claims prep and support. `kb`: the kb_search
    engine; by default the web-search QA (agent/qa.py)."""
    from agent import orchestrator
    from agent.claims_prep import agent as claims_prep
    from agent.intake import agent as intake
    from agent.qa import make_qa
    from agent.support import agent as support

    harness = Harness(lm, TraceLog(Path(data_dir) / "traces.jsonl"))
    agents = {"orchestrator": orchestrator.spec(), "intake": intake.spec(), "claims_prep": claims_prep.spec(),
              "support": support.spec()}  # fmt: skip
    return Runtime(Store(Path(data_dir) / "cases.sqlite"), harness, agents, kb=kb or make_qa("openrouter"))


def route(case: CaseFile) -> str:
    """D1: who answers the veteran's message."""
    if not case.parked and case.owner == "intake":
        return "intake"
    return "support"
