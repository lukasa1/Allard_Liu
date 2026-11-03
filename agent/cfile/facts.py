"""What a face note needs from a C-file, as structured facts.

The same schema is used three ways: the synthetic C-file generator writes documents FROM it
(ground truth), the extractor reads documents INTO it (offline regex or DSPy), and the renderer
turns it into the firm's face-note template. Scoring compares extracted facts to the truth.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from agent.intake.schema import RatedCondition, ServicePeriod
from agent.personas import Persona

Outcome = Literal["granted", "denied", "deferred"]


class Issue(BaseModel):
    condition: str
    outcome: Outcome
    pct: int | None = None


class Decision(BaseModel):
    decision_date: str  # YYYY-MM-DD
    notified: str | None = None  # date of the notification letter (deadlines run from it)
    form: str | None = None  # filing form named in the decision's evidence list (526EZ, 0995, ...)
    filed: str | None = None
    issues: list[Issue] = Field(default_factory=list)


class PriorRep(BaseModel):
    name: str
    kind: Literal["attorney", "agent", "vso"]
    signed: str | None = None


class PendingFiling(BaseModel):
    form: str
    filed: str
    conditions: list[str] = Field(default_factory=list)


class CfileFacts(BaseModel):
    dob: str | None = None
    service_periods: list[ServicePeriod] = Field(default_factory=list)
    mos: list[str] = Field(default_factory=list)
    combined_rating: int | None = None  # from the most recent code sheet
    sc_conditions: list[RatedCondition] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    prior_reps: list[PriorRep] = Field(default_factory=list)
    pending_filings: list[PendingFiling] = Field(default_factory=list)
    # Documents a person must read: unreadable, or read without their key facts. No dates or
    # contents, only document labels: these become flags, which reach tasks and prompts.
    problems: list[str] = Field(default_factory=list)


def _plus_days(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def default_decisions(p: Persona) -> list[Decision]:
    """A persona with a rating but no `cfile.decisions`: one old decision granting what's rated."""
    t = p.truth
    if not (t.filed_before and t.sc_conditions):
        return []
    last_end = max((sp.end for sp in t.service_periods if sp.end), default="2015-01")
    decided = f"{int(last_end[:4]) + 2}-{last_end[5:7]}-15"
    return [
        Decision(
            decision_date=decided,
            notified=_plus_days(decided, 4),
            form="526EZ",
            filed=f"{int(last_end[:4]) + 1}-{last_end[5:7]}-01",
            issues=[
                Issue(condition=c.name, outcome="granted", pct=c.rating_pct)
                for c in t.sc_conditions
            ],
        )
    ]


def truth_facts(p: Persona) -> CfileFacts:
    """The ground truth a perfect reading of the persona's synthetic C-file would produce."""
    spec = p.cfile
    decisions = [
        Decision.model_validate(d) for d in spec.get("decisions", [])
    ] or default_decisions(p)
    rated = bool(decisions) and bool(p.truth.receiving_va_pay)  # a code sheet exists
    return CfileFacts(
        dob=p.identity.get("dob") if p.truth.service_periods else None,  # read from the DD-214
        service_periods=list(p.truth.service_periods),
        mos=list(p.truth.mos) if p.truth.service_periods else [],
        combined_rating=p.truth.rating_pct if rated else None,
        sc_conditions=list(p.truth.sc_conditions) if rated else [],
        decisions=sorted(decisions, key=lambda d: d.decision_date),
        prior_reps=[PriorRep.model_validate(r) for r in spec.get("prior_reps", [])],
        pending_filings=[PendingFiling.model_validate(f) for f in spec.get("pending_filings", [])],
    )
