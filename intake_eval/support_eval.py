"""Evaluate the customer-support subagent on labeled messages (intake_eval/support_messages.yaml).

Each message goes, through the real CaseSession, to a parked case: one case is run once per phase
(attorney_review, closed, human_handoff), saved, and every message gets a fresh copy of it, resumed
from disk (CaseSession.resume). Scored per message:

  flags       the flags support raised vs the label (precision / recall over all messages)
  status      a status answer when one was asked for
  person      a staff task created exactly when a person must read the message
  crisis      the crisis message plus a hand-off task (must be every one)
  unchanged   nothing in the case changed except tasks, events and decisions (support is read-only)
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent.intake.controller import CRISIS_MESSAGE
from agent.lighthouse import StubLighthouse
from agent.personas import get_persona
from agent.session import CaseSession
from agent.support import FLAG_KINDS, snapshot, status_text
from intake_eval.runner import run_case

MESSAGES = Path(__file__).with_name("support_messages.yaml")
BASE_CASES = {  # phase -> (persona, condition) that parks a case there
    "attorney_review": ("baseline_clean", "fetch_confirm"),
    "closed": ("not_a_veteran", "ask"),
    "human_handoff": ("oth_only_period", "fetch_confirm"),
}
# What support may change: the staff queue and the logs. Everything else must stay as it was.
# open_flags / escalation: how support hands things back to the orchestrator (escalation: by rule,
# for a withdrawal or a request for a person in a stage no person owns yet).
MAY_CHANGE = {"tasks", "events", "decisions", "subagents", "open_flags", "escalation", "awaiting_veteran"}
# A crisis is handled before support (in every phase): the session also records the escalation.
MAY_CHANGE_IN_CRISIS = MAY_CHANGE | {"escalation"}


@dataclass
class SupportScore:
    text: str
    phase: str
    expected_flags: list[str]
    flags: list[str]
    status_ok: bool
    person_ok: bool
    crisis_ok: bool | None
    unchanged: bool
    reply: str = ""
    errors: list[str] = field(default_factory=list)


def load_messages(path: Path = MESSAGES) -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text())


def _base_case(phase: str, root: Path) -> tuple[Path, str]:
    persona_id, condition = BASE_CASES[phase]
    folder = root / phase
    run = run_case(get_persona(persona_id), condition, data_dir=folder)
    if run.case.phase != phase:
        raise RuntimeError(f"base case for {phase} ended in {run.case.phase}")
    return folder, run.case.case_id


def run_support_eval(messages: list[dict[str, Any]] | None = None, provider: str = "offline") -> list[SupportScore]:
    messages = messages if messages is not None else load_messages()
    root = Path(tempfile.mkdtemp(prefix="support-eval-"))
    bases = {ph: _base_case(ph, root) for ph in {m["phase"] for m in messages}}
    scores = []
    for i, m in enumerate(messages):
        base, case_id = bases[m["phase"]]
        copy = root / f"msg{i}"
        shutil.copytree(base, copy)
        session = CaseSession.resume(case_id, data_dir=copy, lighthouse=StubLighthouse())
        # Score support alone: what it hands back, before the orchestrator acts on its flags
        # (reopening intake for a new condition is the orchestrator's decision, scored elsewhere).
        session.orchestrator.handle = lambda case, event: []
        if provider != session.provider:
            raise ValueError("the base cases are built offline; run with provider=offline")
        before = session.case.model_dump(mode="json")
        tasks_before = len(session.case.tasks)
        turn = session.message(m["text"])
        after = session.case.model_dump(mode="json")
        reply = " ".join(turn.messages)
        new_tasks = session.case.tasks[tasks_before:]
        support_events = [e for e in session.case.events if e.type == "support_message"]
        flags = support_events[-1].data.get("flags", []) if support_events else []
        expect_status = bool(m.get("status"))
        status = status_text(snapshot(session.case))
        crisis = m.get("crisis", False)
        changed = {k for k in after if after[k] != before[k]} - (MAY_CHANGE_IN_CRISIS if crisis else MAY_CHANGE)
        scores.append(SupportScore(
            text=m["text"], phase=m["phase"], expected_flags=list(m.get("flags", [])), flags=list(flags),
            status_ok=(status in reply) == expect_status,
            # a person will see it: a task now, a flag the orchestrator must route, or a hand-off
            person_ok=bool(new_tasks or session.case.open_flags or session.case.escalation) == bool(m.get("person")),
            crisis_ok=(CRISIS_MESSAGE in reply and any(t.kind == "handoff" for t in new_tasks)) if crisis else None,
            unchanged=not changed, reply=reply,
            errors=[f"changed: {sorted(changed)}"] if changed else [],
        ))  # fmt: skip
    shutil.rmtree(root, ignore_errors=True)
    return scores


def summarize(scores: list[SupportScore]) -> dict[str, Any]:
    tp = sum(len(set(s.flags) & set(s.expected_flags)) for s in scores)
    fp = sum(len(set(s.flags) - set(s.expected_flags)) for s in scores)
    fn = sum(len(set(s.expected_flags) - set(s.flags)) for s in scores)
    crisis = [s.crisis_ok for s in scores if s.crisis_ok is not None]
    n = len(scores)
    return {
        "messages": n,
        "flag_precision": tp / (tp + fp) if tp + fp else 1.0,
        "flag_recall": tp / (tp + fn) if tp + fn else 1.0,
        "status_accuracy": sum(s.status_ok for s in scores) / n if n else None,
        "person_routing_accuracy": sum(s.person_ok for s in scores) / n if n else None,
        "crisis_handled": f"{sum(crisis)}/{len(crisis)}",
        "case_unchanged": f"{sum(s.unchanged for s in scores)}/{n}",
        "flag_kinds": list(FLAG_KINDS),
    }


def misses(scores: list[SupportScore]) -> list[str]:
    out = []
    for s in scores:
        why = []
        if set(s.flags) != set(s.expected_flags):
            why.append(f"flags {s.flags} != {s.expected_flags}")
        if not s.status_ok:
            why.append("status")
        if not s.person_ok:
            why.append("person routing")
        if s.crisis_ok is False:
            why.append("CRISIS")
        why += s.errors
        if why:
            out.append(f"[{s.phase}] {s.text!r}: {', '.join(why)} -> {s.reply[:160]!r}")
    return out


if __name__ == "__main__":  # uv run python -m intake_eval.support_eval
    _scores = run_support_eval()
    for _k, _v in summarize(_scores).items():
        print(f"{_k:>24}: {_v}")
    _missed = misses(_scores)
    print(f"\n{len(_missed)} label-level misses" + (":" if _missed else ""))
    for _line in _missed:
        print("  " + _line)
