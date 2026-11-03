"""The stage table and its guard (plan §2).

  1 screening (intake pass 1)        -> 2 when every screening field is answered or unknown and
                                          no stop rule fired
  2 account opening (intake pass 1)  -> 3 when the 21-22a is submitted and the ITF filed
  3 filed (pass 1 ends)              -> 4 only by the orchestrator's `run_prep` handoff
  4 C-file requested (prep, then intake pass 2)
                                     -> 5 when claims prep is done and every pass-2 checklist
                                          field is filled or marked unknown
  5 gaps closed: ready for attorney review (the demo's end)
  6 file review done: not reachable (needs F7)

Code derives the stage and the waiting state from the case file after every change (`settle`)
and runs each proposed change through the same guard (`check_stage`, `check_side`) that checks
the orchestrator's moves and handoffs. Moves inside one owner's stages happen automatically;
a move to another owner only through a handoff (`check_handoff`). The only move back is from
stage 5 to stage 4 (F9: other moves back would need rebuilt stages); it leaves a pending reopen
item in pass 2 (`CaseFile.reopen`), so stage 5 waits until intake asks about it. A fired stop rule parks the
case: `closed` while nothing is filed (or `needs_human` when the rule leaves it to an attorney),
`needs_human` after filing (a person decides on withdrawal).
"""

from __future__ import annotations

from typing import Any

from agent.casefile import PARKED, CaseFile, Reopen

SIDE_STATES = ("waiting_on_veteran", "waiting_on_attorney", "waiting_on_va", *PARKED)
SIGNED_FORMS = ("21-22a", "fee_agreement")


def entry_unmet(case: CaseFile, stage: int) -> str | None:
    """Why `stage`'s entry criteria (the previous stage's exit criteria) don't hold, or None."""
    if stage == 1:
        return None
    if stage == 2:
        missing = case.missing("screen")
        if missing is None:
            return "stage 1 exit criteria not met: screening checklist not built"
        if missing:
            return f"stage 1 exit criteria not met: screening fields missing: {', '.join(missing)}"
        if case.stop:
            return f"stage 1 exit criteria not met: stop rule {case.stop.rule} fired"
        return None
    if stage == 3:
        if not case.filed("21-22a", "itf"):
            return "stage 2 exit criteria not met: the 21-22a and the intent to file must both be filed"
        return None
    if stage == 4:
        return entry_unmet(case, 3)
    if stage == 5:
        if not case.prep.done:
            return "stage 4 exit criteria not met: claims prep has not returned"
        missing = case.missing("pass2")
        if missing is None:
            return "stage 4 exit criteria not met: pass-2 checklist not built"
        if missing:
            return f"stage 4 exit criteria not met: intake fields missing: {', '.join(missing)}"
        return None
    if stage == 6:
        return "stage 5 exit criteria not met: no file review (not built: F7)"
    return f"no stage {stage}"


def check_stage(case: CaseFile, to: int, actor: str, reason: str | None = None) -> str | None:
    """Guard for a stage move. `actor` is `derive` (code), `handoff`, or the agent moving it."""
    if to == case.stage:
        return None
    if case.parked:
        return f"the case is {case.side_state}: only a person can move it"
    if to < case.stage:
        if actor != "orchestrator":
            return "only the orchestrator moves a case back"
        if to != 4:
            return "the only move back is to stage 4 (pass 2), from stage 5"
        if not reason:
            return "a move back needs a reason"
        if case.owner:
            return f"{case.owner} holds the case; a move back happens between owners"
        return None
    if to != case.stage + 1:
        return f"can't skip from stage {case.stage} to stage {to}"
    if to == 4 and actor != "handoff":
        return "stage 4 starts only with the orchestrator's run_prep handoff"
    if actor == "orchestrator":
        return "forward moves happen in code when the exit criteria hold, or by a handoff"
    return entry_unmet(case, to)


def check_side(case: CaseFile, to: str | None, actor: str, reason: str | None = None) -> str | None:
    """Guard for entering (or leaving, `to=None`) a side state."""
    if to == case.side_state:
        return None
    if case.parked:
        return f"the case is {case.side_state}: only a person can move it"
    if to in PARKED:
        if not reason:
            return f"{to} needs a reason"
        if to == "closed" and case.filings:
            return "something was filed with VA: a person decides on withdrawal (needs_human), not closed"
        return None
    if to is not None and to not in SIDE_STATES:
        return f"no side state {to!r}"
    if actor != "derive":
        return "waiting states are derived from the case file, not set"
    return None


def check_handoff(case: CaseFile, agent: str, running: set[str]) -> str | None:
    """Guard for the orchestrator's run_intake / run_prep. `running`: agents with a live turn."""
    if case.parked:
        return f"the case is {case.side_state}"
    if case.owner:
        return f"{case.owner} owns the case"
    if busy := running & {"intake", "claims_prep"}:  # A3: one case-owning sub-agent at a time
        return f"{', '.join(sorted(busy))} still has a running turn"
    if agent == "intake":
        if case.stage == 1:
            return None
        if case.stage == 4:
            return None if case.prep.done else "pass 2 starts after claims prep returns"
        if case.stage == 5:
            return "stage 5: move the case back to stage 4 with a reason first"
        return f"intake has no pass at stage {case.stage}"
    if agent == "claims_prep":
        if case.stage != 3:
            return f"claims prep starts at stage 3 (the case is at stage {case.stage})"
        return check_stage(case, 4, "handoff")
    return f"no handoff to {agent}"


def _derived_side(case: CaseFile) -> str | None:
    if case.owner == "intake" and case.stage == 2 and _awaiting_countersign(case):
        return "waiting_on_attorney"
    if case.owner == "intake" and case.awaiting_veteran:
        return "waiting_on_veteran"
    if case.owner is None and case.stage in (3, 4):
        return "waiting_on_va"  # between stages: filed, or claims prep returned
    return None


def _awaiting_countersign(case: CaseFile) -> bool:
    docs = [case.documents.get(f) for f in SIGNED_FORMS]
    return all(d and d.signed_at for d in docs) and any(not d.countersigned_at for d in docs)


def settle(case: CaseFile) -> list[dict[str, Any]]:
    """Derive the stage and side state from the case file; apply what the guard allows.

    Mutates `case`; returns the events to log (`stage_changed`, `refused`)."""
    events: list[dict[str, Any]] = []
    if case.parked:
        return events
    if case.stop:
        to = "needs_human" if case.filings else case.stop.to
        reason = f"stop rule {case.stop.rule}: {case.stop.reason}"
        events.append(move(case, to, "derive", reason))
        return events
    while case.owner == "intake" and case.stage in (1, 2, 4):
        to = case.stage + 1
        if entry_unmet(case, to):
            break
        events.append(_move_stage(case, to, "derive", "exit criteria met"))
    side = _derived_side(case)
    if side != case.side_state and case.side_state not in PARKED:
        if refusal := check_side(case, side, "derive"):
            events.append({"type": "refused", "data": {"move": str(side), "actor": "derive", "reason": refusal}})
        else:
            events.append(_move_side(case, side, "derive", None))
    return events


def _move_stage(case: CaseFile, to: int, actor: str, reason: str | None) -> dict[str, Any]:
    event = {"type": "stage_changed", "data": {"from": case.stage, "to": to, "actor": actor, "reason": reason}}
    if to < case.stage:  # back to pass 2: intake rebuilds its checklist, with the reopen item
        case.checklist["pass2"] = None
        before = case.answers.get("claim_conditions")
        case.reopen = Reopen(reason=reason or "moved back", before=before and before.model_dump(mode="json"))
    case.stage = to
    return event


def _move_side(case: CaseFile, to: str | None, actor: str, reason: str | None) -> dict[str, Any]:
    event = {"type": "side_state_changed",
             "data": {"from": case.side_state, "to": to, "actor": actor, "reason": reason}}  # fmt: skip
    case.side_state, case.side_reason = to, reason
    if to in PARKED:
        case.awaiting_veteran = False
    return event


def move(case: CaseFile, to: int | str, actor: str, reason: str | None) -> dict[str, Any]:
    """A guarded move by an agent or a rule. Returns the event: `stage_changed`,
    `side_state_changed`, or `refused` (with the reason for the caller)."""
    if isinstance(to, int):
        refusal = check_stage(case, to, actor, reason)
        if refusal is None:
            return _move_stage(case, to, actor, reason)
    else:
        refusal = check_side(case, to, actor, reason)
        if refusal is None:
            event = _move_side(case, to, actor, reason)
            if to in PARKED:
                case.owner, case.goal = None, None  # a person (or nobody) has the case now
            return event
    return {"type": "refused", "data": {"move": str(to), "actor": actor, "reason": refusal}}
