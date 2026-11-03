"""Stub Lighthouse responses, built from a synthetic persona in VA's real response shapes.

The shapes follow the OpenAPI specs saved from developer.va.gov (Veteran Service History and
Eligibility v2, Benefits Claims v1); field names and enums are VA's. Values come from the
persona's ground truth, changed by its `va:` overrides (for example `omit_periods: [1]` drops a
Reserve period VA's data doesn't list, `wrong_discharge: {0: general}` misstates a discharge), so the
eval can test what happens when records are incomplete or wrong.
"""

from __future__ import annotations

import hashlib
from typing import Any

from agent.personas import Persona

BRANCH_TO_VA = {
    "army": "Army",
    "navy": "Navy",
    "air force": "Air Force",
    "marine corps": "Marine Corps",
    "coast guard": "Coast Guard",
    "space force": "Space Force",
}
DISCHARGE_TO_VA = {
    "honorable": "honorable",
    "general": "general",
    "oth": "other-than-honorable",
    "bad_conduct": "bad-conduct",
    "dishonorable": "dishonorable",
    "uncharacterized": "uncharacterized",
    None: "unknown",
}
COMPONENT_TO_SERVICE_TYPE = {
    "active": "Active Duty",
    "reserve": "Reserve",
    "guard": "National Guard",
}


def _uuid(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _month_start(ym: str | None) -> str | None:
    return f"{ym}-01" if ym else None


def _month_end(ym: str | None) -> str | None:
    if not ym:
        return None
    year, month = (int(x) for x in ym.split("-"))
    days = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30,
            31, 31, 30, 31, 30, 31][month - 1]  # fmt: skip
    return f"{ym}-{days:02d}"


def veteran_status(p: Persona) -> dict[str, Any]:
    status = p.va.get("status") or ("confirmed" if p.truth.is_veteran else "not_confirmed")
    attrs: dict[str, Any] = {"veteran_status": status}
    if status != "confirmed":
        attrs["not_confirmed_reason"] = p.va.get("not_confirmed_reason", "PERSON_NOT_FOUND")
    return {"data": {"id": p.icn, "type": "veteran_status_confirmations", "attributes": attrs}}


def service_history(p: Persona) -> dict[str, Any]:
    omit = set(p.va.get("omit_periods", []))
    # VA's data can also be wrong, not just incomplete: {index: discharge} replaces a discharge.
    wrong_discharge = {int(k): v for k, v in (p.va.get("wrong_discharge") or {}).items()}
    episodes = []
    if p.truth.is_veteran:
        for i, sp in enumerate(p.truth.service_periods):
            if i in omit:
                continue
            branch = BRANCH_TO_VA.get(sp.branch or "", (sp.branch or "").title())
            episodes.append({
                "id": _uuid(p.id, "episode", str(i)),
                "type": "service-history-episodes",
                "attributes": {
                    "first_name": p.truth.first_name,
                    "last_name": p.truth.last_name,
                    "branch_of_service": branch,
                    "service_type": COMPONENT_TO_SERVICE_TYPE.get(sp.component or "active", "Active Duty"),
                    "start_date": _month_start(sp.start),
                    "end_date": _month_end(sp.end),
                    "pay_grade": "E05",
                    "component_of_service": branch,
                    "discharge_status": DISCHARGE_TO_VA.get(wrong_discharge.get(i, sp.discharge), "unknown"),
                    "separation_reason": "COMPLETION OF REQUIRED ACTIVE SERVICE",
                    "service_episode_combat_pay": False,
                    "deployments": [],
                },
            })  # fmt: skip
    return {"data": episodes}


def disability_rating(p: Persona) -> dict[str, Any]:
    t = p.truth
    ratings = [
        {
            "decision": "Service Connected",
            "disability_rating_id": str(1070000 + i),
            "effective_date": None,
            "rating_end_date": None,
            "rating_percentage": c.rating_pct,
            "diagnostic_type_code": "",
            "hyph_diagnostic_type_code": "",
            "diagnostic_type_name": c.name,
            "diagnostic_text": c.name,
            "static_ind": False,
        }
        for i, c in enumerate(t.sc_conditions)
    ]
    combined = t.rating_pct if t.receiving_va_pay else (0 if t.filed_before else None)
    return {
        "data": {
            "id": p.icn[-5:],
            "type": "disability-rating",
            "attributes": {
                "combined_disability_rating": combined,
                "combined_effective_date": None,
                "legal_effective_date": None,
                "individual_ratings": ratings,
            },
        }
    }


def permanent_and_total(p: Persona) -> dict[str, Any]:
    return {
        "data": {
            "permanent_and_total": {
                "service_connected_status": False,
                "pension_award_status": False,
            },
            "total_disability": {"status": bool(p.truth.tdiu), "effective_date": None},
        }
    }


def claims(p: Persona) -> dict[str, Any]:
    """Benefits Claims v1 GET /claims: one completed claim per decision on file."""
    items = []
    if p.truth.filed_before:
        decisions = p.cfile.get("decisions") or [{"filed": None}]
        for i, d in enumerate(decisions):
            claim_id = (
                600300000 + int(hashlib.sha256(f"{p.id}{i}".encode()).hexdigest(), 16) % 99999
            )
            items.append({
                "id": str(claim_id),
                "type": "evss_claims",
                "attributes": {
                    "evss_id": claim_id,
                    "open": False,
                    "waiver_submitted": False,
                    "requested_decision": False,
                    "claim_type": "Compensation",
                    "date_filed": d.get("filed"),
                    "min_est_date": None,
                    "max_est_date": None,
                    "development_letter_sent": False,
                    "decision_letter_sent": True,
                    "documents_needed": False,
                    "status": "Complete",
                },
            })  # fmt: skip
    return {"data": items}


def active_poa(p: Persona) -> dict[str, Any] | None:
    """Benefits Claims v1 GET /forms/2122/active. None means VA has no POA on file (404)."""
    override = p.va.get("active_poa")
    if override == "none" or (override is None and not p.truth.prior_attorney):
        return None
    if isinstance(override, dict):
        rep = override
    else:
        first, _, last = (p.truth.prior_attorney_name or "Prior Attorney").partition(" ")
        rep = {"first_name": first, "last_name": last, "organization_name": None}
    return {
        "data": {
            "id": None,
            "type": "claims_api_power_of_attorneys",
            "attributes": {
                "status": "updated",
                "date_request_accepted": None,
                "representative": {
                    "service_organization": {
                        "first_name": rep.get("first_name"),
                        "last_name": rep.get("last_name"),
                        "organization_name": rep.get("organization_name"),
                        "phone_number": "555-555-0199",
                        "poa_code": rep.get("poa_code", "A1Q"),
                    }
                },
                "previous_poa": None,
            },
        }
    }
