"""The customer-support sub-agent (L29-L30): answers the veteran when no owner is talking with them.

Code routes a message here (D1, agent/runtime.py) while claims prep reads the C-file, while the
case waits on VA or sits between stages, and once it is parked (needs_human, closed). Crisis
language, a request for a person and a request to end the representation never get here: code
hands them to a person first (D2, D3).

One ReAct turn per message. Context: the skill index (harness), a read-only snapshot of the case
(stage, what's done, deadlines, the fee, flags already passed on, earlier Q&A from the event
log), the last 8 messages of this conversation and the latest message.

Tools: read_skill (harness), kb_search, get_case, log_event, flag_orchestrator, escalate. The
reply output is the only channel to the veteran. Support is read-only by construction: no tool
moves a stage, files, signs or edits the case file. Its only writes are an event line
(log_event), a flag for the orchestrator (rt.flag: held while claims prep runs, §3) and a staff
task (rt.escalate).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from agent.casefile import STAGE_NAMES, CaseFile
from agent.harness import AgentSpec, Turn, conversation
from agent.ingest import redact_chat
from agent.intake.agent import fee_line
from agent.kb import kb_tool
from agent.tools.registry import NoArgs, ToolSpec

HISTORY = 8
EARLIER_QA = 8  # support_log and kb_search lines in the snapshot
FlagKind = Literal["new_condition", "contact_change", "complaint"]

INSTRUCTIONS = """You are customer support for a law firm that represents veterans before VA. You \
answer one veteran in a web chat while nobody else on the case is talking with them: our team may be \
reading their VA claims file, the case may be waiting on VA, or a person may already be handling it. \
Your context holds a read-only snapshot of the case and the recent messages.

You can read the case but never change it. You have no tool that files, signs or moves the case, and \
you never say you did any of those.
- Where the case stands, what happens next: answer from the snapshot in plain words (read `case-status`).
- General questions about VA process, forms or fees: kb_search, then answer only from what it \
returns and name its source (read `answer-questions`).
- Never give legal advice, predict a rating or an outcome, or promise a date or a time frame for \
anything VA does.
- Anything that would change the case goes to the orchestrator with flag_orchestrator: a new or \
worsened condition (new_condition), a new address, phone or email (contact_change), a complaint \
about us or the service (complaint). Tell the veteran you passed it on; don't promise what happens next.
- Anything you can't answer from the snapshot or kb_search: escalate, and tell the veteran a person \
on our team will follow up (read `hand-to-a-person`).
- Before you finish, write one log_event line: what was asked and what you answered or did."""


# ------------------------------------------------------------------------------ the snapshot


def _date(at: str | None) -> str:
    return (at or "")[:10]


def done(case: CaseFile) -> list[str]:
    """What has happened on the case, in plain words with dates (never the C-file's contents)."""
    out = []
    for key, name in (("21-22a", "VA Form 21-22a (appoints our attorney)"), ("fee_agreement", "the fee agreement")):
        doc = case.documents.get(key)
        if doc and doc.signed_at:
            out.append(f"the veteran signed {name} on {_date(doc.signed_at)}")
        if doc and doc.countersigned_at:
            out.append(f"our attorney countersigned {name} on {_date(doc.countersigned_at)}")
    filed = case.filings
    if "21-22a" in filed:
        out.append(f"we filed the 21-22a with VA on {_date(filed['21-22a'].at)}")
    if "itf" in filed:
        itf = filed["itf"].data.get("itf_date") or _date(filed["itf"].at)
        out.append(f"we filed an intent to file on {itf}; it protects the start date for benefits")
    if "fee_agreement" in filed:
        out.append(f"we sent the fee agreement to VA's Office of General Counsel on {_date(filed['fee_agreement'].at)}")
    if case.stage >= 4:
        out.append("we asked VA for the veteran's claims file (C-file)")
    if case.prep.pulled:
        out.append("the claims file arrived" + (" and our team finished reading it" if case.prep.done else
                                                "; our team is reading it now"))  # fmt: skip
    return out


def deadlines(case: CaseFile) -> list[str]:
    out = []
    if (itf := case.filings.get("itf")) and (expires := itf.data.get("expires")):
        out.append(f"the intent to file holds until {expires} (the claim must be filed by then)")
    return out + [f"{t.text} (due {t.due})" for t in case.tasks if t.kind == "deadline" and not t.done_at]


def working_now(case: CaseFile) -> str:
    if case.side_state == "needs_human":
        return "a person on our team is handling the case"
    if case.side_state == "closed":
        return "nobody: the case is closed"
    if case.owner == "claims_prep":
        return "our team (claims prep) is reading the claims file"
    if case.stage == 5:
        return "our attorney is reviewing the file"
    return "nobody right now (waiting on VA, or between steps)"


def snapshot(turn: Turn) -> dict:
    """Support's read-only view of the case (L30): no answers, no C-file facts, no face note, no
    staff tasks (they can quote the veteran's crisis words)."""
    case = turn.case
    events = turn.rt.store.events(turn.case_id, types=("support_log", "kb_search"), last=EARLIER_QA)
    earlier = [f"{_date(e.at)} {e.type}: " + (f"[{e.data['kind']}] {e.data['text']}" if e.type == "support_log" else
               f"{e.data['question']!r} answered={e.data['answered']}") for e in events]  # fmt: skip
    return {
        "stage": f"{case.stage}: {STAGE_NAMES[case.stage]}",
        "side_state": case.side_state,
        "why": case.stop.reason if case.stop else None,  # side_reason can be "crisis" or a harness error
        "working_on_it_now": working_now(case),
        "done": done(case),
        "deadlines": deadlines(case),
        "fee": fee_line(case),
        "already_passed_on": [f"{f.kind}: {f.text} ({f.status})" for f in case.flags],
        "earlier_qa": earlier,
    }


def context(turn: Turn) -> str:
    return (
        f"## Case snapshot (read-only)\n{json.dumps(snapshot(turn), indent=1)}\n\n"
        f"## Last {HISTORY} messages\n{conversation(turn, HISTORY)}"
    )


# ------------------------------------------------------------------------------ tools


class LogArgs(BaseModel):
    kind: Literal["question", "status", "other"]
    text: str = Field(min_length=3, description="one line: what was asked and what you answered or did")


class FlagArgs(BaseModel):
    kind: FlagKind
    text: str = Field(min_length=2, description="what the veteran said, in a few words (e.g. 'knees')")


class EscalateArgs(BaseModel):
    reason: str = Field(min_length=3, description="why a person must read this, in one line")


def log_event(turn: Turn, args: LogArgs) -> str:
    turn.rt.store.append_event(turn.case_id, "support_log", {"kind": args.kind, "text": args.text}, actor="support")
    return "logged"


def escalate(turn: Turn, args: EscalateArgs, done_this_turn: list[str]) -> str:
    if done_this_turn:
        return "already handed to staff this turn"
    done_this_turn.append(args.reason)
    detail = f"{args.reason}. The veteran wrote: {turn.incoming}"
    event = turn.rt.escalate(turn.case_id, args.reason, actor="support", detail=detail)
    turn.deferred.append(turn.rt.wake_job(event))
    return "handed to staff: a person will follow up with the veteran"


def tools(turn: Turn) -> list[ToolSpec]:
    escalated: list[str] = []
    return [
        kb_tool(turn),
        ToolSpec("get_case", "Reload the read-only case snapshot (stage, what's done, deadlines, fee, "
                 "earlier Q&A).", NoArgs, lambda a: snapshot(turn)),
        ToolSpec("log_event", "Write one line to the case's event log: what was asked and what you "
                 "answered. The team and later turns read it.", LogArgs, lambda a: log_event(turn, a)),
        ToolSpec("flag_orchestrator", "Pass something that would change the case to the orchestrator, "
                 "which decides what to do: new_condition, contact_change or complaint.", FlagArgs,
                 lambda a: turn.rt.flag(turn.case_id, a.kind, a.text, turn)),
        ToolSpec("escalate", "Hand this message to a staff member (a person follows up). For what you "
                 "can't answer from the snapshot or kb_search.", EscalateArgs, lambda a: escalate(turn, a, escalated)),
    ]  # fmt: skip


# ------------------------------------------------------------------------------ guard


def guard(turn: Turn, name: str, args: BaseModel) -> str | None:
    text = getattr(args, "text", None) or getattr(args, "reason", None)
    if text and redact_chat(text)[1]:
        return "ID numbers and dates of birth never go in the case file; leave them out"
    if name == "flag_orchestrator" and (
        same := [f.text for f in turn.case.flags if f.kind == args.kind and f.status != "handled"]
    ):
        return f"a {args.kind} flag is already with the orchestrator ({', '.join(same)}); don't flag it again"
    return None


def spec() -> AgentSpec:
    return AgentSpec(
        name="support", instructions=INSTRUCTIONS, tools=tools, context=context, guard=guard,
        max_iters=5, timeout_s=60,
    )  # fmt: skip
