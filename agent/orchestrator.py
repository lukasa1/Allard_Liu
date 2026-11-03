"""The orchestrating agent: keeps the case moving and decides what runs next.

Every case event wakes it. It computes the actions the case's state ALLOWS (code: the stage
table below), lets the policy CHOOSE one (an LLM via DSPy, or a deterministic policy offline),
executes it, and repeats until it hands the case to a subagent (at most one handoff per wake; the
subagent's result arrives as the next event) or the only option is to wait. Tool actions with no
subagent (filing the 21-22a, the intent to file, requesting the C-file) may run back to back.

Honest framing: this is a gated workflow with model tie-breaking. Code decides what is possible,
and most of the time exactly one action is; the model's choices matter where several are open
(ordering, and whether a flag needs a person before the case moves on). The open-ended agency is
in the subagents. Code guarantees no gate is skipped: no filing before the attorney countersigns,
no C-file before the 21-22a and the intent to file are in, no pass 2 before claims prep, nothing
after a crisis but the hand-off.

Every step is logged on the case (`case.decisions`) with the options it had and its reason, which
is what the demo's case panel shows.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from agent.case import CHAT_PHASES, TERMINAL_PHASES, CaseState, Decision

STOP_DECISIONS = ("not_veteran", "rated_100")
MAX_STEPS_PER_EVENT = 12


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    allowed: Callable[[CaseState], bool]
    handoff: bool = False  # hands the case to a subagent: the wake ends after it (one per wake)


def _outcome(case: CaseState) -> str | None:
    return case.intake_outcome.decision if case.intake_outcome else None


def _no_attention_blockers(case: CaseState) -> bool:
    return not case.escalation and _outcome(case) not in (
        "attorney_review",
        "escalated",
        "incomplete",
    )


# The stage table. Each action's gate is its stage's entry criteria: the policy can only choose
# among the actions whose gate holds, so it can't skip one (e.g. no C-file before the 21-22a is
# countersigned and filed and the intent to file is in; no pass 2 before claims prep).
ACTIONS: list[Action] = [
    Action(
        "request_va_sign_in",
        "Offer the veteran 'Sign in with VA' so their service history, ratings and claims come from VA's records instead of questions. They may skip it.",
        lambda c: c.phase == "new" and c.va_consent is None,
    ),
    Action(
        "fetch_va_records",
        "Pull the veteran's VA records through Lighthouse (service history, disability ratings, claims, active POA) and pre-fill the intake.",
        lambda c: (
            c.va_consent == "granted" and c.va_records is None and c.phase not in TERMINAL_PHASES
        ),
    ),
    Action(
        "start_screening",
        "Hand the case to the intake subagent for pass 1: the eligibility screening, in chat.",
        lambda c: (
            c.phase in ("new", "va_sign_in")
            and c.va_consent in ("granted", "declined", "not_offered")
            and (c.va_consent != "granted" or c.va_records is not None)
        ),
        handoff=True,
    ),
    Action(
        "start_poa",
        "Screening passed: have the intake subagent get VA Form 21-22a filled and signed (POA skill).",
        lambda c: (
            c.screening_done and _outcome(c) is None and not c.poa_signed and c.phase == "screening"
        ),
        handoff=True,
    ),
    Action(
        "request_attorney_signoff",
        "The veteran signed the 21-22a: ask the attorney to review and countersign it (Item 25A) before anything is filed.",
        lambda c: c.phase == "poa" and c.poa_signed and not c.poa_countersigned,
    ),
    Action(
        "submit_poa_to_va",
        "The attorney countersigned: submit the 21-22a to VA (Lighthouse Benefits Claims POST /forms/2122, or a manual-filing task if there's no VA sign-in).",
        lambda c: c.poa_countersigned and c.poa_submission is None and c.phase not in TERMINAL_PHASES,
    ),
    Action(
        "file_intent_to_file",
        "File an intent to file (VA Form 21-0966) to lock in the veteran's effective date.",
        lambda c: c.poa_submission is not None and c.itf is None and c.phase not in TERMINAL_PHASES,
    ),
    Action(
        "fetch_cfile",
        "The 21-22a and the intent to file are filed: request the veteran's C-file (Benefits Documents).",
        lambda c: (
            c.phase == "attorney_signoff"
            and c.poa_submission is not None
            and c.itf is not None
            and not c.cfile_documents
            and not c.cfile_manual
        ),
    ),
    Action(
        "run_claims_prep",
        "The C-file is here: hand the case to claims prep (read the C-file, write the face note, pre-fill intake pass 2, list what the C-file contradicts).",
        lambda c: c.phase == "case_prep" and bool(c.cfile_documents) and c.face_note is None,
        handoff=True,
    ),
    Action(
        "continue_intake",
        "Claims prep is done (or no C-file can be read): hand the case to the intake subagent for pass 2, which asks only what is still missing.",
        lambda c: (
            c.phase == "case_prep"
            and (c.face_note is not None or c.cfile_manual)
            and c.intake_outcome is None
        ),
        handoff=True,
    ),
    Action(
        "send_to_attorney_review",
        "Intake pass 2 is complete and the face note is ready: hand the case (intake record, signed 21-22a, face note) to an attorney.",
        lambda c: c.phase == "intake" and _outcome(c) == "eligible" and c.face_note is not None,
    ),
    Action(
        "close_case",
        "Intake found the firm can't take the case (not a veteran, or already rated 100%): close it politely.",
        lambda c: (  # after a filing, a person decides (withdraw the 21-22a?): see attention()
            _outcome(c) in STOP_DECISIONS and c.phase not in TERMINAL_PHASES
            and c.poa_submission is None and c.itf is None
        ),
    ),
    # Support's flags (the veteran said something that would change the case while it is parked).
    # The orchestrator decides what each one means; a withdrawal or a request for a person is
    # never a choice: the session escalates those by rule.
    Action(
        "reopen_intake_for_new_condition",
        "The veteran wants to add a condition after intake ended: reopen intake to ask about it (the condition, then its narrative prompts), then return the case to attorney review.",
        lambda c: (
            any(f["kind"] == "new_condition" for f in c.open_flags)
            and c.phase == "attorney_review" and _outcome(c) == "eligible" and not c.escalation
        ),
        handoff=True,
    ),
    Action(
        "pass_flags_to_staff",
        "Record the veteran's open flags (a new condition, new contact details, a complaint) as staff tasks for the attorney's review, without changing the case's stage.",
        lambda c: bool(c.open_flags),
    ),
    Action(
        "hand_off_to_staff",
        "Something needs a person now (crisis, attorney review of discharge, missing data, a face-note flag, no C-file): create a staff task and pause the case.",
        lambda c: bool(c.attention()) and c.phase not in TERMINAL_PHASES,
        handoff=True,
    ),
]
ACTION_BY_NAME = {a.name: a for a in ACTIONS}
WAIT = "wait"


def allowed_actions(case: CaseState) -> list[str]:
    names = [a.name for a in ACTIONS if a.allowed(case)]
    if case.escalation:  # after a crisis or a request for a person, only the hand-off
        names = [n for n in names if n in ("hand_off_to_staff", "pass_flags_to_staff")]
    if case.open_flags and names:  # the veteran was told it was passed on: decide, don't wait
        return names
    # Waiting is only an option while someone else has the next move: a subagent waiting on the
    # veteran, the VA sign-in card, or a parked (terminal) case. Otherwise the agent must act,
    # so a model can't leave a finished intake (or a crisis) sitting with nobody on it.
    if (
        (case.phase in CHAT_PHASES and case.awaiting_veteran)
        or case.phase in TERMINAL_PHASES
        or case.va_consent == "pending"
        or (case.phase == "attorney_signoff" and not case.poa_countersigned)  # the attorney's move
        or (case.phase == "case_prep" and not case.cfile_documents and not case.cfile_manual)  # VA's move
    ):
        return names + [WAIT]
    return names or [WAIT]


# ------------------------------------------------------------------------------- policies


class OfflinePolicy:
    """Deterministic: the first allowed action in ACTIONS order, but a hand-off wins."""

    name = "offline"

    def choose(self, case: CaseState, event: str, allowed: list[str]) -> tuple[str, str]:
        if "hand_off_to_staff" in allowed and not _no_attention_blockers(case):
            return "hand_off_to_staff", "a person must take over: " + "; ".join(case.attention())
        for name in allowed:
            if name not in ("hand_off_to_staff", WAIT):
                return name, ACTION_BY_NAME[name].description
        if WAIT in allowed:
            return WAIT, "waiting for the veteran or staff"
        if "hand_off_to_staff" in allowed:  # nothing else can move the case
            return "hand_off_to_staff", "; ".join(case.attention())
        return WAIT, "nothing to do"


ORCHESTRATOR_INSTRUCTIONS = """You are the orchestrating agent for one veteran's case at a law firm that \
represents veterans before VA. You keep the case moving: after each event, pick the single next action \
from `allowed_actions` (only those are possible right now). Prefer moving the case forward. Choose \
hand_off_to_staff only when `case.attention` shows something a person must handle before the case can \
continue safely; minor issues can go along with the case to the attorney. Choose wait only when no \
other action makes sense. Give a one-sentence reason.

Your skills (call read_skill with a name to read one; only when you need it):
{skills}"""


class DSPyPolicy:
    name = "dspy"

    def __init__(self, lm) -> None:
        import dspy

        class ChooseNextAction(dspy.Signature):
            case: str = dspy.InputField(desc="JSON summary of the case")
            event: str = dspy.InputField(desc="what just happened")
            allowed_actions: str = dspy.InputField(desc="JSON list of {name, description}")
            action: str = dspy.OutputField(desc="exactly one name from allowed_actions")
            reason: str = dspy.OutputField(desc="one sentence")

        from agent.skills import read_skill, skill_index

        def read_orchestrator_skill(name: str) -> str:
            """Load one of your skills' full directions by name."""
            return read_skill("orchestrator", name)

        self.lm = lm
        instructions = ORCHESTRATOR_INSTRUCTIONS.format(skills=skill_index("orchestrator"))
        # A small ReAct loop: the model may read a skill (progressive disclosure), then chooses.
        self.predict = dspy.ReAct(
            ChooseNextAction.with_instructions(instructions),
            tools=[dspy.Tool(read_orchestrator_skill, name="read_skill")],
            max_iters=3,
        )
        self._dspy = dspy

    def choose(self, case: CaseState, event: str, allowed: list[str]) -> tuple[str, str]:
        if allowed == [WAIT]:
            return WAIT, "[rule] waiting for the veteran or staff (no other option)"
        if (
            case.phase in CHAT_PHASES
            and not case.escalation
            and allowed == ["hand_off_to_staff", WAIT]
        ):
            # Mid-conversation with nothing but a non-blocking concern: the subagent keeps talking.
            if _no_attention_blockers(case):
                return WAIT, "[rule] the intake subagent is talking with the veteran"
        options = [
            {
                "name": n,
                "description": ACTION_BY_NAME[n].description
                if n in ACTION_BY_NAME
                else "Do nothing until the next event.",
            }
            for n in allowed
        ]
        try:
            with self._dspy.context(lm=self.lm):
                pred = self.predict(
                    case=json.dumps(case.summary()),
                    event=event,
                    allowed_actions=json.dumps(options),
                )
            raw = (pred.action or "").strip()
            action = _match_action(raw, allowed)
            if action is not None:
                return action, (pred.reason or "").strip()
            action = raw
            fallback, why = OfflinePolicy().choose(case, event, allowed)
            return fallback, f"[model chose {action!r}, not allowed; fallback] {why}"
        except (
            Exception
        ) as exc:  # model unreachable: the deterministic policy keeps the case moving
            fallback, why = OfflinePolicy().choose(case, event, allowed)
            return fallback, f"[model unavailable: {type(exc).__name__}; fallback] {why}"


def _match_action(text: str, allowed: list[str]) -> str | None:
    """The allowed action named in the model's output ("`start_screening`.", "Action: wait")."""
    if text in allowed or not allowed:
        return text if text in allowed else None
    names = sorted(allowed, key=len, reverse=True)
    pattern = r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z0-9_])"
    by_lower = {n.lower(): n for n in names}
    found = {by_lower[m.group(1).lower()] for m in re.finditer(pattern, text, re.IGNORECASE)}
    return found.pop() if len(found) == 1 else None  # two different names: ambiguous


# ------------------------------------------------------------------------------- orchestrator


class Orchestrator:
    """Runs the choose -> execute loop. `execute(action, case)` is supplied by the session."""

    def __init__(self, policy, execute: Callable[[str, CaseState], None]) -> None:
        self.policy = policy
        self.execute = execute

    def handle(self, case: CaseState, event: str) -> list[str]:
        """Process one event. Returns the actions taken (excluding the final wait)."""
        taken: list[str] = []
        for _ in range(MAX_STEPS_PER_EVENT):
            allowed = allowed_actions(case)
            if case.escalation and "hand_off_to_staff" in allowed:
                # Safety: a crisis or a request for a person is handed off by rule, not by the model.
                action, reason, policy_name = "hand_off_to_staff", f"escalated: {case.escalation}", "rule"
            else:
                action, reason = self.policy.choose(case, event, allowed)
                if reason.startswith("[model"):
                    policy_name = "dspy_fallback"
                elif reason.startswith("[rule]"):  # decided without calling the model
                    policy_name = "rule"
                else:
                    policy_name = self.policy.name
            case.decisions.append(
                Decision(
                    event=event, action=action, reason=reason, allowed=allowed, policy=policy_name
                )
            )
            if action == WAIT:
                break
            self.execute(action, case)
            taken.append(action)
            if ACTION_BY_NAME[action].handoff:
                break  # one handoff per wake: the subagent's result is the next wake's event
            event = f"completed {action}"
        else:
            case.decisions.append(Decision(
                event=event, action=WAIT, reason=f"step limit ({MAX_STEPS_PER_EVENT}) reached in one wake",
                allowed=allowed_actions(case), policy="rule",
            ))  # fmt: skip
        return taken
