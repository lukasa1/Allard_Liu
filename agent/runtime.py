"""The runtime protocol (plan §3): wakes, message routing, queued turns, delivery.

  open_case / message / event   the only ways in (the web chat, card actions, staff actions)
  route (D1)                    the case's owner gets the veteran's messages (intake, including
                                while it waits on the attorney); otherwise support. Decided
                                again when the queued turn runs: the owner may have changed
  crisis (D3), person (D2)      checked in code on every message, in every state, before any
                                model: the crisis line, or a hand-off to a person, then needs_human
  wakes                         case_opened, subagent_result, support_flag, escalated and staff
                                events nobody owns wake the orchestrator; nothing else does
  executor                      one worker per case runs queued turns in order; claims prep
                                runs on a second, background worker so the chat stays live
  delivery                      every reply and card goes to the store's outbox; a turn queued
                                before a hand-off to a person by rule (crisis, a request for a
                                person), an orchestrator wake on a case a rule parked, or a turn
                                that lost the case has its reply held back (logged)
  failures                      a crashed or failed turn, or claims prep out of continuations,
                                parks the case at needs_human with a staff task naming the
                                undecided flags; a support crash sends the canned reply and a
                                staff task, and leaves the case where it is

All case changes go through `patch`, which applies a change under the store's lock and then
re-derives the stage (agent.stages.settle).
"""

from __future__ import annotations

import dataclasses
import json
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent import clock, stages
from agent.casefile import CaseFile, EvalCondition, Flag, SubagentResult, Task
from agent.harness import CANNED_REPLY, OWNING, AgentSpec, Harness, Turn, TurnOutcome
from agent.ingest import (
    CRISIS_MESSAGE,
    HANDOFF_MESSAGE,
    WITHDRAW_MESSAGE,
    ingest,
    untrusted,
    wants_withdraw,
)
from agent.qa import QATool
from agent.store import Event, Store
from agent.traces import TraceLog

MAX_CONTINUATIONS = 3  # claims prep turns that end before the stop rule (max_iters, early) are continued
CHAT_EVENT_TYPES = ("message",)  # never in the orchestrator's memory block (no transcripts)
# Wakes whose data may quote the veteran (L6); a sub-agent's result is model text written from it.
QUOTING_WAKES = ("support_flag", "escalated", "subagent_result")


@dataclass
class Job:
    agent: str
    incoming: str
    kind: str  # wake | start | message | event | continue | nudge
    redacted: bool = False  # message: ingest hid an ID number or a date of birth
    front: bool = False  # queued ahead of the lane's waiting jobs (a turn's own follow-ups)
    to_person: int = -1  # the case's rule hand-offs when queued (set by _enqueue); a later one holds the reply


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
        self._errors: list[tuple[str, BaseException]] = []
        self._to_person_count: dict[str, int] = {}  # per case: D2/D3 hand-offs to a person so far
        self._say_lock = threading.Lock()  # a reply's hold check and its send vs. a rule's hand-off

    # ---------------------------------------------------------------- ways in

    def open_case(self, persona_id: str | None = None, eval_condition: EvalCondition = "cfile") -> CaseFile:
        case = self.store.create_case(CaseFile(case_id=clock.token_hex(6), persona_id=persona_id,
                                               eval_condition=eval_condition))  # fmt: skip
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
        agent = route(case)  # logged when the turn runs (_reroute): the owner may change meanwhile
        if agent == case.owner:
            self.patch(case_id, lambda c: setattr(c, "awaiting_veteran", False), actor="veteran")
        self._enqueue(case_id, Job(agent, msg.clean, "message", msg.redacted))

    def event(self, case_id: str, type: str, data: dict | None = None, actor: str = "host",
              apply: Callable[[CaseFile], Any] | None = None) -> Event:  # fmt: skip
        """A card action or a staff action. `apply` records its effect on the case file first.
        The owner (intake) handles it in its next turn; with no owner it wakes the orchestrator."""
        if apply:
            self.patch(case_id, apply, actor=actor)
        event = self.store.append_event(case_id, type, data or {}, actor=actor)
        owner = self.store.get_case(case_id).owner
        self._enqueue(case_id, Job("intake" if owner == "intake" else "orchestrator", event.line(), "event"))
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
            errors = [e for c, e in self._errors if case_id in (None, c)]
            self._errors = [(c, e) for c, e in self._errors if case_id not in (None, c)]
        if errors:
            raise RuntimeError(f"{len(errors)} turn(s) crashed") from errors[0]
        if not done:
            raise TimeoutError("turns still running")

    def running(self, case_id: str) -> set[str]:
        with self._cond:
            return set(self._running.get(case_id, ()))

    def busy(self, case_id: str) -> bool:
        """True while any turn for the case is queued or running."""
        with self._cond:
            return self._pending.get(case_id, 0) > 0

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
        if (kind, text) in turn.flags_raised:  # a retried attempt raising it again
            return "already passed on this turn"
        turn.flags_raised.append((kind, text))
        flag = Flag(kind=kind, text=text)

        def add(case: CaseFile) -> None:
            # Decided under the lock: claims prep's hand-back clears the owner under the same lock,
            # so a held flag is always there when its result wakes the orchestrator.
            flag.status = "held" if case.owner == "claims_prep" else "open"
            case.flags.append(flag)

        self.patch(case_id, add, actor=turn.agent)
        event = self.store.append_event(case_id, "support_flag", flag.model_dump(), actor=turn.agent)
        if flag.status == "open" and not turn.flag_woke:  # one wake shows every open flag
            turn.flag_woke = True
            turn.deferred.append(self.wake_job(event))
        return "held until claims prep returns" if flag.status == "held" else "passed to the orchestrator"

    def escalate(self, case_id: str, reason: str, actor: str, urgent: bool = False, detail: str | None = None) -> Event:
        """A staff task (with `detail`, e.g. the veteran's words) and an `escalated` event."""
        add_task(self, case_id, Task(kind="urgent" if urgent else "staff", text=detail or reason), actor)
        return self.store.append_event(case_id, "escalated", {"reason": reason}, actor=actor)

    def say(self, case_id: str, agent: str, text: str) -> None:
        self.store.post(case_id, "message", {"text": text}, agent=agent)
        self._log_message(case_id, agent, "veteran", text)

    def post_card(self, case_id: str, agent: str, card: dict) -> None:
        self.store.post(case_id, "card", card, agent=agent)

    # ---------------------------------------------------------------- internals

    def _to_person(self, case_id: str, text: str, kind: str, reply: str, urgent: bool = False) -> None:
        """D2/D3: by rule, no model: reply, a staff task, needs_human, and wake the orchestrator.
        A turn running meanwhile has its reply held back (`_run`)."""
        with self._say_lock:  # no agent reply checked before this count lands after the rule's
            with self._cond:
                self._to_person_count[case_id] = self._to_person_count.get(case_id, 0) + 1
            self._log_message(case_id, "veteran", "rule", text)
            self.say(case_id, "rule", reply)
        event = self.escalate(case_id, kind, actor="rule", urgent=urgent, detail=f"{kind}: {text}")
        if not self.store.get_case(case_id).parked:
            self.move(case_id, "needs_human", "rule", kind)
        self._wake(case_id, event)

    def _log_message(self, case_id: str, sender: str, to: str, text: str, **extra: Any) -> None:
        self.store.append_event(case_id, "message", {"from": sender, "to": to, "text": text, **extra}, actor=sender)

    def wake_job(self, event: Event) -> Job:
        if event.type in QUOTING_WAKES:
            return Job("orchestrator", f"[wake] {event.type}\n" + untrusted("the waking event", event.line()), "wake")
        return Job("orchestrator", event.line(), "wake")

    def _wake(self, case_id: str, event: Event) -> None:
        self._enqueue(case_id, self.wake_job(event))

    def _enqueue(self, case_id: str, job: Job) -> None:
        lane = (case_id, "background" if job.agent == "claims_prep" else "main")
        with self._cond:
            if job.to_person < 0:
                job.to_person = self._to_person_count.get(case_id, 0)
            queue = self._queues.setdefault(lane, deque())
            queue.appendleft(job) if job.front else queue.append(job)
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
            after: list[Job] = []
            try:
                job = self._reroute(case_id, job)
                after = self._run(case_id, job)
            except BaseException as err:  # noqa: BLE001 - surfaced by wait_until_idle
                with self._cond:
                    self._errors.append((case_id, err))
                self.store.append_event(case_id, "turn_crashed", {"agent": job.agent, "error": repr(err)})
                self._crashed(case_id, job, err)
            finally:
                # Under one lock: the turn's follow-ups (a handoff's first turn, a sub-agent's result
                # wake) never see this agent still running.
                with self._cond:
                    self._running[case_id].discard(job.agent)
                    for follow in after:
                        self._enqueue(case_id, follow)
                    self._pending[case_id] -= 1
                    self._cond.notify_all()

    def _reroute(self, case_id: str, job: Job) -> Job:
        """A1: a message or a card/staff event goes to whoever should get it now, not when it was
        queued (the owner may have handed back, or taken the case, meanwhile). A message is logged
        here, once, to the agent that answers it."""
        if job.kind not in ("message", "event"):
            return job
        case = self.store.get_case(case_id)
        if job.kind == "message":
            agent = route(case)
            moved = {"rerouted_from": job.agent} if agent != job.agent else {}
            self._log_message(case_id, "veteran", agent, job.incoming, redacted=job.redacted, **moved)
        else:  # intake handles it while it owns the case; otherwise it wakes the orchestrator
            agent = "intake" if case.owner == "intake" else "orchestrator"
        if agent == job.agent:
            return job
        new = dataclasses.replace(job, agent=agent)
        with self._cond:
            self._running[case_id].discard(job.agent)
            self._running[case_id].add(new.agent)
        return new

    def _crashed(self, case_id: str, job: Job, err: BaseException) -> None:
        """A crashed turn leaves the case with a person, not stuck with an owner that never runs.
        Support owns nothing: its crash gets the canned reply and a staff task, and the case stays."""
        why = f"{job.agent} turn crashed: {type(err).__name__}"
        try:
            if job.agent == "support":
                if job.kind == "message":
                    self._deliver(case_id, "support", CANNED_REPLY, job.to_person)
                add_task(self, case_id, Task(kind="staff", text=f"{why}; check the veteran's last message"), "harness")
            else:
                self.to_staff(case_id, why)
        except Exception as again:  # noqa: BLE001 - the crash itself is already recorded and re-raised
            self.store.append_event(case_id, "turn_crashed", {"agent": "harness", "error": repr(again)})

    def to_staff(self, case_id: str, why: str) -> None:
        """The harness parks the case (a failed or crashed turn, claims prep out of continuations):
        needs_human (unless already parked), and a staff task naming the flags nobody decided. A
        repeat of the same failure ("<agent> turn <status>") while its task is open adds nothing."""
        case = self.store.get_case(case_id)
        if not case.parked:
            self.move(case_id, "needs_human", "harness", why)
        key = why.split(":")[0]
        if any(t.kind == "staff" and t.done_at is None and t.text.startswith(key) for t in case.tasks):
            return
        flags = [f"{f.kind}: {f.text}" for f in case.flags if f.status != "handled"]
        text = why + ("; undecided support flags: " + " | ".join(flags) if flags else "")
        add_task(self, case_id, Task(kind="staff", text=text), "harness")

    def _run(self, case_id: str, job: Job) -> list[Job]:
        """Run one turn; returns its follow-up jobs (`_drain` queues them)."""
        spec = self.agents[job.agent]
        case = self.store.get_case(case_id)
        if job.agent in OWNING and case.owner != job.agent:
            self.store.append_event(case_id, "turn_skipped", {"agent": job.agent, "reason": "not the owner"})
            return []
        key = (case_id, job.agent)
        self._turns[key] = self._turns.get(key, 0) + 1
        text = f"[event] {job.incoming}" if (job.kind, job.agent) == ("event", "intake") else job.incoming
        turn = Turn(self, case_id, job.agent, text, self._turns[key], owner_at_start=case.owner == job.agent,
                    kind=job.kind)  # fmt: skip
        try:
            outcome = self.harness.run(spec, turn)
            if outcome.reply:
                self._deliver(case_id, turn.agent, outcome.reply, job.to_person, turn.owner_at_start)
        finally:  # the cards its tools made follow the reply that introduces them (even if it crashed)
            self._post_cards(case_id, turn, job.to_person)
        after: list[Job] = []
        if job.agent == "orchestrator":
            self._after_wake(case_id, turn, outcome)
        elif turn.owner_at_start:
            after = self._after_owner_turn(case_id, spec, turn, outcome, job)
        for deferred in turn.deferred:  # the turn's own follow-ups run next (D9), in order
            deferred.front = True
        return list(reversed(turn.deferred)) + after

    def _held(self, case_id: str, agent: str, to_person: int, owner_at_start: bool) -> str | None:
        """D3: why what a turn says now must not reach the veteran, or None. A turn that started
        before a person took over (a crisis, a request for a person), or that lost the case
        meanwhile, is not heard: the rule's message is the last word. Neither is the
        orchestrator on a case a rule parked."""
        case = self.store.get_case(case_id)
        with self._cond:
            ruled = self._to_person_count.get(case_id, 0)
        if ruled != to_person:
            return "the case went to a person by rule"
        if agent == "orchestrator" and case.parked and ruled:
            return f"the case is {case.side_state} after a hand-off to a person by rule"
        if owner_at_start and case.owner != agent and case.stop is None:
            return f"{agent} lost the case during the turn ({case.side_state or 'no owner'})"
        return None

    def _deliver(self, case_id: str, agent: str, reply: str, to_person: int, owner_at_start: bool = False) -> None:
        """A turn's reply, unless it is held (D3, `_held`)."""
        with self._say_lock:
            why = self._held(case_id, agent, to_person, owner_at_start)
            if why:
                self.store.append_event(case_id, "reply_held", {"agent": agent, "reason": why, "text": reply},
                                        actor=agent)  # fmt: skip
            else:
                self.say(case_id, agent, reply)

    def _post_cards(self, case_id: str, turn: Turn, to_person: int) -> None:
        """The cards a turn's tools made, after its reply. A repeat (a retried attempt, harness L4,
        repeats its tool calls) shows once, where it last came, so the newest card stays the
        newest. Held by the same rule as the reply (D3), whether the turn replied, said nothing or
        crashed: the rule's message stays the last word. Held cards are kept in the event."""
        cards = _last_of_each(turn.cards)
        if not cards:
            return
        with self._say_lock:
            why = self._held(case_id, turn.agent, to_person, turn.owner_at_start)
            if why:
                self.store.append_event(case_id, "cards_held", {"agent": turn.agent, "reason": why, "cards": cards},
                                        actor=turn.agent)  # fmt: skip
            else:
                for card in cards:
                    self.post_card(case_id, turn.agent, card)

    def _after_wake(self, case_id: str, turn: Turn, outcome: TurnOutcome) -> None:
        def handled(case: CaseFile) -> None:
            for i in set(turn.flags_shown):
                case.flags[i].status = "handled"

        # The flags its context showed are decided only if something went through (a handoff, a
        # move, a staff task); otherwise they stay open and show again at the next wake.
        if turn.flags_shown and turn.acted and outcome.status == "ok":
            self.patch(case_id, handled, actor="orchestrator")
        if outcome.status != "ok" and turn.handoff is None:
            self.to_staff(case_id, f"orchestrator turn {outcome.status}: {outcome.detail}")

    def _after_owner_turn(self, case_id: str, spec: AgentSpec, turn: Turn, outcome: TurnOutcome, job: Job) -> list[Job]:
        """The owner's stop rule: hand back (returns the result's wake), continue, or wait."""
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
            return [self.wake_job(event)]
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
                self.to_staff(case_id, f"{spec.name} turn {outcome.status}: {detail}")
            return []
        if not outcome.reply and outcome.status == "ok" and job.kind in ("message", "event", "nudge"):
            # The veteran is waiting and the turn sent nothing (D28): one more turn is asked to
            # answer; if that one is empty too, the canned reply goes out, so the chat never stalls.
            if job.kind == "nudge":
                self._deliver(case_id, spec.name, CANNED_REPLY, job.to_person, turn.owner_at_start)
                return []
            what = untrusted("veteran message", turn.incoming) if job.kind == "message" else turn.incoming
            note = (f"[nudge] Your last turn ended without a reply, and the veteran is waiting. Answer "
                    f"what they last sent (below) and ask the next question in `reply`.\n{what}")  # fmt: skip
            turn.deferred.append(Job(spec.name, note, "nudge", to_person=job.to_person))
            return []
        if outcome.reply:
            self.patch(case_id, lambda c: setattr(c, "awaiting_veteran", True), actor=spec.name)
        return []


def _last_of_each(cards: list[dict]) -> list[dict]:
    """The cards in order, an exact repeat kept only where it last appears."""
    keys = [json.dumps(c, sort_keys=True) for c in cards]
    return [c for i, c in enumerate(cards) if keys[i] not in keys[i + 1:]]


def make_runtime(data_dir: Path, lm, kb: QATool | None = None) -> Runtime:
    """The runtime with the orchestrator, intake, claims prep and support. `kb`: the kb_search
    engine; by default the web-search QA (agent/qa.py)."""
    from agent import orchestrator
    from agent.claims_prep import agent as claims_prep
    from agent.intake import agent as intake
    from agent.qa import WebSearchQA
    from agent.support import agent as support

    harness = Harness(lm, TraceLog(Path(data_dir) / "traces.jsonl"))
    agents = {"orchestrator": orchestrator.spec(), "intake": intake.spec(), "claims_prep": claims_prep.spec(),
              "support": support.spec()}  # fmt: skip
    return Runtime(Store(Path(data_dir) / "cases.sqlite"), harness, agents, kb=kb or WebSearchQA())


def add_task(rt: Runtime, case_id: str, task: Task, actor: str) -> bool:
    """Add a staff task unless the same one is open already (a retried turn repeats its calls)."""
    added = []

    def apply(case: CaseFile) -> None:
        if not any(t.done_at is None and (t.kind, t.text) == (task.kind, task.text) for t in case.tasks):
            case.tasks.append(task)
            added.append(task)

    rt.patch(case_id, apply, actor=actor)
    return bool(added)


def route(case: CaseFile) -> str:
    """D1: who answers the veteran's message."""
    if case.owner == "intake":  # a parked case has no owner (stages.move)
        return "intake"
    return "support"
