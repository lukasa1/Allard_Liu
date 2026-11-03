"""The intake record: everything the intake subagent collects, as structured data.

This is the contract between the intake subagent and the rest of the system (the orchestrator,
claims prep, the face note). Fields map to the firm's 36-question intake form; see
data/questions.yaml for the question behind each field. The case file keeps each answer with its
source (agent/casefile.Answer); checklist.record rebuilds this record from those answers.
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

    # What claims prep found in the C-file that differs from this record (plain words), and the
    # veteran's answer when pass 2 asked about it.
    cfile_discrepancies: list[str] = Field(default_factory=list)
    cfile_discrepancy_answer: str | None = None

