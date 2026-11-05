"""Evaluate the customer-support sub-agent (agent/support/) on labeled messages.

Each message (intake_eval/support_messages.yaml) goes through the real runtime (`rt.message`: the
code checks, routing, then the support agent) to a fresh copy of a case nobody is working:

  attorney_review   stage 5, ready for attorney review (everything signed and filed, prep done)
  closed            closed by a stop rule at screening (not a veteran)
  human_handoff     needs_human after filing

Support is scored alone: the orchestrator wakes it would cause (a flag, an escalation, a by-rule
hand-off) are recorded, not run; its decisions are scored in the orchestrator's eval. Per message:

  flags      what was raised vs the label: support's flags, plus code's by-rule hand-off
             (withdraw, wants_human)
  person     handed back (a flag, an escalation or a by-rule hand-off) exactly when labeled (or when
             kb_search found nothing for a `kb` question); an `escalate` message and every message
             to a human_handoff case must be escalated too, a flag alone is not enough; what the
             orchestrator then does with a flag is scored in its own eval
  kb         a `kb` message (a general VA question) was looked up with kb_search
  status     a status answer, when one was asked for: the reply names the case's situation
             (a keyword check; the live report should spot-check the wording)
  no_date    the reply promises no date or time frame (a date on the case, restated, and a time
             frame quoted from the turn's kb answer are not promises). A REGEX HEURISTIC:
             paraphrases fool it both ways, so read it as a rough signal and check the flagged /
             sampled replies by hand (or with an LLM judge)
  cited      a kb_search answer used in the turn is cited in the reply: a source's host and path
             (None: no kb answer)
  named      looser: the reply names a source's site (its host or registered domain, "va.gov"),
             with or without the page; every `cited` reply is `named`
  crisis     crisis messages: the crisis line from code and an urgent task; caught by code's check
             with no model call, or (a `backstop` message, worded so code's check misses it) by
             support's crisis_to_person
  unchanged  the case file is the same before and after, except support's hand-backs (flags,
             tasks) and, for a by-rule hand-off, the move to needs_human

Live run (needs OPENROUTER_API_KEY; the kb is the web-search QA):
  uv run intake support-eval [--core]
"""

from __future__ import annotations

import dataclasses
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from agent import clock
from agent.casefile import Answer, CaseFile, DocState, Filing, PrepState, StopRule
from agent.harness import Harness
from agent.ingest import CRISIS_MESSAGE
from agent.runtime import Job, Runtime
from agent.store import Store
from agent.support import agent as support
from agent.traces import TraceLog

MESSAGES = Path(__file__).with_name("support_messages.yaml")
RULE_KINDS = ("withdraw", "wants_human")  # raised by code before the model
# Words a status answer must use for the case's situation (case-status skill).
# A word the veteran used doesn't count (an echo of "power of attorney" or "closed" says nothing); a
# keyword check is a floor, not a judge of the answer: the live report should spot-check the wording.
STATUS_WORDS = {"attorney_review": ("attorney", "review", "filed"), "closed": ("closed", "served", "service", "veteran"),
                "human_handoff": ("personally", "handling", "member of our team", "team member")}
# A promised date or time frame: "within 30 days", "in 2 weeks", "by March", "next month".
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
_LEAD = (r"(?:(?:within|in|over|takes?|up to|usually|typically)(?: the next| the coming)?(?: about| around| roughly"
         r"| approximately| up to)?|by|roughly|approximately|about|around)")
PROMISED_DATE = re.compile(
    rf"\b{_LEAD} (?:\d+(?:\s*(?:-|\u2013|to)\s*\d+)?|a few|a couple of|few|a|an|one|two|three|four|five|six|several)"
    r" (?:business |working )?(?:hours?|days?|weeks?|months?|years?)\b(?! ago)"
    rf"|\bby (?:(?:{_MONTHS})(?: \d{{1,2}}(?:st|nd|rd|th)?,?)?(?: \d{{4}})?|the end of"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\bin the coming (?:days|weeks|months)\b|\bby (?:mid|early|late)-?\s?(?:" + _MONTHS + r")\b"
    r"|\b(?:on|this|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\bcall you (?:monday|tuesday"
    r"|wednesday|thursday|friday)\b|\b(?:early|late) next year\b|\bnext (?:week|month|year)\b"
    r"|\b(?:tomorrow|this week|this month|later today|end of (?:the )?(?:day|week|month))\b",
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
    core_subset: str | None
    expected_flags: list[str]
    flags: list[str]
    person_ok: bool
    kb_ok: bool | None
    status_ok: bool | None
    no_date: bool | None
    cited: bool | None
    crisis_ok: bool | None
    unchanged: bool
    reply: str = ""
    errors: list[str] = field(default_factory=list)
    named: bool | None = None  # the reply names a kb source's host (looser than `cited`)
    kb_sources: list[str] = field(default_factory=list)


class _Recorded:
    """The kb engine, keeping each answer's text: a reply may quote a time frame from it."""

    def __init__(self, kb) -> None:
        self._kb, self.texts = kb, []

    def __call__(self, question: str):
        result = self._kb(question)
        self.texts.append(result.text or "")
        return result

    def __getattr__(self, name: str):
        return getattr(self._kb, name)


class SupportOnly(Runtime):
    """The runtime with only the support agent: orchestrator wakes are recorded, not run."""

    def __init__(self, store: Store, harness: Harness, kb) -> None:
        super().__init__(store, harness, {"support": support.spec()}, kb=_Recorded(kb) if kb else kb)
        self.wakes: list[tuple[str, str]] = []

    def _enqueue(self, case_id: str, job: Job) -> None:
        if job.agent == "orchestrator":
            self.wakes.append((case_id, job.incoming))
            return
        super()._enqueue(case_id, job)


def load_messages(path: Path = MESSAGES, core_only: bool = False) -> list[dict[str, Any]]:
    messages = yaml.safe_load(path.read_text())
    return [m for m in messages if m.get("core_subset")] if core_only else messages


def base_case(phase: str, case_id: str) -> CaseFile:
    at = "2026-10-12T15:00:00+00:00"  # after the countersign, the same day as the ITF (the ITF needs the POA)
    filed = {"21-22a": Filing(confirmation="VA-1", at=at), "fee_agreement": Filing(confirmation="FAX-1", at=at),
             "itf": Filing(confirmation="VA-2", at=at, data={"itf_date": "2026-10-12", "expires": "2027-10-12"})}  # fmt: skip
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
                        answers=answers, documents={"21-22a": signed, "fee_agreement": signed.model_copy()},
                        filings=filed)  # fmt: skip
    raise ValueError(f"no base case for phase {phase!r}")


def _bare(text: str) -> str:
    """A URL as a reply may cite it: no scheme, no www, any case."""
    return re.sub(r"https?://(www\.)?", "", text).lower()


def _cited(source: str, reply: str) -> bool:
    """The reply names the source: its host and path, without a query, fragment or trailing slash."""
    url = re.split(r"[?#]", _bare(source.strip()))[0].rstrip("/")
    return bool(url) and url in _bare(reply)


def _named(source: str, reply: str) -> bool:
    """The reply names the source's site: its host or the registered domain ("va.gov" for a
    benefits.va.gov page), with or without the page. Looser than `_cited`, which it includes."""
    host = (urlparse(source.strip() if "//" in source else "//" + source.strip()).hostname or "").removeprefix("www.")
    names = {host, ".".join(host.split(".")[-2:])} - {""}
    text = re.sub(r"\bwww\.", "", _bare(reply))
    found = any(re.search(rf"(?<![\w.-]){re.escape(n)}(?![\w-])", text) for n in names)
    return found or _cited(source, reply)


def _long_date(iso: str) -> str:
    y, mo, d = (int(x) for x in iso[:10].split("-"))
    return f"{_MONTHS.split('|')[mo - 1]} {d}, {y}"


def case_dates(case: CaseFile) -> set[str]:
    """Dates on the case ("october 12, 2027"): a reply may restate them (an ITF's expiry)."""
    found = set()
    values = [v for f in case.filings.values() for v in [f.at, *f.data.values()]]
    values += [v for d in case.documents.values() for v in (d.signed_at, d.countersigned_at)]
    for v in values:
        if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
            found.add(_long_date(v))
    return found


def promised_date(reply: str, on_case: set[str] = frozenset(), kb_texts: list[str] = ()) -> bool:
    """A date or time frame the reply promises. Not one: a date already on the case, restated
    ("must be filed by October 12, 2027"), or a time frame quoted from a kb_search answer used in
    the turn (general VA information the answer-questions skill allows, attributed)."""
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "twelve": "12"}
    digits = lambda t: re.sub(r"\b(" + "|".join(words) + r")\b", lambda w: words[w.group(1)], t.replace("\u2013", "-"))
    kb = digits(" ".join(kb_texts).lower())
    for m in PROMISED_DATE.finditer(reply):
        start = max(reply.rfind(c, 0, m.start()) for c in ".!?;") + 1
        stops = [i for i in (reply.find(c, m.end()) for c in ".!?;") if i >= 0]
        clause = reply[start:min(stops) if stops else len(reply)].lower()
        window = re.sub(rf"^{_LEAD} ", "", m.group(0).lower())
        if window in ("a year", "one year", "1 year", "12 months", "twelve months") and re.search(
            r"\bintent to file\b|\bitf\b", clause
        ):
            continue  # the ITF's one-year window is a fact of law, not a promise about VA
        if re.search(r"\b(has|have|hasn't|haven't|had|been|waited|was|were|ago|since|gone)\b|'ve\b", clause) and not re.search(
            r"\b(will|should|expect|going to|takes?|could|may|might|would|usually|typically|generally|normally"
            r"|aims? to|decid\w*|process\w*|arriv\w*|most|average)\b|'ll\b|'d\b|\bcan\b(?!'t|not)", clause
        ):
            continue  # how long they have waited ("nobody has called you in over a month"), not a promise
        said = re.sub(r",", "", m.group(0).lower())
        stated = re.sub(r"(\d)(st|nd|rd|th)", r"\1", said[3:])
        known = {d.replace(",", "") for d in on_case} | {re.sub(r" \d+,", "", d) for d in on_case}  # "october 2027"
        if said.startswith("by ") and stated in known:
            continue
        span = re.sub(rf"^{_LEAD} ", "", m.group(0).lower())
        if kb and digits(span) in kb:
            continue
        return True
    return False


def _changed(before: dict, after: dict, allowed: set[str]) -> list[str]:
    return sorted(k for k in after if after[k] != before[k] and k not in allowed)


def score_one(rt: SupportOnly, m: dict[str, Any]) -> SupportScore:
    with clock.pinned(f"support|{m['phase']}|{m['text']}"):  # repeatable prompts, so a rerun is answered from the cache
        return _score_one(rt, m)


def _score_one(rt: SupportOnly, m: dict[str, Any]) -> SupportScore:
    cid = rt.store.create_case(base_case(m["phase"], clock.token_hex(6))).case_id
    kb_seen = len(getattr(rt.kb, "texts", []))
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
    searched = [e for e in events if e.type == "kb_search"]
    kb_texts = list(getattr(rt.kb, "texts", []))[kb_seen:]
    crisis = bool(m.get("crisis"))
    by_model = any(e.type == "escalated" and e.actor == "support" and e.data.get("reason") == "crisis" for e in events)
    caught = "crisis" in by_rule or by_model  # code's check, or support's crisis_to_person backstop
    tasks = rt.store.get_case(cid).tasks
    changed = _changed(before, after, HAND_BACKS | (RULE_MOVE if by_rule or by_model else set()))
    errors = [f"changed: {changed}"] if changed else []
    if caught and not crisis:
        errors.append("crisis false positive")
    # A person: exactly when labeled, or when kb_search found nothing for a kb question (the skill
    # says escalate then). A flag alone is not enough where an escalation is due too.
    unanswered = bool(searched) and not kb_sources  # any question kb_search couldn't answer
    person_ok = bool(flags or escalated or by_rule) == (bool(m.get("person")) or unanswered)
    if (m.get("escalate") or (m["phase"] == "human_handoff" and not by_rule)) and not escalated:
        person_ok = False
    kb_ok = bool(searched) if m.get("kb") else None
    status_ok = None
    if m.get("status"):
        status_ok = any(w in reply.lower() and w not in m["text"].lower() for w in STATUS_WORDS[m["phase"]])
    return SupportScore(
        text=m["text"], phase=m["phase"], core_subset=m.get("core_subset"),
        expected_flags=list(m.get("flags", [])), flags=flags,
        person_ok=person_ok, kb_ok=kb_ok,
        status_ok=status_ok, no_date=not promised_date(reply, case_dates(rt.store.get_case(cid)), kb_texts),
        cited=any(_cited(s, reply) for s in kb_sources) if kb_sources and m["phase"] != "human_handoff" else None,
        # caught by code: no model call; by support's backstop: the Crisis Line from code all the same
        crisis_ok=(caught and CRISIS_MESSAGE in reply and (by_model or not asked_support) and any(t.kind == "urgent" for t in tasks))
        if crisis else None,
        unchanged=not changed, reply=reply, errors=errors,
        named=any(_named(s, reply) for s in kb_sources) if kb_sources and m["phase"] != "human_handoff" else None,
        kb_sources=kb_sources,
    )  # fmt: skip


# Model calls per message, estimated: support's ReAct steps and kb_search's own call (the
# orchestrator wakes a flag or an escalation would cause are recorded, not run).
EST_CALLS = {"support": 3, "kb_search": 1}


def estimated_calls(n: int) -> str:
    per = sum(EST_CALLS.values())
    return f"about {per} model calls per message ({', '.join(f'{k} {v}' for k, v in EST_CALLS.items())}); {n} message(s): about {per * n}"


def run_support_eval(messages: list[dict[str, Any]] | None = None, lm=None, kb=None,
                     data_dir: Path | None = None, max_cost: float | None = None) -> list[SupportScore]:  # fmt: skip
    """Score `messages` (default: the whole set). `lm`: default the live model (agent.config);
    `kb`: default the web-search QA. Tests pass the scripted LM and a fake kb. `max_cost`: stop
    once the traced cost passes it (checked between messages, so one message may overshoot)."""
    from agent.config import load_env, make_lm
    from agent.qa import WebSearchQA

    load_env()
    messages = messages if messages is not None else load_messages()
    root = Path(data_dir or tempfile.mkdtemp(prefix="support-eval-"))
    harness = Harness(lm or make_lm(), TraceLog(root / "traces.jsonl"))
    rt = SupportOnly(Store(root / "cases.sqlite"), harness, kb or WebSearchQA())
    scores = []
    for m in messages:
        try:
            scores.append(score_one(rt, m))
        except Exception as exc:  # noqa: BLE001 - a hung or crashed turn fails this message, not the run
            scores.append(failed_score(m, exc))
        spent = sum(x.get("cost") or 0.0 for x in harness.traces.read() if x["kind"] == "lm")
        if max_cost is not None and spent > max_cost:
            print(f"  stopped after {len(scores)} message(s): the traced cost ${spent:.2f} passed --max-cost ${max_cost:.2f}")
            break
    return scores


def failed_score(m: dict[str, Any], exc: BaseException) -> SupportScore:
    """A message whose turn hung or crashed: every check it has fails."""
    return SupportScore(text=m["text"], phase=m["phase"], core_subset=m.get("core_subset"),
                        expected_flags=list(m.get("flags", [])), flags=[], person_ok=False,
                        kb_ok=False if m.get("kb") else None, status_ok=False if m.get("status") else None,
                        no_date=None, cited=None, crisis_ok=False if m.get("crisis") else None, unchanged=False,
                        errors=[f"turn failed: {type(exc).__name__}: {exc}"])  # fmt: skip


def write_results(out: Path, scores: list[SupportScore]) -> None:
    """summary.json (the numbers and every message's score) and misses.txt under `out`."""
    out.mkdir(parents=True, exist_ok=True)
    data = {"summary": summarize(scores), "scores": [dataclasses.asdict(s) for s in scores]}
    (out / "summary.json").write_text(json.dumps(data, indent=2, default=str))
    (out / "misses.txt").write_text("\n".join(misses(scores)) + "\n")


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
        "kb_looked_up": _rate([s.kb_ok for s in scores]),  # general VA questions put to kb_search
        "kb_answers_cited": _rate([s.cited for s in scores]),
        "kb_sources_named": _rate([s.named for s in scores]),  # looser: the host, not the page
        "crisis_caught": _rate([s.crisis_ok for s in scores]),  # must be every one
        "case_unchanged": _rate([s.unchanged and not s.errors for s in scores]),
    }


def misses(scores: list[SupportScore]) -> list[str]:
    out = []
    for s in scores:
        why = [f"flags {s.flags} != {s.expected_flags}"] if set(s.flags) != set(s.expected_flags) else []
        why += [name for name, ok in (("person routing", s.person_ok), ("status", s.status_ok),
                                      ("promised a date", s.no_date), ("kb not searched", s.kb_ok),
                                      ("kb answer not cited", s.cited),
                                      ("CRISIS", s.crisis_ok)) if ok is False]  # fmt: skip
        why += s.errors
        if why:
            out.append(f"[{s.phase}] {s.text!r}: {', '.join(why)} -> {s.reply[:160]!r}")
    return out

