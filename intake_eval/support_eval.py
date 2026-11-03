"""Evaluate the customer-support sub-agent (agent/support/) on labeled messages (L32).

Each message (intake_eval/support_messages.yaml) goes through the real runtime (`rt.message`: the
code checks, D1 routing, then the support agent) to a fresh copy of a case nobody is working:

  attorney_review   stage 5, ready for attorney review (everything signed and filed, prep done)
  closed            closed by a stop rule at screening (not a veteran)
  human_handoff     needs_human after filing

Support is scored alone: the orchestrator wakes it would cause (a flag, an escalation, a by-rule
hand-off) are recorded, not run; its decisions are scored in the orchestrator's eval. Per message:

  flags      what was raised vs the label: support's flags, plus code's by-rule hand-off
             (withdraw, wants_human)
  person     handed back (a flag, an escalation or a by-rule hand-off) exactly when labeled; what
             the orchestrator then does with a flag is scored in its own eval
  status     a status answer, when one was asked for: the reply names the case's situation
             (a keyword check; the live report should spot-check the wording)
  no_date    the reply promises no date or time frame
  cited      a kb_search answer used in the turn is cited in the reply (None: no kb answer)
  crisis     crisis messages: the crisis line from code, an urgent task, and no model call
  unchanged  the case file is the same before and after, except support's hand-backs (flags,
             tasks) and, for a by-rule hand-off, the move to needs_human

Live run (needs OPENROUTER_API_KEY; the kb is the web-search QA):
  uv run intake support-eval [--luke]
"""

from __future__ import annotations

import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent.casefile import Answer, CaseFile, DocState, Filing, PrepState, StopRule
from agent.harness import Harness
from agent.ingest import CRISIS_MESSAGE
from agent.runtime import Job, Runtime
from agent.store import Store
from agent.support import agent as support
from agent.traces import TraceLog

MESSAGES = Path(__file__).with_name("support_messages.yaml")
RULE_KINDS = ("withdraw", "wants_human")  # raised by code before the model (D2)
# Words a status answer must use for the case's situation (case-status skill).
STATUS_WORDS = {"attorney_review": ("attorney",), "closed": ("closed",), "human_handoff": ("personally", "handling")}
# A promised date or time frame: "within 30 days", "in 2 weeks", "by March", "next month".
PROMISED_DATE = re.compile(
    r"\b(within|in(?: about| around)?|by|over the next) (\d+|a few|a couple of|one|two|three|several) "
    r"(days?|weeks?|months?)\b|\bby (january|february|march|april|may|june|july|august|september|october"
    r"|november|december|the end of)\b|\bnext (week|month)\b",
    re.IGNORECASE,
)
# What a by-rule hand-off or support's hand-backs may change; everything else must stay as it was.
HAND_BACKS = {"flags", "tasks"}
RULE_MOVE = {"side_state", "side_reason", "owner", "goal", "awaiting_veteran"}
VETERAN = "veteran, chat 10:00 UTC"


@dataclass
class SupportScore:
    text: str
    phase: str
    luke_subset: str | None
    expected_flags: list[str]
    flags: list[str]
    person_ok: bool
    status_ok: bool | None
    no_date: bool
    cited: bool | None
    crisis_ok: bool | None
    unchanged: bool
    reply: str = ""
    errors: list[str] = field(default_factory=list)


class SupportOnly(Runtime):
    """The runtime with only the support agent: orchestrator wakes are recorded, not run."""

    def __init__(self, store: Store, harness: Harness, kb) -> None:
        super().__init__(store, harness, {"support": support.spec()}, kb=kb)
        self.wakes: list[tuple[str, str]] = []

    def _enqueue(self, case_id: str, job: Job) -> None:
        if job.agent == "orchestrator":
            self.wakes.append((case_id, job.incoming))
            return
        super()._enqueue(case_id, job)


def load_messages(path: Path = MESSAGES, luke_only: bool = False) -> list[dict[str, Any]]:
    messages = yaml.safe_load(path.read_text())
    return [m for m in messages if m.get("luke_subset")] if luke_only else messages


def base_case(phase: str, case_id: str) -> CaseFile:
    filed = {"21-22a": Filing(confirmation="VA-1"), "fee_agreement": Filing(confirmation="FAX-1"),
             "itf": Filing(confirmation="VA-2", data={"itf_date": "2026-10-12", "expires": "2027-10-12"})}  # fmt: skip
    signed = DocState(signed_at="2026-10-10T15:00:00+00:00", countersigned_at="2026-10-11T15:00:00+00:00")
    answers = {k: Answer(value=False, source=VETERAN) for k in ("prior_attorney", "filed_before")}
    if phase == "attorney_review":
        return CaseFile(case_id=case_id, stage=5, answers=answers, checklist={"screen": [], "pass2": []},
                        documents={"21-22a": signed, "fee_agreement": signed.model_copy()}, filings=filed,
                        prep=PrepState(pulled=True, face_note="(face note)", verified=True, prefill_done=True))  # fmt: skip
    if phase == "closed":
        stop = StopRule(rule="not_veteran", reason="never served in the military")
        return CaseFile(case_id=case_id, stage=1, stop=stop, side_state="closed", side_reason=stop.reason,
                        answers={"is_veteran": Answer(value=False, source=VETERAN)})  # fmt: skip
    if phase == "human_handoff":
        return CaseFile(case_id=case_id, stage=3, side_state="needs_human", side_reason="attorney asked to review",
                        answers=answers, documents={"21-22a": signed}, filings=filed)  # fmt: skip
    raise ValueError(f"no base case for phase {phase!r}")


def _bare(text: str) -> str:
    """A URL as a reply may cite it: no scheme, no www."""
    return re.sub(r"https?://(www\.)?", "", text)


def _changed(before: dict, after: dict, allowed: set[str]) -> list[str]:
    return sorted(k for k in after if after[k] != before[k] and k not in allowed)


def score_one(rt: SupportOnly, m: dict[str, Any]) -> SupportScore:
    cid = rt.store.create_case(base_case(m["phase"], uuid.uuid4().hex[:12])).case_id
    before = rt.store.get_case(cid).model_dump(mode="json")
    rt.message(cid, m["text"])
    rt.wait_until_idle(cid, timeout=180)
    after = rt.store.get_case(cid).model_dump(mode="json")
    events = rt.store.events(cid)
    reply = " ".join(o.payload["text"] for o in rt.updates(cid) if o.kind == "message")
    by_rule = [e.data["reason"] for e in events if e.type == "escalated" and e.actor == "rule"]
    flags = [e.data["kind"] for e in events if e.type == "support_flag"] + [r for r in by_rule if r in RULE_KINDS]
    escalated = any(e.type == "escalated" and e.actor == "support" for e in events)
    asked_support = any(e.type == "message" and e.data.get("to") == "support" for e in events)
    kb_sources = [s for e in events if e.type == "kb_search" and e.data["answered"] for s in e.data["sources"]]
    crisis = bool(m.get("crisis"))
    caught = "crisis" in by_rule
    tasks = rt.store.get_case(cid).tasks
    changed = _changed(before, after, HAND_BACKS | (RULE_MOVE if by_rule else set()))
    errors = [f"changed: {changed}"] if changed else []
    if caught and not crisis:
        errors.append("crisis false positive")
    status_ok = None
    if m.get("status"):
        status_ok = any(w in reply.lower() for w in STATUS_WORDS[m["phase"]])
    return SupportScore(
        text=m["text"], phase=m["phase"], luke_subset=m.get("luke_subset"),
        expected_flags=list(m.get("flags", [])), flags=flags,
        person_ok=bool(flags or escalated or by_rule) == bool(m.get("person")),
        status_ok=status_ok, no_date=not PROMISED_DATE.search(reply),
        cited=any(_bare(s) in _bare(reply) for s in kb_sources) if kb_sources else None,
        crisis_ok=(caught and CRISIS_MESSAGE in reply and not asked_support and tasks[-1].kind == "urgent")
        if crisis else None,
        unchanged=not changed, reply=reply, errors=errors,
    )  # fmt: skip


def run_support_eval(messages: list[dict[str, Any]] | None = None, lm=None, kb=None,
                     data_dir: Path | None = None) -> list[SupportScore]:  # fmt: skip
    """Score `messages` (default: the whole set). `lm`: default the live model (agent.config);
    `kb`: default the web-search QA. Tests pass the scripted LM and a fake kb."""
    from agent.config import load_env, make_lm
    from agent.qa import WebSearchQA

    load_env()
    messages = messages if messages is not None else load_messages()
    root = Path(data_dir or tempfile.mkdtemp(prefix="support-eval-"))
    harness = Harness(lm or make_lm(), TraceLog(root / "traces.jsonl"))
    rt = SupportOnly(Store(root / "cases.sqlite"), harness, kb or WebSearchQA())
    return [score_one(rt, m) for m in messages]


def _rate(values: list[bool | None]) -> str:
    scored = [v for v in values if v is not None]
    return f"{sum(scored)}/{len(scored)}"


def summarize(scores: list[SupportScore]) -> dict[str, Any]:
    tp = sum(len(set(s.flags) & set(s.expected_flags)) for s in scores)
    fp = sum(len(set(s.flags) - set(s.expected_flags)) for s in scores)
    fn = sum(len(set(s.expected_flags) - set(s.flags)) for s in scores)
    return {
        "messages": len(scores),
        "flag_precision": tp / (tp + fp) if tp + fp else 1.0,
        "flag_recall": tp / (tp + fn) if tp + fn else 1.0,
        "person_routing": _rate([s.person_ok for s in scores]),
        "status_answers": _rate([s.status_ok for s in scores]),
        "no_promised_dates": _rate([s.no_date for s in scores]),
        "kb_answers_cited": _rate([s.cited for s in scores]),
        "crisis_caught": _rate([s.crisis_ok for s in scores]),  # must be every one
        "case_unchanged": _rate([s.unchanged and not s.errors for s in scores]),
    }


def misses(scores: list[SupportScore]) -> list[str]:
    out = []
    for s in scores:
        why = [f"flags {s.flags} != {s.expected_flags}"] if set(s.flags) != set(s.expected_flags) else []
        why += [name for name, ok in (("person routing", s.person_ok), ("status", s.status_ok),
                                      ("promised a date", s.no_date), ("kb answer not cited", s.cited),
                                      ("CRISIS", s.crisis_ok)) if ok is False]  # fmt: skip
        why += s.errors
        if why:
            out.append(f"[{s.phase}] {s.text!r}: {', '.join(why)} -> {s.reply[:160]!r}")
    return out

