"""The intake record: everything the intake subagent collects, as structured data.

This is the contract between the intake subagent and the rest of the system (the orchestrator,
case prep, the face-note pipeline). Fields map to the firm's 36-question intake form; see
data/questions.yaml for the question behind each field. `provenance` says where each answer came
from: the veteran in chat, VA's records (Lighthouse), the POA skill's secure form, or the C-file
(read by claims prep before intake pass 2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Discharge = Literal["honorable", "general", "oth", "bad_conduct", "dishonorable", "uncharacterized"]
Component = Literal["active", "reserve", "guard"]

# Discharges that need attorney review before the firm takes the case (firm policy; legally most
# of these need a VA character-of-discharge determination, not an automatic bar: 38 CFR 3.12).
NON_HONORABLE: frozenset[str] = frozenset({"oth", "bad_conduct", "dishonorable"})


class ServicePeriod(BaseModel):
    branch: str | None = None  # army | navy | air force | marine corps | coast guard | space force
    component: Component | None = None
    start: str | None = None  # YYYY-MM
    end: str | None = None  # YYYY-MM
    discharge: Discharge | None = None


class RatedCondition(BaseModel):
    name: str
    rating_pct: int | None = None


class IntakeRecord(BaseModel):
    # Screening and identity
    is_veteran: bool | None = None
    first_name: str | None = None
    last_name: str | None = None
    service_periods: list[ServicePeriod] = Field(default_factory=list)

    # Claim history
    filed_before: bool | None = None
    receiving_va_pay: bool | None = None
    rating_pct: int | None = None
    tdiu: bool | None = None
    sc_conditions: list[RatedCondition] = Field(default_factory=list)

    # Contact
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    cell_phone: str | None = None
    email: str | None = None

    # Representation and benefits screens
    prior_attorney: bool | None = None
    prior_attorney_name: str | None = None
    dic_claim: bool | None = None
    earning_over_1600: bool | None = None
    receives_ssa: bool | None = None
    ssa_interest: bool | None = None
    partner_share_consent: bool | None = None

    # Service details
    mos: list[str] = Field(default_factory=list)
    retired: bool | None = None
    exposures: list[str] = Field(default_factory=list)
    litigation_contact: bool | None = None

    # Conditions
    claim_conditions: list[str] = Field(default_factory=list)
    other_conditions: list[str] = Field(default_factory=list)

    # Family
    marital_status: Literal["single", "married", "divorced", "separated", "widowed"] | None = None
    spouse_name: str | None = None
    children_under_18: bool | None = None
    next_of_kin: str | None = None

    # Marketing
    heard_about: str | None = None
    internet_source: str | None = None

    # Narrative answers: condition -> prompt id (h01..h16) -> the veteran's answer
    narratives: dict[str, dict[str, str]] = Field(default_factory=dict)
    narrative_summaries: dict[str, str] = Field(default_factory=dict)

    # Questions the veteran asked that a person on the team should answer
    questions_for_team: list[str] = Field(default_factory=list)
    # Questions the QA tool answered during intake: {question, answer, sources}
    qa_log: list[dict] = Field(default_factory=list)

    # What claims prep found in the C-file that differs from this record (plain words), and the
    # veteran's answer when pass 2 asked about it (cfile_mode confirm).
    cfile_discrepancies: list[str] = Field(default_factory=list)
    cfile_discrepancy_answer: str | None = None

    # field name -> where the value came from: chat | va_records | secure_form | cfile
    provenance: dict[str, str] = Field(default_factory=dict)


DecisionKind = Literal[
    "eligible",  # everything collected; the case moves on to case prep
    "not_veteran",  # stop: the firm only represents veterans
    "rated_100",  # stop: already at 100%, nothing to increase
    "attorney_review",  # stop collecting; an attorney decides (e.g. only non-honorable service)
    "escalated",  # a person must take over now (crisis, refusal, veteran asked for a human)
    "incomplete",  # the conversation ended before the required fields were collected
]


class Outcome(BaseModel):
    decision: DecisionKind
    reasons: list[str] = Field(default_factory=list)
    # Firm policy: 30% standard, 20% when a prior private attorney or agent represented the veteran.
    # VA withholds at most 20% from past-due benefits (38 CFR 14.636(h)); at 30% the firm collects
    # the other 10% from the client directly.
    fee_pct: int | None = None
    flags: list[str] = Field(default_factory=list)
