"""The intake subagent's controller: deterministic, with an LLM (or rule-based) brain.

The controller owns WHAT happens: which question comes next, when to stop, when to hand off to a
person. The brain owns HOW: reading free-text replies into typed answers and phrasing questions.
The brain cannot skip a question, end the conversation or change a decision; those are code paths
here and in rules.py ("the engine owns what, the AI owns how").

Intake runs in two passes, which the orchestrator sequences:
  screen    pass 1, before the veteran signs the 21-22a: eligibility, stop rules, fee
  post_poa  pass 2, after claims prep has read the C-file: only what is still missing (the C-file
            and VA's records settle the rest), any pass-1 question that became relevant, a check
            of what the C-file contradicts, then the per-condition narrative prompts

Answers can come from four places (`provenance`): the veteran in chat, VA's records fetched
through Lighthouse (`prefill_from_records`), the POA skill's secure form (`prefill_secure_form`),
or the C-file read by claims prep (`prefill_from_cfile`, set by `cfile_mode`: off | fetch | confirm).
`records_mode` sets how VA's records are used, which is the main ablation in the eval:
  ask            no records: every question is asked in chat
  fetch          records answer their questions; the verification probes are skipped
  fetch_confirm  records answer their questions; the probes are asked, worded around the records
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import rules
from .brains import _WANTS_HUMAN, Brain, Extraction, OfflineBrain, detect_crisis
from .parsing import coerce
from .questions import Ask, QuestionBank, is_visible
from .schema import IntakeRecord, Outcome, ServicePeriod

GREETING = (
    "Hi, I'm the intake assistant for the law firm. I'll ask about your service and the "
    "conditions you'd like help with. You can say \"I don't know\" to any question, and you can "
    "ask me questions along the way. I can't give legal advice, but an attorney will review "
    "everything you tell me."
)
CRISIS_MESSAGE = (
    "I'm really glad you told me. I'm stopping our questions so a person from our team can reach "
    "you. If you're in crisis or thinking about hurting yourself, please call the Veterans Crisis "
    "Line now: dial 988 and press 1, or text 838255. If you're in immediate danger, call 911."
)
HANDOFF_MESSAGE = "Of course. I'm passing your conversation to a person on our team, and they'll contact you shortly."
QUESTION_FOR_TEAM_NOTE = "Good question. I'll make sure someone from our team answers that."
CLOSINGS = {
    "eligible": "Thank you{name}, that's everything I need from you for now.",
    "not_veteran": "Thank you for reaching out. Our firm represents veterans with VA disability claims, so we aren't able to help with this one.",
    "rated_100": "Thank you{name}. Since you're already rated at 100%, there's no increase for us to pursue right now, but someone from our team will follow up if there's anything we can do.",
    "attorney_review": "Thank you{name}. One of our attorneys needs to review your service details before we go further. Someone from our team will contact you.",
    "incomplete": "Thank you{name}. We still need a few details, and someone from our team will follow up to finish.",
}
RECORDS_MODES = ("ask", "fetch", "fetch_confirm")
CFILE_MODES = ("off", "fetch", "confirm")  # off: the C-file is only for case prep, not for intake


class BrainError(RuntimeError):
    """The language model could not be reached or failed; the turn can simply be retried."""


@dataclass
class AgentConfig:
    records_mode: str = "fetch_confirm"
    cfile_mode: str = "confirm"  # use the C-file in pass 2: off | fetch (trust it) | confirm (ask about conflicts)
    verification_probes: bool = True  # in "ask" mode: ask the probes (second period, old claims)
    narrative: bool = True  # the per-condition narrative prompts after the structured questions
    secure_form: bool = True  # the POA skill's secure form collects name/contact: skip in chat
    max_clarifications: int = 2  # re-asks before a question is marked unknown
    open_ask_window: int = 12  # how many upcoming questions the brain may fill from one reply

    def __post_init__(self) -> None:
        if self.records_mode not in RECORDS_MODES:
            raise ValueError(f"records_mode must be one of {RECORDS_MODES}")
        if self.cfile_mode not in CFILE_MODES:
            raise ValueError(f"cfile_mode must be one of {CFILE_MODES}")


@dataclass
class QAResult:
    text: str
    sources: list[str] = field(default_factory=list)
    handoff: bool = False  # True: a person on the team should answer (legal advice, case-specific)
    usage: dict[str, Any] = field(default_factory=dict)  # tokens / cost of the call, if any (trace log)


QATool = Callable[[str], QAResult]


@dataclass
class TurnLog:
    ask_key: str | None
    kind: str  # question | clarify | extract | qa | closing | escalation | stage_complete
    extraction: dict[str, Any] = field(default_factory=dict)


@dataclass
class Turn:
    """What one controller step produced. `event` tells the orchestrator what happened."""

    text: str
    event: str | None = (
        None  # None (keep chatting) | stage_complete | stopped | escalated | complete
    )


class IntakeAgent:
    def __init__(
        self,
        brain: Brain,
        bank: QuestionBank | None = None,
        config: AgentConfig | None = None,
        qa: QATool | None = None,
    ) -> None:
        self.brain = brain
        self.bank = bank or QuestionBank.load()
        self.config = config or AgentConfig()
        self.qa = qa
        self.record = IntakeRecord()
        self.status: dict[
            str, str
        ] = {}  # ask key -> answered | volunteered | unknown | declined | auto | va_records | secure_form | skipped
        self.asked: Counter[str] = Counter()
        self.redundant_asks = 0  # asked although the field already held a value (should stay 0)
        self.transcript: list[dict[str, str]] = []
        self.log: list[TurnLog] = []
        self.pending: Ask | None = None
        self.stage: str | None = None
        self.done = False
        self.stopped: Outcome | None = None
        self.escalation: str | None = None
        self.records_service_text: str | None = None  # VA's service list, for the confirm probe
        self._greeted = False

    def mark_greeted(self) -> None:
        """The host already greeted the veteran: don't prefix the first question with GREETING."""
        self._greeted = True

    # ---------------------------------------------------------------- prefill

    def prefill_from_records(self, values: dict[str, Any], service_text: str | None) -> list[str]:
        """Answers from VA's records. Returns the question ids they settled (skipped in chat)."""
        if self.config.records_mode == "ask":
            return []
        self.records_service_text = service_text
        settled = []
        for q in self.bank.structured:
            if q.source != "va_records" or q.field not in values:
                continue
            value = values[q.field]
            if value is None:
                continue
            setattr(self.record, q.field, value)
            self.record.provenance[q.field] = "va_records"
            self.status[q.id] = "va_records"
            settled.append(q.id)
        if self.config.records_mode == "fetch":
            for q in self.bank.structured:  # trust the records: no verification probes
                if q.probe and q.confirms in values and values[q.confirms] is not None:
                    self.status.setdefault(q.id, "skipped")
        return settled

    def prefill_from_cfile(self, values: dict[str, Any]) -> list[str]:
        """Answers claims prep read from the C-file (questions marked `cfile: true`), before pass 2.
        Returns the question ids they settled. Never overwrites an answer already given."""
        if self.config.cfile_mode == "off":
            return []
        settled = []
        for q in self.bank.structured:
            if not q.cfile or q.id in self.status or values.get(q.field) in (None, [], ""):
                continue
            setattr(self.record, q.field, values[q.field])
            self.record.provenance[q.field] = "cfile"
            self.status[q.id] = "cfile"
            settled.append(q.id)
        return settled

    def note_cfile_discrepancies(self, texts: list[str]) -> None:
        """What the C-file contradicts. In cfile_mode confirm, pass 2 asks the veteran about it."""
        if self.config.cfile_mode == "confirm":
            self.record.cfile_discrepancies = list(texts)

    def prefill_secure_form(self, values: dict[str, str]) -> None:
        """Non-secret identity/contact fields from the POA skill's vault (host side only)."""
        for q in self.bank.structured:
            if q.source == "secure_form" and values.get(q.field):
                setattr(self.record, q.field, values[q.field])
                self.record.provenance[q.field] = "secure_form"
                self.status[q.id] = "secure_form"

    # ---------------------------------------------------------------- public API

    def start(self, stage: str) -> Turn:
        """Begin (or resume) a stage. Returns the first question, or stage_complete at once."""
        if self.done:
            raise RuntimeError("intake is over")
        self.stage = stage
        stop = rules.early_stop(self.record, self._answered_for_rules())
        if stop is not None:
            self.stopped = stop
            return self._close()
        nxt = self._next_ask()
        if nxt is None:
            return self._end_of_stage()
        prefix = "" if self._greeted else GREETING
        self._greeted = True
        return self._ask(nxt, kind="question", prefix=prefix)

    def reopen_for_new_condition(self) -> Turn:
        """After intake ended (pass 2 done), the orchestrator reopens it: ask which condition to
        add, then that condition's narrative prompts. Ends with `complete` like pass 2."""
        self.done = False
        self.stopped = None
        self.status.pop("add_condition", None)
        return self.start("reopen")

    def reply(self, text: str) -> Turn:
        if self.done:
            raise RuntimeError("intake is over")
        if self.pending is None:
            raise RuntimeError("no question is pending; call start() first")
        pending = self.pending

        # A deterministic safety check runs before (and regardless of) the brain.
        if detect_crisis(text):
            self.transcript.append({"role": "veteran", "text": text})
            return self._escalate("possible crisis or risk of self-harm", CRISIS_MESSAGE)
        if _WANTS_HUMAN.search(text):  # deterministic too: an LLM brain might miss the flag
            self.transcript.append({"role": "veteran", "text": text})
            return self._escalate("the veteran asked to speak with a person", HANDOFF_MESSAGE)

        try:
            ext = self.brain.extract(
                pending=pending,
                open_asks=self._open_asks(exclude=pending),
                transcript=self.transcript + [{"role": "veteran", "text": text}],
                user_text=text,
            )
        except Exception as exc:  # network, auth, rate limit: nothing changed, retry the turn
            raise BrainError(str(exc)) from exc
        self.transcript.append({"role": "veteran", "text": text})
        self.log.append(
            TurnLog(ask_key=pending.key, kind="extract", extraction=ext.__dict__.copy())
        )

        if ext.escalate:
            return self._escalate(
                ext.escalate_reason or "the assistant flagged a safety concern", CRISIS_MESSAGE
            )
        if ext.wants_human:
            return self._escalate("the veteran asked to speak with a person", HANDOFF_MESSAGE)

        note = self._answer_question(ext.veteran_question) if ext.veteran_question else ""

        self._apply(ext, pending)

        if pending.key not in self.status:
            if ext.pending_status == "declined":
                self.status[pending.key] = "declined"
            elif note and ext.pending_status == "not_addressed":
                # The reply was only a question: answer it and ask again, without counting a
                # clarification against the veteran.
                self.asked[pending.key] -= 1
                return self._ask(pending, kind="question", note=note)
            elif self.asked[pending.key] <= self.config.max_clarifications:
                return self._ask(pending, kind="clarify", note=ext.clarify_hint or note)
            else:
                self.status[pending.key] = "unknown"

        stop = rules.early_stop(self.record, self._answered_for_rules())
        if stop is not None:
            self.stopped = stop
            return self._close()

        nxt = self._next_ask()
        if nxt is None:
            return self._end_of_stage(note)
        if nxt.prompt is not None and nxt.condition != (
            pending.condition if pending.prompt else None
        ):
            transition = (
                f"Thank you. Now I'd like to understand your {nxt.condition} a little better."
            )
            note = f"{note} {transition}".strip()
        return self._ask(nxt, kind="question", note=note)

    def outcome(self) -> Outcome:
        return rules.final_outcome(self.record, self.stopped, self.escalation)

    # ---------------------------------------------------------------- memory (save / resume)

    def to_state(self) -> dict[str, Any]:
        """Everything needed to pick the conversation up again after a restart (JSON-safe).
        The brain, the question bank, the QA tool and the config are rebuilt by the host."""
        p = self.pending
        return {
            "record": self.record.model_dump(mode="json"),
            "status": dict(self.status),
            "asked": dict(self.asked),
            "redundant_asks": self.redundant_asks,
            "transcript": list(self.transcript),
            "log": [_jsonable(t.__dict__) for t in self.log],
            "pending": None if p is None else {
                "question": p.question.id if p.question else None,
                "prompt": p.prompt.id if p.prompt else None,
                "condition": p.condition,
                "records_text": p.records_text,
            },
            "stage": self.stage,
            "done": self.done,
            "stopped": self.stopped.model_dump(mode="json") if self.stopped else None,
            "escalation": self.escalation,
            "records_service_text": self.records_service_text,
            "greeted": self._greeted,
        }  # fmt: skip

    def load_state(self, state: dict[str, Any]) -> None:
        self.record = IntakeRecord.model_validate(state["record"])
        self.status = dict(state["status"])
        self.asked = Counter(state["asked"])
        self.redundant_asks = state["redundant_asks"]
        self.transcript = list(state["transcript"])
        self.log = [TurnLog(**t) for t in state["log"]]
        self.pending = self._ask_from_state(state["pending"])
        self.stage = state["stage"]
        self.done = state["done"]
        self.stopped = Outcome.model_validate(state["stopped"]) if state["stopped"] else None
        self.escalation = state["escalation"]
        self.records_service_text = state["records_service_text"]
        self._greeted = state["greeted"]

    def _ask_from_state(self, p: dict[str, Any] | None) -> Ask | None:
        if p is None:
            return None
        if p["question"] is not None:
            q = next((q for q in self.bank.structured if q.id == p["question"]), None)
            if q is None:
                raise ValueError(f"saved question {p['question']!r} is not in the question bank")
            return Ask(question=q, records_text=p["records_text"])
        prompt = next((n for n in self.bank.narrative if n.id == p["prompt"]), None)
        if prompt is None:
            raise ValueError(f"saved narrative prompt {p['prompt']!r} is not in the question bank")
        return Ask(prompt=prompt, condition=p["condition"])

    # ---------------------------------------------------------------- QA

    def answer_question(self, question: str) -> str:
        """Answer (or route to the team) a question the veteran asked; returns the text to say."""
        return self._answer_question(question)

    def _answer_question(self, question: str) -> str:
        if self.qa is None:
            self.record.questions_for_team.append(question)
            return QUESTION_FOR_TEAM_NOTE
        try:
            result = self.qa(question)
        except Exception:  # QA is a convenience: never let it break the intake
            result = QAResult(text="", handoff=True)
        self.log.append(TurnLog(ask_key=None, kind="qa", extraction={"question": question}))
        if result.handoff or not result.text:
            self.record.questions_for_team.append(question)
            return QUESTION_FOR_TEAM_NOTE
        self.record.qa_log.append(
            {"question": question, "answer": result.text, "sources": result.sources}
        )
        source = f" (Source: {result.sources[0]})" if result.sources else ""
        return f"{result.text}{source}"

    # ---------------------------------------------------------------- question selection

    def _skipped(self, q) -> bool:
        if q.id == "cfile_discrepancy_check":
            return self.config.cfile_mode != "confirm"
        if q.probe and self.config.records_mode == "ask" and not self.config.verification_probes:
            return True
        if q.source == "secure_form" and self.config.secure_form:
            return True
        return False

    def _ask_for(self, q) -> Ask:
        if q.id == "cfile_discrepancy_check":
            return Ask(question=q, records_text="; ".join(self.record.cfile_discrepancies))
        if q.ask_with_records and self.records_service_text is not None:
            if self.config.records_mode == "fetch_confirm":
                return Ask(question=q, records_text=self.records_service_text)
        return Ask(question=q)

    def _structured_candidates(self) -> list[Ask]:
        out = []
        for q in self.bank.structured:
            # Pass 2 also closes pass-1 gaps that became relevant (e.g. the C-file shows a claim).
            in_stage = q.stage == self.stage or (self.stage == "post_poa" and q.stage == "screen")
            if not in_stage or q.id in self.status or self._skipped(q):
                continue
            if not is_visible(q, self.record):
                continue
            out.append(self._ask_for(q))
        return out

    def _narrative_candidates(self) -> list[Ask]:
        if not self.config.narrative or self.stage not in ("post_poa", "reopen"):
            return []
        out = []
        for condition in self.record.claim_conditions:
            for prompt in self.bank.narrative:
                ask = Ask(prompt=prompt, condition=condition)
                if not prompt.auto and ask.key not in self.status:
                    out.append(ask)
        return out

    def _next_ask(self) -> Ask | None:
        candidates = self._structured_candidates() or self._narrative_candidates()
        return candidates[0] if candidates else None

    def _open_asks(self, exclude: Ask) -> list[Ask]:
        """Upcoming questions the brain may fill from one reply (so nothing is asked twice)."""
        upcoming = [
            a
            for a in self._structured_candidates() + self._narrative_candidates()
            if a.key != exclude.key
        ]
        return upcoming[: self.config.open_ask_window]

    def _answered_for_rules(self) -> set[str]:
        answered = set(self.status)
        if self.config.records_mode == "ask" and not self.config.verification_probes:
            answered |= {q.id for q in self.bank.structured if q.probe}
        return answered

    # ---------------------------------------------------------------- applying answers

    def _lookup(self, key: str, pending: Ask) -> Ask | None:
        if key == pending.key:
            return pending
        for ask in self._structured_candidates() + self._narrative_candidates():
            if ask.key == key:
                return ask
        return None

    def _apply(self, ext: Extraction, pending: Ask) -> None:
        for key, raw in ext.values.items():
            ask = self._lookup(key, pending)
            if ask is None or key in self.status:
                continue
            options = ask.question.options if ask.question else ()
            try:
                value = coerce(ask.type, raw, options)
            except (ValueError, TypeError):
                continue  # an unusable value counts as no answer; the controller re-asks
            self._store(ask, value)
            self.status[key] = "answered" if key == pending.key else "volunteered"

    def _store(self, ask: Ask, value: Any) -> None:
        if ask.prompt is not None:
            assert ask.condition is not None
            self.record.narratives.setdefault(ask.condition, {})[ask.prompt.id] = value
            return
        q = ask.question
        assert q is not None
        if q.type == "service_periods_append":
            existing = {_period_key(p) for p in self.record.service_periods}
            new: list[ServicePeriod] = [p for p in value if _period_key(p) not in existing]
            self.record.service_periods.extend(new)
            if new:
                self.record.provenance[q.field] = "chat+" + self.record.provenance.get(
                    q.field, "chat"
                )
            return
        if q.id == "add_condition":  # added to the claim, not a replacement for it
            value = self.record.claim_conditions + [c for c in value if c not in self.record.claim_conditions]
        setattr(self.record, q.field, value)
        self.record.provenance[q.field] = "chat"
        if q.field == "claim_conditions":
            for condition in value:
                for prompt in self.bank.narrative:
                    if prompt.auto:
                        self.record.narratives.setdefault(condition, {})[prompt.id] = condition
                        self.status[Ask(prompt=prompt, condition=condition).key] = "auto"

    # ---------------------------------------------------------------- speaking

    def _ask(self, ask: Ask, *, kind: str, note: str = "", prefix: str = "") -> Turn:
        if kind == "question" and ask.question is not None:
            if getattr(self.record, ask.question.field) not in (None, [], ""):
                appends = ask.question.type == "service_periods_append" or ask.question.id == "add_condition"
                if not appends and not ask.question.probe:
                    self.redundant_asks += 1
        self.asked[ask.key] += 1
        self.pending = ask
        try:
            text = self.brain.phrase(ask=ask, kind=kind, transcript=self.transcript, note=note)
        except Exception:  # the model is unreachable: the question bank's wording is always safe
            text = OfflineBrain().phrase(ask=ask, kind=kind, transcript=self.transcript, note=note)
        if prefix:
            text = f"{prefix}\n\n{text}"
        self.transcript.append({"role": "agent", "text": text, "ask": ask.key})
        self.log.append(TurnLog(ask_key=ask.key, kind=kind))
        return Turn(text)

    def _end_of_stage(self, note: str = "") -> Turn:
        self.pending = None
        if self.stage in ("post_poa", "reopen"):
            self._write_summaries()
            return self._close(note, event="complete")
        if self.stage == "screen" and self.record.is_veteran is not True:
            # Unknown or declined veteran status: never move on to signing the POA.
            self.stopped = Outcome(decision="incomplete", reasons=["veteran status not confirmed in screening"])
            return self._close(note)
        self.log.append(TurnLog(ask_key=None, kind="stage_complete"))
        text = note or ""
        if text:
            self.transcript.append({"role": "agent", "text": text})
        return Turn(text, event="stage_complete")

    def _close(self, note: str = "", event: str = "stopped") -> Turn:
        self.done = True
        self.pending = None
        decision = self.outcome().decision
        name = f", {self.record.first_name}" if self.record.first_name else ""
        text = CLOSINGS.get(decision, CLOSINGS["incomplete"]).format(name=name)
        if note:
            text = f"{note} {text}"
        self.transcript.append({"role": "agent", "text": text})
        self.log.append(TurnLog(ask_key=None, kind="closing"))
        return Turn(text, event=event)

    def _escalate(self, reason: str, message: str) -> Turn:
        self.escalation = reason
        self.done = True
        self.pending = None
        self.transcript.append({"role": "agent", "text": message})
        self.log.append(TurnLog(ask_key=None, kind="escalation"))
        return Turn(message, event="escalated")

    def _write_summaries(self) -> None:
        prompts = {p.id: p for p in self.bank.narrative}
        for condition, answers in self.record.narratives.items():
            qa = [
                (prompts[pid].ask.format(condition=condition), text)
                for pid, text in sorted(answers.items())
                if not prompts[pid].auto
            ]
            if not qa:
                continue
            try:
                self.record.narrative_summaries[condition] = self.brain.summarize(
                    condition=condition, qa=qa
                )
            except Exception:
                self.record.narrative_summaries[condition] = (
                    "(summary not generated: the model was unavailable; see the answers)"
                )


def _jsonable(value: Any) -> Any:
    """A JSON round-trip, so model objects inside a turn log (e.g. ServicePeriod) become plain data."""
    import json

    def default(o: Any) -> Any:
        if hasattr(o, "model_dump"):
            return o.model_dump(mode="json")
        return str(o)

    return json.loads(json.dumps(value, default=default))


def _period_key(p: ServicePeriod) -> tuple:
    return (p.branch, p.component, p.start, p.end)
