"""The firm's intake rules, as plain deterministic code.

These decisions must be identical every time and explainable: who to stop with and the fee
percentage. agent/intake/checklist.stop_rule applies them (A1). Each rule is labelled with its basis:

  law          follows from VA law (38 USC / 38 CFR)
  firm_policy  the firm's own choice (as described to the team by the firm)

The model never makes these calls; it only records the facts they run on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import IntakeRecord


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
            "non_honorable_period",
            "firm_policy",
            "Any service period other than honorable, bad conduct or dishonorable: an attorney "
            "decides whether the firm takes the case (plan A1). Legally most of these need a VA "
            "character-of-discharge determination (38 CFR 3.12), so this is a review, not a rejection.",
        ),
        Rule(
            "screen_unresolved",
            "firm_policy",
            "The veteran couldn't say whether they served, or their service periods: the stop "
            "rules above can't be decided, so a person on the team follows up (plan A1).",
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


def fee_pct(record: IntakeRecord) -> int:
    """The fee % offered to a new client. A PLACEHOLDER for firm policy: the firm's SOP only says
    how to read the % off an existing C-file, not how the firm chooses it for a new client (plan
    Q1, unconfirmed). Nothing else may rely on the "prior attorney -> 20%" rule."""
    return 20 if record.prior_attorney else 30

