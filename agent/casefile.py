"""The case file: one veteran's case as every agent sees it (L7).

The case file is the shared memory. It holds what the stage table is derived from (answers and
the checklist, documents, filings, claims prep's output, a fired stop rule) and the stage, owner
and side state themselves. It holds no event log: the store's `events` table is the log, and
each agent's recent conversation is read from it (L3). The SSN is never here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Agent = Literal["orchestrator", "intake", "claims_prep", "support"]
Owner = Literal["intake", "claims_prep"]  # the case-owning sub-agents (A3: one at a time)
SideState = Literal["waiting_on_veteran", "waiting_on_attorney", "waiting_on_va", "needs_human", "closed"]
PARKED = ("needs_human", "closed")
STAGE_NAMES = {
    1: "screening",
    2: "account opening",
    3: "filed",
    4: "C-file requested",
    5: "gaps closed (ready for attorney review)",
    6: "file review done",
}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Answer(BaseModel):
    value: Any  # the parsed value (None when unknown)
    source: str  # "veteran, chat <time>" | "C-file p. N" | "secure form"
    at: str = Field(default_factory=now)
    raw: str | None = None  # the text the value was parsed from, kept verbatim
    unknown: bool = False  # the veteran doesn't know or declined: counts as settled


class Conflict(BaseModel):
    """The C-file disagrees with an answer on file (A2). Claims prep's prefill records it; pass 2
    asks the veteran, and the veteran's new answer to `question` resolves it."""

    question: str  # the question id in questions.yaml
    on_file: Any  # the answer intake already had
    cfile: Any  # what the C-file says
    cite: str  # "C-file p. N"
    resolved_at: str | None = None


class DocState(BaseModel):
    """A document the veteran signs and the attorney countersigns (21-22a, fee agreement)."""

    document_id: str | None = None
    signed_at: str | None = None
    countersigned_at: str | None = None
    countersigned_by: str | None = None


class Filing(BaseModel):
    confirmation: str
    at: str = Field(default_factory=now)
    data: dict[str, Any] = Field(default_factory=dict)


class PrepState(BaseModel):
    """Claims prep's output. It is done when the face note is rendered, `verify` passed or the
    lines it couldn't cite were escalated, and prefill ran (§2, stage 4)."""

    face_note: str | None = None
    verified: bool = False
    uncertain: list[str] = Field(default_factory=list)
    prefill_done: bool = False
    continuations: int = 0

    @property
    def done(self) -> bool:
        return bool(self.face_note) and (self.verified or bool(self.uncertain)) and self.prefill_done


class Task(BaseModel):
    kind: str  # staff | deadline | urgent
    text: str
    due: str | None = None
    created_at: str = Field(default_factory=now)
    done_at: str | None = None


class Flag(BaseModel):
    """Something support heard that would change the case; the orchestrator decides (L12)."""

    kind: str
    text: str
    at: str = Field(default_factory=now)
    status: Literal["open", "held", "handled"] = "open"


class StopRule(BaseModel):
    rule: str  # not_veteran | rated_100 | non_honorable_period
    reason: str
    # Where the case goes while nothing is filed: closed, or a person (the attorney) decides.
    # Once anything is filed it is always needs_human.
    to: Literal["closed", "needs_human"] = "closed"


class SubagentResult(BaseModel):
    """What a sub-agent hands back (L13). The orchestrator reads only these, never transcripts."""

    agent: str = ""  # set by the harness
    finished: str = Field(description="what finished, in one line")
    wrote: list[str] = Field(default_factory=list, description="case-file fields written")
    needs: list[str] = Field(default_factory=list, description="what must happen next")
    flags: list[str] = Field(default_factory=list, description="anything the orchestrator must decide")


class CaseFile(BaseModel):
    case_id: str
    created_at: str = Field(default_factory=now)
    persona_id: str | None = None  # demo/eval only: which synthetic veteran the simulators serve

    stage: int = 1
    owner: Owner | None = None
    side_state: SideState | None = None
    side_reason: str | None = None
    goal: str | None = None  # the owner's goal from the orchestrator's handoff
    awaiting_veteran: bool = False  # the owner's last turn asked the veteran something

    answers: dict[str, Answer] = Field(default_factory=dict)
    # Missing fields per part ("screen", "pass2"), rebuilt by intake's code from the answers.
    # None: not built yet (so never "complete").
    checklist: dict[str, list[str] | None] = Field(default_factory=dict)
    stop: StopRule | None = None
    conflicts: list[Conflict] = Field(default_factory=list)  # C-file vs intake (claims prep writes)
    documents: dict[str, DocState] = Field(default_factory=dict)  # "21-22a" | "fee_agreement"
    filings: dict[str, Filing] = Field(default_factory=dict)  # "21-22a" | "itf" | "fee_agreement"
    prep: PrepState = Field(default_factory=PrepState)
    tasks: list[Task] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)

    def filed(self, *names: str) -> bool:
        return all(n in self.filings for n in names)

    def missing(self, part: str) -> list[str] | None:
        return self.checklist.get(part)

    @property
    def parked(self) -> bool:
        return self.side_state in PARKED

    def memory(self) -> dict[str, Any]:
        """The case-file part of a memory block (L10): what the case is, not how agents talk."""
        data = self.model_dump(mode="json", exclude={"created_at", "persona_id"})
        data["stage_name"] = STAGE_NAMES[self.stage]
        data["prep"]["done"] = self.prep.done
        data["open_tasks"] = [t.text for t in self.tasks if t.done_at is None]
        del data["tasks"]
        return data
