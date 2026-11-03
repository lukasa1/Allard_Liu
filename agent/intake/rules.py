"""The firm's intake rules, as plain deterministic code.

These decisions must be identical every time and explainable: who to stop with, the fee
percentage, and the flags case prep needs. Each rule is labelled with its basis:

  law          follows from VA law (38 USC / 38 CFR)
  firm_policy  the firm's own choice (as described to the team by the firm)

The LLM never makes these calls; it only extracts the facts they run on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import NON_HONORABLE, IntakeRecord, Outcome


@dataclass(frozen=True)
class Rule:
    id: str
    basis: str  # law | firm_policy
    text: str


RULES: dict[str, Rule] = {
    r.id: r
    for r in [
        Rule("not_veteran", "firm_policy", "The firm represents veterans only."),
        Rule(
            "rated_100",
            "firm_policy",
            "Already rated 100%: no increase to pursue. Not a legal bar to representation; past-due "
            "benefits (and so a contingency fee) would be small or zero.",
        ),
        Rule(
            "all_periods_non_honorable",
            "firm_policy",
            "Every service period is other than honorable, bad conduct or dishonorable: an attorney "
            "decides. Legally most of these need a VA character-of-discharge determination "
            "(38 CFR 3.12), so this is a review, not a rejection.",
        ),
        Rule(
            "non_honorable_period",
            "firm_policy",
            "Any service period other than honorable, bad conduct or dishonorable: an attorney "
            "decides whether the firm takes the case (plan A1). Legally most of these need a VA "
            "character-of-discharge determination (38 CFR 3.12), so this is a review, not a rejection.",
        ),
        Rule(
            "fee_pct",
            "firm_policy",
            "PLACEHOLDER, unconfirmed by the firm: 30% standard; 20% when a prior private attorney "
            "or agent represented the veteran. VA withholds at most 20% (38 CFR 14.636(h)); above "
            "that the client pays the firm directly.",
        ),
        Rule(
            "no_fee_before_decision",
            "law",
            "An attorney may charge only for work after VA's notice of the initial decision "
            "(38 USC 5904(c)(1)).",
        ),
    ]
}


def early_stop(record: IntakeRecord, answered: set[str]) -> Outcome | None:
    """A decision that ends intake before every question is asked, or None to keep going."""
    if record.is_veteran is False:
        return Outcome(decision="not_veteran", reasons=[RULES["not_veteran"].text])
    if record.rating_pct == 100:
        return Outcome(decision="rated_100", reasons=[RULES["rated_100"].text])
    service_known = "service_periods" in answered and "other_service_periods" in answered
    periods = record.service_periods
    if service_known and periods and all(p.discharge in NON_HONORABLE for p in periods):
        return Outcome(
            decision="attorney_review", reasons=[RULES["all_periods_non_honorable"].text]
        )
    return None


def fee_pct(record: IntakeRecord) -> int:
    """The fee % offered to a new client. A PLACEHOLDER for firm policy: the firm's SOP only says
    how to read the % off an existing C-file, not how the firm chooses it for a new client (plan
    Q1, unconfirmed). Nothing else may rely on the "prior attorney -> 20%" rule."""
    return 20 if record.prior_attorney else 30


def flags(record: IntakeRecord) -> list[str]:
    out: list[str] = []
    bad = [p for p in record.service_periods if p.discharge in NON_HONORABLE]
    if bad and len(bad) < len(record.service_periods):
        out.append("non_honorable_period")  # mark it on the face note; no withdrawal needed
    if any(p.discharge is None for p in record.service_periods):
        out.append("discharge_unknown")
    if len(record.service_periods) > 1:
        out.append("multiple_service_periods")  # expect more than one DD-214
    if record.filed_before:
        out.append("prior_va_claim")  # the C-file will hold earlier decisions
    if record.filed_before is None and record.is_veteran:
        out.append("claim_history_unknown")  # ratings / prior-claim screens were skipped
    if record.filed_before is False:
        out.append("no_decision_yet")  # law: no fee until VA's first decision on a claim
    if record.dic_claim:
        out.append("dic_claim")
    if record.ssa_interest:
        out.append("refer_social_security")
    if record.exposures and record.litigation_contact:
        out.append("refer_exposure_litigation")
    if record.earning_over_1600 is False and not record.tdiu:
        out.append("possible_tdiu")
    if record.questions_for_team:
        out.append("veteran_questions_pending")
    return out


# Collected in chat or through the POA skill's secure form before intake can call itself complete.
REQUIRED_FIELDS = ("first_name", "last_name", "service_periods", "claim_conditions")


def final_outcome(record: IntakeRecord, stopped: Outcome | None, escalation: str | None) -> Outcome:
    if escalation:
        return Outcome(decision="escalated", reasons=[escalation], flags=flags(record))
    if stopped is not None:
        return stopped.model_copy(update={"flags": flags(record)})
    missing = [f for f in REQUIRED_FIELDS if not getattr(record, f)]
    if missing:
        return Outcome(
            decision="incomplete", reasons=[f"missing: {', '.join(missing)}"], flags=flags(record)
        )
    return Outcome(decision="eligible", fee_pct=fee_pct(record), flags=flags(record))
