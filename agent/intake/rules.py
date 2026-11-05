"""The firm's intake rules, as plain deterministic code.

These decisions must be identical every time and explainable: who to stop with and the fee
percentage. agent/intake/checklist.stop_rule applies them. Each rule is labelled with its basis:

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
            "Every service period ended other than honorable (OTH), with a bad conduct discharge or "
            "with a dishonorable discharge: an attorney decides whether the firm takes the case. When "
            "only some periods did, intake goes on and a staff task names those periods for the "
            "attorney. General (under honorable conditions) and uncharacterized "
            "discharges are neither. Legally most of these need a VA character-of-discharge "
            "determination (38 CFR 3.12), so this is a review, not a rejection.",
        ),
        Rule(
            "screen_unresolved",
            "firm_policy",
            "The veteran couldn't say whether they served, their service periods, their VA pay or "
            "rating, or whether a lawyer helped before: the stop rules above or the fee can't be "
            "decided, so a person on the team follows up.",
        ),
        Rule(
            "fee_pct",
            "firm_policy",
            "30% standard; 20% when a prior private attorney or agent represented the veteran (a "
            "VSO doesn't count). VA withholds at most 20% (38 CFR 14.636(h)); above "
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
    """The fee % offered to a new client: 20% if a private attorney or agent represented them
    before (a VSO doesn't count), else 30% (the firm's rule)."""
    return 20 if record.prior_attorney else 30

