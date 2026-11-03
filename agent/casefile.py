"""The case file: one veteran's case as every agent sees it (L7).

The case file is the shared memory. It holds what the stage table is derived from (answers and
the checklist, documents, filings, claims prep's output, a fired stop rule) and the stage, owner
and side state themselves. It holds no event log: the store's `events` table is the log, and
each agent's recent conversation is read from it (L3). The SSN is never here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.ingest import untrusted

Agent = Literal["orchestrator", "intake", "claims_prep", "support"]
Owner = Literal["intake", "claims_prep"]  # the case-owning sub-agents (A3: one at a time)
SideState = Literal["waiting_on_veteran", "waiting_on_attorney", "waiting_on_va", "needs_human", "closed"]
PARKED = ("needs_human", "closed")
# The eval's conditions (L32). The demo always runs `cfile`.
#   ask_no_probes  intake skips its verification probes (a second service period, an old claim),
#                  and claims prep's prefill writes nothing (every question is asked in chat)
#   ask            the probes are asked; prefill still writes nothing
#   cfile          the probes, and prefill from the C-file with pass 2 confirming the conflicts
EvalCondition = Literal["ask_no_probes", "ask", "cfile"]
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

    def key(self) -> dict[str, Any]:
        """What identifies the answer, without the veteran's raw text or the time."""
        return self.model_dump(mode="json", exclude={"raw", "at"})


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
    """Claims prep's working memory and output (agent/claims_prep). It is done when the face note
    is rendered, `verify` passed or the lines it couldn't cite were escalated, and prefill ran
    (§2, stage 4). Recording a fact clears the face note, the verdict and prefill: both are built
    from the current fact table."""

    pulled: bool = False  # pull_cfile ran
    pages_read: list[int] = Field(default_factory=list)  # C-file pages read so far (citable)
    facts: list[dict[str, Any]] = Field(default_factory=list)  # the fact table, each fact with its cite
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
    rule: str  # not_veteran | rated_100 | non_honorable_period | screen_unresolved
    reason: str
    # Where the case goes while nothing is filed: closed, or a person (the attorney) decides.
    # Once anything is filed it is always needs_human.
    to: Literal["closed", "needs_human"] = "closed"


class Reopen(BaseModel):
    """The orchestrator moved the case back to stage 4 (pass 2). Until intake records
    `claim_conditions` again (the answer differs from `before`, or was recorded after `before_at`),
    pass 2 shows it as missing, so stage 5 waits."""

    reason: str
    at: str = Field(default_factory=now)
    before: dict[str, Any] | None = None  # the claim_conditions answer at the move back (`Answer.key`)
    before_at: str | None = None  # when that answer was recorded

    @staticmethod
    def of(case: CaseFile, reason: str) -> Reopen:
        before = case.answers.get("claim_conditions")
        return Reopen(reason=reason, before=before and before.key(), before_at=before and before.at)

    def pending(self, answer: Answer | None) -> bool:
        """True while `answer` is still the one on file at the move back."""
        return answer is not None and answer.key() == self.before and answer.at == self.before_at


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
    eval_condition: EvalCondition = "cfile"  # eval only (L32); never shown to a model

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
    reopen: Reopen | None = None  # the last move back to pass 2

    def filed(self, *names: str) -> bool:
        return all(n in self.filings for n in names)

    def missing(self, part: str) -> list[str] | None:
        return self.checklist.get(part)

    def flags_to_decide(self) -> list[int]:
        """Indexes of the flags the orchestrator decides now: open ones, and held ones once claims
        prep has handed back (held flags wait for prep's result, §3)."""
        return [i for i, f in enumerate(self.flags)
                if f.status == "open" or (f.status == "held" and self.owner != "claims_prep")]  # fmt: skip

    @property
    def parked(self) -> bool:
        return self.side_state in PARKED

    def memory(self) -> dict[str, Any]:
        """The case-file part of a memory block (L10): what the case is, not how agents talk.

        Text from outside the firm (the veteran's answers, C-file values, the face note, flags,
        tasks, conflicts, the reopen reason and answer) is one `untrusted` block (L6), under the key "untrusted"; the raw text
        an answer was parsed from is left out (no transcripts)."""
        data = self.model_dump(mode="json", include={"case_id", "stage", "owner", "side_state", "side_reason",
                                                     "goal", "awaiting_veteran", "stop", "documents", "filings"})  # fmt: skip
        data["stage_name"] = STAGE_NAMES[self.stage]
        # Claims prep's working memory stays out: what it produced, not how it read.
        data["prep"] = {"done": self.prep.done, "facts": len(self.prep.facts), "verified": self.prep.verified,
                        "prefill_done": self.prep.prefill_done, "face_note": bool(self.prep.face_note),
                        "uncertain": len(self.prep.uncertain)}  # fmt: skip
        data["answered"] = len(self.answers)
        text = {
            "answers": {k: a.model_dump(mode="json", exclude={"raw"}) for k, a in self.answers.items()},
            "checklist": self.checklist,
            "conflicts": [c.model_dump(mode="json") for c in self.conflicts],
            "face_note": self.prep.face_note,
            "uncertain": self.prep.uncertain,
            "open_tasks": [t.text for t in self.tasks if t.done_at is None],
            "flags": [f.model_dump(mode="json") for f in self.flags],
            "reopen": self.reopen and self.reopen.model_dump(mode="json"),
        }
        data["untrusted"] = untrusted("case-file text from the veteran, the C-file and the team",
                                      json.dumps(text, indent=1))  # fmt: skip
        return data
