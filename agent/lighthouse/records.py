"""VA's records for one veteran, and how they map onto the intake record.

`VaRecords` keeps every Lighthouse response verbatim (for provenance and for the demo's "VA
records" panel); `intake_values()` turns them into intake fields. The mapping is deliberately
conservative: a field is only filled when the records actually settle it.

  is_veteran        VSHE /status "confirmed" -> True. "not_confirmed" (the spec's schema also
                    spells it "not confirmed") is NOT mapped to False
                    (it can mean MORE_RESEARCH_REQUIRED), so the question is asked in chat.
  service_periods   VSHE /service_history episodes (branch, component, dates, discharge)
  filed_before      Benefits Claims v1 /claims: any claim on file
  receiving_va_pay  VSHE /disability_rating: combined rating > 0 (only when a rating exists)
  rating_pct        combined rating; sc_conditions: individual "Service Connected" ratings
  tdiu              VSHE /permanent_and_total_disability total_disability.status
  prior_attorney    Benefits Claims v1 /forms/2122/active names an individual (no organization).
                    No active POA is NOT mapped to False: a revoked earlier POA wouldn't show, so
                    the question is still asked. A VSO (organization) doesn't count: VSOs can't
                    charge a fee.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from agent.intake.schema import RatedCondition, ServicePeriod

VA_TO_BRANCH = {
    "army": "army",
    "navy": "navy",
    "air force": "air force",
    "marine corps": "marine corps",
    "coast guard": "coast guard",
    "space force": "space force",
}
VA_TO_DISCHARGE = {
    "honorable": "honorable",
    "honorable-absence-of-negative-report": "honorable",
    "honorable-for-va-purposes": "honorable",
    "general": "general",
    "other-than-honorable": "oth",
    "bad-conduct": "bad_conduct",
    "dishonorable": "dishonorable",
    "dishonorable-for-va-purposes": "dishonorable",
    "uncharacterized": "uncharacterized",
}
SERVICE_TYPE_TO_COMPONENT = {
    "active duty": "active",
    "reserve": "reserve",
    "reserves": "reserve",
    "national guard": "guard",
    "guard": "guard",
}


class VaRecords(BaseModel):
    icn: str
    mode: str  # stub | recorded | sandbox
    fetched_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    veteran_status: dict[str, Any] | None = None
    service_history: dict[str, Any] | None = None
    disability_rating: dict[str, Any] | None = None
    permanent_and_total: dict[str, Any] | None = None
    claims: dict[str, Any] | None = None
    active_poa: dict[str, Any] | None = None
    errors: dict[str, str] = Field(default_factory=dict)  # endpoint -> error, when a call failed

    # ---------------------------------------------------------------- parsed views

    def confirmed_veteran(self) -> bool | None:
        if not self.veteran_status:
            return None
        status = self.veteran_status.get("data", {}).get("attributes", {}).get("veteran_status")
        return True if status == "confirmed" else None

    def service_periods(self) -> list[ServicePeriod] | None:
        if self.service_history is None:
            return None
        out = []
        for ep in self.service_history.get("data", []):
            a = ep.get("attributes", {})
            branch = VA_TO_BRANCH.get(str(a.get("branch_of_service", "")).lower())
            stype = str(a.get("service_type", "")).lower()
            out.append(
                ServicePeriod(
                    branch=branch,
                    component=SERVICE_TYPE_TO_COMPONENT.get(stype, "active"),
                    start=(a.get("start_date") or "")[:7] or None,
                    end=(a.get("end_date") or "")[:7] or None,
                    discharge=VA_TO_DISCHARGE.get(str(a.get("discharge_status", "")).lower()),
                )
            )
        return out

    def _rating_attrs(self) -> dict[str, Any] | None:
        if self.disability_rating is None:
            return None
        return self.disability_rating.get("data", {}).get("attributes", {})

    def combined_rating(self) -> int | None:
        attrs = self._rating_attrs()
        return None if attrs is None else attrs.get("combined_disability_rating")

    def sc_conditions(self) -> list[RatedCondition] | None:
        attrs = self._rating_attrs()
        if attrs is None:
            return None
        return [
            RatedCondition(
                name=str(r.get("diagnostic_text") or r.get("diagnostic_type_name") or "").lower(),
                rating_pct=r.get("rating_percentage"),
            )
            for r in attrs.get("individual_ratings", [])
            if r.get("decision") == "Service Connected"
        ]

    def tdiu(self) -> bool | None:
        if self.permanent_and_total is None:
            return None
        return bool(
            self.permanent_and_total.get("data", {}).get("total_disability", {}).get("status")
        )

    def claim_count(self) -> int | None:
        return None if self.claims is None else len(self.claims.get("data", []))

    def private_representative(self) -> str | None:
        """Name of an individual (attorney/agent) with an active POA, or None."""
        if not self.active_poa:
            return None
        rep = (
            self.active_poa.get("data", {})
            .get("attributes", {})
            .get("representative", {})
            .get("service_organization", {})
        )
        if rep.get("organization_name"):
            return None  # a VSO
        name = " ".join(x for x in (rep.get("first_name"), rep.get("last_name")) if x)
        return name or None

    # ---------------------------------------------------------------- intake mapping

    def intake_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if self.confirmed_veteran():
            values["is_veteran"] = True
        periods = self.service_periods()
        if periods:
            values["service_periods"] = periods
        count = self.claim_count()
        if count is not None:
            values["filed_before"] = count > 0
        combined = self.combined_rating()
        if combined is not None:  # no rating on file (never filed) settles nothing about pay
            values["receiving_va_pay"] = bool(combined)
            if combined:
                values["rating_pct"] = combined
                values["sc_conditions"] = self.sc_conditions() or []
                tdiu = self.tdiu()
                if tdiu is not None:
                    values["tdiu"] = tdiu
        rep = self.private_representative()
        if rep:
            values["prior_attorney"] = True
            values["prior_attorney_name"] = rep
        return values

    def service_text(self) -> str | None:
        periods = self.service_periods()
        if not periods:
            return None
        return "; ".join(describe_period(p) for p in periods)


def describe_period(p: ServicePeriod) -> str:
    component = {"active": "active duty", "reserve": "Reserve", "guard": "National Guard"}.get(
        p.component or "active", "active duty"
    )
    discharge = {"oth": "other than honorable", "bad_conduct": "bad conduct"}.get(
        p.discharge or "", p.discharge or "unknown discharge"
    )
    return (
        f"{(p.branch or 'unknown branch').title()} {component} {p.start} to {p.end} ({discharge})"
    )
