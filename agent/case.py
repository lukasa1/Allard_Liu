"""Persisted state of one case: the contract between the orchestrator and its subagents.

A case lives for months, so it is not one long LLM conversation: everything the orchestrator
decides from is here, saved as JSON after every turn (CaseStore). The subagents' working memory
(the intake's pending question, answers and transcript; the POA step's position; the host's open
cards) is saved in the same file under `subagents`, so CaseSession.resume() picks a case up again
after a restart, mid-conversation. Phases:

  new -> va_sign_in -> screening -> poa -> attorney_signoff -> case_prep -> intake -> attorney_review
         (VA records) (pass 1)     (sign)  (countersign, file   (C-file, claims  (pass 2)
                                            21-22a + ITF)        prep, prefill)
  terminal: closed (not eligible) | human_handoff (a person takes over)

Contact details copied from the POA skill's vault are kept here for the firm's staff. The SSN never
is. The date of birth appears only inside the face note, because the firm's template shows it;
the stored C-file facts keep it masked. (A production store would be encrypted like the vault.)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.cfile.facts import CfileFacts
from agent.intake.schema import IntakeRecord, Outcome
from agent.lighthouse.records import VaRecords

Phase = Literal[
    "new", "va_sign_in", "screening", "poa", "attorney_signoff", "case_prep", "intake",
    "attorney_review", "closed", "human_handoff",
]  # fmt: skip
CHAT_PHASES = ("screening", "poa", "intake")  # a subagent is talking with the veteran
TERMINAL_PHASES = ("attorney_review", "closed", "human_handoff")
SCHEMA_VERSION = 2


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class CaseEvent(BaseModel):
    type: str
    at: str = Field(default_factory=now)
    data: dict[str, Any] = Field(default_factory=dict)


class HumanTask(BaseModel):
    kind: str  # review | handoff | deadline | manual_filing | approval
    text: str
    due: str | None = None
    created_at: str = Field(default_factory=now)
    done_at: str | None = None  # set when the task is completed (e.g. the attorney countersigned)


class SubagentResult(BaseModel):
    """What a subagent hands back to the orchestrator (the orchestrator never reads transcripts)."""

    agent: Literal["intake", "poa", "claims_prep", "support"]
    status: Literal["working", "done", "stopped", "escalated", "answered", "needs_person"]
    event: str | None = None  # the case event it raises for the orchestrator, if any
    wrote: list[str] = Field(default_factory=list)  # case fields it changed
    needs: list[str] = Field(default_factory=list)  # what must happen next (for a person or a stage)
    flags: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """One orchestrator step: which action it took, why, and what it could have done."""

    at: str = Field(default_factory=now)
    event: str
    action: str
    reason: str
    allowed: list[str]
    policy: str  # offline | dspy | dspy_fallback | rule


class CaseState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    case_id: str
    created_at: str = Field(default_factory=now)
    phase: Phase = "new"
    persona_id: str | None = None  # demo/eval only: which synthetic veteran the stubs serve

    # not_offered: VA sign-in is off (the default; the firm hasn't approved collecting VA records
    # before representation), so pass 1 asks in chat.
    va_consent: Literal["pending", "granted", "declined", "not_offered"] | None = None
    icn: str | None = None
    va_records: VaRecords | None = None
    records_prefilled: list[str] = Field(default_factory=list)  # question ids VA's records settled

    screening_done: bool = False
    intake: IntakeRecord | None = None
    intake_outcome: Outcome | None = None

    poa_document_id: str | None = None
    poa_countersigned_at: str | None = None  # the attorney approved filing the 21-22a (Item 25A)
    poa_countersigned_by: str | None = None
    poa_submission: dict[str, Any] | None = None
    itf: dict[str, Any] | None = None

    cfile_documents: list[dict[str, Any]] = Field(default_factory=list)
    cfile_facts: CfileFacts | None = None
    cfile_skipped: int = 0
    face_note: str | None = None
    face_note_flags: list[str] = Field(default_factory=list)
    cfile_prefilled: list[str] = Field(default_factory=list)  # question ids the C-file settled
    cfile_discrepancies: list[str] = Field(default_factory=list)  # C-file vs intake, plain words

    escalation: str | None = None
    awaiting_veteran: bool = False  # a subagent asked the veteran something and is waiting
    cfile_manual: bool = False  # no C-file source: staff must download it from VBMS
    tasks: list[HumanTask] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    events: list[CaseEvent] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)  # model calls, tokens, cost (all turns)
    # Support's flags the orchestrator hasn't decided on yet: {kind, text, at, phase}
    open_flags: list[dict[str, Any]] = Field(default_factory=list)
    # Working memory for resuming (see CaseSession.resume); not shown to the orchestrator's model.
    subagents: dict[str, Any] = Field(default_factory=dict)

    @property
    def poa_signed(self) -> bool:
        return self.poa_document_id is not None

    @property
    def poa_countersigned(self) -> bool:
        return self.poa_countersigned_at is not None

    def attention(self) -> list[str]:
        """Reasons a person may need to step in now (offered to the orchestrator as hand-off)."""
        out = []
        if self.escalation:
            out.append(f"escalated: {self.escalation}")
        if self.intake_outcome and self.intake_outcome.decision in (
            "attorney_review",
            "incomplete",
            "escalated",
        ):
            out.append(
                f"intake ended '{self.intake_outcome.decision}': {'; '.join(self.intake_outcome.reasons)}"
            )
        if self.va_records and self.va_records.errors:
            out.append(f"VA records incomplete: {sorted(self.va_records.errors)}")
        if self.intake_outcome and self.intake_outcome.decision in ("not_veteran", "rated_100") and (
            self.poa_submission is not None or self.itf is not None
        ):
            out.append(
                f"intake found '{self.intake_outcome.decision}' after the 21-22a / intent to file were filed: "
                "decide whether to withdraw them and tell the veteran"
            )
        if self.cfile_manual:
            out.append("no C-file to read: staff must download it from VBMS for claims prep")
        out += [f"face note: {f}" for f in self.face_note_flags]
        return out

    def summary(self) -> dict[str, Any]:
        """Compact view for the orchestrator's prompt and the demo's case panel."""
        o = self.intake_outcome
        return {
            "phase": self.phase,
            "va_consent": self.va_consent,
            "va_records_fetched": self.va_records is not None,
            "screening_done": self.screening_done,
            "intake_outcome": o.decision if o else None,
            "fee_pct": o.fee_pct if o else None,
            "flags": o.flags if o else [],
            "poa_signed": self.poa_signed,
            "poa_countersigned": self.poa_countersigned,
            "poa_submitted": self.poa_submission is not None,
            "intent_to_file": bool(self.itf),
            "cfile_documents": len(self.cfile_documents),
            "face_note_ready": self.face_note is not None,
            "cfile_prefilled": len(self.cfile_prefilled),
            "attention": self.attention(),
            "open_tasks": [t.text for t in self.tasks if t.done_at is None],
            "open_flags": [f["kind"] for f in self.open_flags],
        }


class CaseStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def path(self, case_id: str) -> Path:
        return self.directory / f"{case_id}.json"

    def exists(self, case_id: str) -> bool:
        return self.path(case_id).exists()

    def load(self, case_id: str) -> CaseState:
        p = self.path(case_id)
        if not p.exists():
            return CaseState(case_id=case_id)
        data = json.loads(p.read_text())
        version = data.get("schema_version", 1)
        if version != SCHEMA_VERSION:  # no migrations yet: refuse rather than misread an old case
            raise ValueError(f"case {case_id} has schema version {version}, expected {SCHEMA_VERSION}")
        return CaseState.model_validate(data)

    def save(self, case: CaseState) -> None:
        data = case.model_dump(mode="json")
        if data.get("cfile_facts") and data["cfile_facts"].get("dob"):
            data["cfile_facts"]["dob"] = "**/**/" + data["cfile_facts"]["dob"][:4]
        # Atomic: a crash mid-write leaves the previous version, never a truncated file.
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=f".{case.case_id}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.path(case.case_id))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
