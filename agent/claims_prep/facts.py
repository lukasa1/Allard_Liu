"""Claims prep's fact schema (L23, Luke's DEC): typed facts, each with a page citation.

`record_facts` takes a batch of these items. Values are normalized as they arrive (dates to ISO,
service dates to YYYY-MM, condition names through `normalize_condition`, branches and form ids
the way the C-file pipeline writes them), so the builder, the face note and `verify` compare like
with like. Each recorded fact gets an id (F1, F2, ...); a correction names the id it replaces.

`build` assembles the fact table into the existing `CfileFacts` (which the face-note template and
the conflict check read) plus a cite map beside it: CfileFacts path -> the fact it came from
("decisions.0" -> F7, "decisions.0.notified" -> F8). Linked facts: a discharge names the start
of its service period, a notification letter the date of its decision. The firm's own 21-22a is
recorded like any appointment form but is not a prior representative (`is_firm`).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from agent.cfile.extract import _branch, _form_id, _iso, _outcome, _pct, _ym
from agent.cfile.facts import CfileFacts, Decision, Issue, PendingFiling, PriorRep
from agent.cfile.reconcile import is_firm
from agent.intake.conditions import normalize_condition
from agent.intake.schema import Component, Discharge, RatedCondition, ServicePeriod


class Cite(BaseModel):
    doc_id: str = Field(description="the document id from pull_cfile / list_docs, e.g. D3")
    page: int = Field(ge=1, description="the global C-file page number the value is on")

    def __str__(self) -> str:
        return f"p. {self.page}"


def _date(v: Any) -> Any:
    return (_iso(v) or v) if isinstance(v, str) else v


def _month(v: Any) -> Any:
    return (_ym(v) or v) if isinstance(v, str) else v


class _Fact(BaseModel):
    id: str | None = Field(None, description="leave empty for a new fact; to correct one, the id it replaces (F3)")
    cite: Cite


class DobFact(_Fact):
    kind: Literal["dob"]
    dob: str = Field(description="date of birth (DD-214), YYYY-MM-DD")
    norm_dates = field_validator("dob", mode="before")(_date)


class ServicePeriodFact(_Fact):
    kind: Literal["service_period"]
    branch: str
    component: Component = "active"
    start: str = Field(description="YYYY-MM")
    end: str | None = Field(None, description="YYYY-MM")
    norm_months = field_validator("start", "end", mode="before")(_month)

    @field_validator("branch", mode="before")
    @classmethod
    def _norm_branch(cls, v: Any) -> Any:
        return _branch(v) or v if isinstance(v, str) else v


class DischargeFact(_Fact):
    kind: Literal["discharge"]
    period_start: str = Field(description="the start (YYYY-MM) of the service period it belongs to")
    character: Discharge
    norm_months = field_validator("period_start", mode="before")(_month)


class MosFact(_Fact):
    kind: Literal["mos"]
    mos: str = Field(min_length=1)


class RatedConditionFact(_Fact):
    kind: Literal["rated_condition"]
    condition: str
    pct: int = Field(ge=0, le=100)
    norm_cond = field_validator("condition", mode="after")(lambda v: normalize_condition(v))


class CombinedRatingFact(_Fact):
    kind: Literal["combined_rating"]
    pct: int = Field(ge=0, le=100, description="the combined evaluation on the most recent code sheet")


class DecisionFact(_Fact):
    kind: Literal["decision"]
    date: str = Field(description="the rating decision's date, YYYY-MM-DD")
    issues: list[Issue] = Field(min_length=1, description="each condition decided: outcome, and % if granted")
    form: str | None = Field(None, description="the filing form in the evidence list, e.g. 526EZ")
    filed: str | None = Field(None, description="the date that form was received, YYYY-MM-DD")
    norm_dates = field_validator("date", "filed", mode="before")(_date)
    norm_form = field_validator("form", mode="before")(_form_id)

    @field_validator("issues", mode="before")
    @classmethod
    def _outcomes(cls, v: Any) -> Any:  # "Granted", "70%" as documents write them
        if not isinstance(v, list):
            return v
        return [{**i, "outcome": _outcome(i.get("outcome")), "pct": _pct(i.get("pct"))} if isinstance(i, dict) else i
                for i in v]  # fmt: skip

    @field_validator("issues", mode="after")
    @classmethod
    def _conds(cls, v: list[Issue]) -> list[Issue]:
        return [i.model_copy(update={"condition": normalize_condition(i.condition)}) for i in v]


class NotificationLetterFact(_Fact):
    kind: Literal["notification_letter"]
    date: str = Field(description="the letter's own date, YYYY-MM-DD (appeal deadlines run from it)")
    decision_date: str = Field(description="the date of the rating decision it is about")
    norm_dates = field_validator("date", "decision_date", mode="before")(_date)


class PriorRepFact(_Fact):
    kind: Literal["prior_representative"]
    name: str = Field(min_length=2)
    rep_type: Literal["attorney", "agent", "vso"]
    signed: str | None = Field(None, description="date signed, YYYY-MM-DD")
    revoked: str | None = Field(None, description="the revocation date, if the form has revocation details")
    norm_dates = field_validator("signed", "revoked", mode="before")(_date)


class PendingFilingFact(_Fact):
    kind: Literal["pending_filing"]
    form: str
    filed: str = Field(description="date received, YYYY-MM-DD")
    conditions: list[str] = Field(default_factory=list)
    norm_dates = field_validator("filed", mode="before")(_date)
    norm_form = field_validator("form", mode="before")(_form_id)
    norm_conds = field_validator("conditions", mode="after")(lambda v: [normalize_condition(c) for c in v])


Fact = Annotated[
    DobFact | ServicePeriodFact | DischargeFact | MosFact | RatedConditionFact | CombinedRatingFact
    | DecisionFact | NotificationLetterFact | PriorRepFact | PendingFilingFact,
    Field(discriminator="kind"),
]  # fmt: skip
FACT = TypeAdapter(Fact)


def load(table: list[dict]) -> list[Fact]:
    return [FACT.validate_python(f) for f in table]


def summary(f: Fact) -> str:
    """One line for the model: the fact's values without the bookkeeping."""
    values = f.model_dump(exclude={"id", "kind", "cite"}, exclude_none=True)
    return f"{f.id} {f.kind} {values} ({f.cite})"


def build(table: list[Fact], firm: dict[str, Any]) -> tuple[CfileFacts, dict[str, Fact]]:
    """The fact table -> (CfileFacts, cite map). Later facts of the same thing win (a period by
    its start, a condition by name, a decision by date); lists keep the C-file's order."""
    by: dict[str, list[Fact]] = {}
    for f in table:
        by.setdefault(f.kind, []).append(f)
    out, cites = CfileFacts(), {}

    if by.get("dob"):
        out.dob, cites["dob"] = by["dob"][-1].dob, by["dob"][-1]
    periods = sorted({f.start: f for f in by.get("service_period", [])}.values(), key=lambda f: f.start)
    discharges = {f.period_start: f for f in by.get("discharge", [])}
    for i, f in enumerate(periods):
        d = discharges.get(f.start)
        out.service_periods.append(ServicePeriod(branch=f.branch, component=f.component, start=f.start, end=f.end,
                                                 discharge=d.character if d else None))  # fmt: skip
        cites[f"service_periods.{i}"] = f
        if d:
            cites[f"service_periods.{i}.discharge"] = d
    for i, f in enumerate({f.mos: f for f in by.get("mos", [])}.values()):
        out.mos.append(f.mos)
        cites[f"mos.{i}"] = f
    if by.get("combined_rating"):
        out.combined_rating, cites["combined_rating"] = by["combined_rating"][-1].pct, by["combined_rating"][-1]
    for i, f in enumerate({f.condition: f for f in by.get("rated_condition", [])}.values()):
        out.sc_conditions.append(RatedCondition(name=f.condition, rating_pct=f.pct))
        cites[f"sc_conditions.{i}"] = f
    letters = {f.decision_date: f for f in by.get("notification_letter", [])}
    decisions = sorted({f.date: f for f in by.get("decision", [])}.values(), key=lambda f: f.date)
    for i, f in enumerate(decisions):
        letter = letters.get(f.date)
        out.decisions.append(Decision(decision_date=f.date, notified=letter.date if letter else None,
                                      form=f.form, filed=f.filed, issues=f.issues))  # fmt: skip
        cites[f"decisions.{i}"] = f
        if letter:
            cites[f"decisions.{i}.notified"] = letter
    reps = [f for f in by.get("prior_representative", []) if not is_firm(f.name, firm)]
    for i, f in enumerate(reps):
        out.prior_reps.append(PriorRep(name=f.name, kind=f.rep_type, signed=f.signed, revoked=f.revoked))
        cites[f"prior_reps.{i}"] = f
    for i, f in enumerate(by.get("pending_filing", [])):
        out.pending_filings.append(PendingFiling(form=f.form, filed=f.filed, conditions=f.conditions))
        cites[f"pending_filings.{i}"] = f
    return out, cites


def unlinked(table: list[Fact]) -> list[str]:
    """Facts that link to nothing recorded: they can't reach the face note."""
    starts = {f.start for f in table if f.kind == "service_period"}
    dates = {f.date for f in table if f.kind == "decision"}
    out = [f"{f.id}: no service period starts {f.period_start}" for f in table
           if f.kind == "discharge" and f.period_start not in starts]  # fmt: skip
    out += [f"{f.id}: no decision dated {f.decision_date}" for f in table
            if f.kind == "notification_letter" and f.decision_date not in dates]  # fmt: skip
    return out
