"""Claims prep's bridge to intake pass 2: what the C-file settles, and where it disagrees.

After the C-file is read (facts with their documents), claims prep
  1. pre-fills the pass-2 questions the C-file answers (`cfile_intake_values`), and
  2. compares the C-file with what intake already holds (`reconcile`). Each disagreement becomes
     a staff review task, and with cfile_mode fetch/confirm the C-file's version is applied
     (a forgotten service period is added, a forgotten claim or representative is recorded);
     with confirm, pass 2 also asks the veteran about it.

The DOB is compared by the face note itself (it shows the DOB) and isn't repeated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent.cfile.facts import CfileFacts
from agent.intake.schema import IntakeRecord, ServicePeriod
from agent.lighthouse.records import describe_period


@dataclass
class Discrepancy:
    kind: str  # service_period | discharge | prior_claim | prior_representative | rating
    text: str  # plain words, shown to the veteran (confirm mode) and to staff
    applies: bool  # the C-file's version is written to the record in fetch/confirm modes


_DISCHARGE = {"oth": "other than honorable", "bad_conduct": "bad conduct"}


def _article(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' or word.startswith('hon') else 'a'} {word}"


def newest_private_rep(facts: CfileFacts):
    """The most recent private attorney or agent: newest by signed date, ties by document order
    (the same rule as the face note's header)."""
    private = [r for r in facts.prior_reps if r.kind in ("attorney", "agent")]
    return max(reversed(private), key=lambda r: r.signed or "") if private else None


def without_firm(facts: CfileFacts, rep: dict[str, Any]) -> CfileFacts:
    """The C-file is pulled after the firm's own 21-22a is filed, so it may list the firm itself:
    that is not a *prior* representative (it would lower the fee and the face note's header)."""
    ours = {n.lower() for n in (rep.get("firm_name"), f"{rep.get('first_name', '')} {rep.get('last_name', '')}".strip()) if n}
    keep = [r for r in facts.prior_reps if not any(o and o in r.name.lower() for o in ours)]
    return facts.model_copy(update={"prior_reps": keep})


def _year(ym: str | None) -> int | None:
    m = re.search(r"(19|20)\d{2}", ym or "")
    return int(m.group(0)) if m else None


def cfile_intake_values(facts: CfileFacts) -> dict[str, Any]:
    """Intake fields (questions marked `cfile: true`) the C-file answers."""
    values: dict[str, Any] = {}
    if facts.sc_conditions:
        values["sc_conditions"] = [c.model_copy() for c in facts.sc_conditions]
    newest = newest_private_rep(facts)
    if newest:
        values["prior_attorney_name"] = newest.name
    if facts.mos:
        values["mos"] = list(facts.mos)
    return values


def _same_period(a: ServicePeriod, b: ServicePeriod) -> bool:
    """The same enlistment if the branch matches and it starts within a year (people round)."""
    if (a.branch or "").lower() != (b.branch or "").lower():
        return False
    ya, yb = _year(a.start), _year(b.start)
    if ya is None or yb is None:  # a free-text or missing date: can't tell them apart
        return True
    return abs(ya - yb) <= 1


def reconcile(record: IntakeRecord, facts: CfileFacts) -> list[Discrepancy]:
    out: list[Discrepancy] = []
    for p in facts.service_periods:
        match = next((q for q in record.service_periods if _same_period(p, q)), None)
        if match is None:
            out.append(Discrepancy("service_period", f"service not on your list ({describe_period(p)})", True))
        elif p.discharge and match.discharge and p.discharge != match.discharge:
            # The DD-214 is the authority on the character of discharge.
            out.append(Discrepancy(
                "discharge",
                f"{_article(_DISCHARGE.get(p.discharge, p.discharge))} discharge on the DD-214 for "
                f"{describe_period(p).split(' (')[0]} (we have {_DISCHARGE.get(match.discharge, match.discharge)})",
                True,
            ))  # fmt: skip
    if facts.decisions and record.filed_before is not True:
        first = min(d.decision_date for d in facts.decisions)
        out.append(Discrepancy("prior_claim", f"an earlier VA claim decision (dated {first})", True))
    newest = newest_private_rep(facts)
    if newest and record.prior_attorney is not True:
        out.append(Discrepancy("prior_representative", f"an earlier {newest.kind} on your claims ({newest.name})", True))
    if (
        record.rating_pct is not None
        and facts.combined_rating is not None
        and record.rating_pct != facts.combined_rating
    ):
        out.append(Discrepancy(
            "rating",
            f"a combined rating of {facts.combined_rating}% on the latest code sheet (we have {record.rating_pct}%)",
            False,  # the code sheet in the file may be older than the veteran's latest decision
        ))  # fmt: skip
    return out


def apply(record: IntakeRecord, facts: CfileFacts, found: list[Discrepancy]) -> list[str]:
    """Write the C-file's version for the discrepancies that apply. Returns the fields changed."""
    changed: list[str] = []
    kinds = {d.kind for d in found if d.applies}
    if "service_period" in kinds:
        for p in facts.service_periods:
            if not any(_same_period(p, q) for q in record.service_periods):
                record.service_periods.append(p.model_copy())
        record.provenance["service_periods"] = "cfile+" + record.provenance.get("service_periods", "chat")
        changed.append("service_periods")
    if "discharge" in kinds:
        for p in facts.service_periods:
            match = next((q for q in record.service_periods if _same_period(p, q)), None)
            if match is not None and p.discharge and match.discharge != p.discharge:
                match.discharge = p.discharge
        record.provenance["service_periods"] = "cfile+" + record.provenance.get("service_periods", "chat")
        if "service_periods" not in changed:
            changed.append("service_periods")
    if "prior_claim" in kinds:
        record.filed_before = True
        record.provenance["filed_before"] = "cfile"
        changed.append("filed_before")
    if "prior_representative" in kinds:
        record.prior_attorney = True
        record.prior_attorney_name = record.prior_attorney_name or newest_private_rep(facts).name
        record.provenance["prior_attorney"] = "cfile"
        record.provenance.setdefault("prior_attorney_name", "cfile")
        changed += ["prior_attorney", "prior_attorney_name"]
    return changed
