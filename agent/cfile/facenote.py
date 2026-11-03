"""Render the firm's face-note template from CfileFacts (deterministic: no LLM).

Template and rules follow the firm's face-note format, simplified:
  - header: fee % and prior private rep, DOB, service era, branch/dates/discharge per period,
    MOS, combined rating at signing, the SC list (highest first), the firm's intent-to-file date
  - numbered lines: decisions whose notification letter is under a year old, newest first, with
    the filing form, the decision date (dated by the notification letter, since deadlines run
    from it) and the AMA appeal deadline (one year later); filings with no decision yet get
    their own line
  - OLD CLAIMS: conditions whose latest decision is more than a year old, one per line
Not covered yet: following conditions back through older decisions on the same line, Board
appeals, deferrals and proposed reductions on their own lines.

Flags for staff (not part of the firm's template, listed under the note):
  - DOB on the intake / 21-22a differs from the DD-214 (the "swapped day and month" case)
  - a period with a non-honorable discharge
  - documents the extractor could not read, or read without their key facts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from agent.cfile.facts import CfileFacts, Decision

THIN = "-" * 44
THICK = "=" * 44
WAVE = "~" * 30
NON_HONORABLE = {"oth", "bad_conduct", "dishonorable"}
DISCHARGE_LABEL = {
    "honorable": "Honorable",
    "general": "General",
    "oth": "Other than honorable",
    "bad_conduct": "Bad conduct",
    "dishonorable": "Dishonorable",
    "uncharacterized": "Uncharacterized",
}


ACRONYMS = {
    "ptsd": "PTSD",
    "gerd": "GERD",
    "tbi": "TBI",
    "mst": "MST",
    "copd": "COPD",
    "ibs": "IBS",
}


def cond_name(name: str) -> str:
    """Display form of a condition: "ptsd" -> "PTSD", "left knee condition" -> "Left knee condition"."""
    words = [ACRONYMS.get(w, w) for w in name.split()]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def _short(iso: str | None) -> str:
    if not iso:
        return "(unknown)"
    d = date.fromisoformat(iso)
    return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"


def _ym(ym: str | None) -> str:
    return f"{ym[5:7]}/{ym[2:4]}" if ym else "?"


def _plus_year(iso: str) -> str:
    d = date.fromisoformat(iso)
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:  # Feb 29
        return (d + timedelta(days=365)).isoformat()


def service_era(start: str | None) -> str:
    if not start:
        return "(unknown)"
    ym = start[:7]
    if ym >= "1990-08":
        return "Gulf War"
    if ym >= "1975-05":
        return "Peacetime (post-Vietnam)"
    if ym >= "1961-11":
        return "Vietnam Era"
    return "Pre-Vietnam"


@dataclass
class FaceNote:
    text: str
    flags: list[str] = field(default_factory=list)
    deadlines: list[dict] = field(default_factory=list)  # {deadline, decision_date, conditions}


def render(
    facts: CfileFacts,
    *,
    fee_pct: int | None,
    itf_date: str | None,
    intake_dob: str | None,
    firm: str = "Law Firm",
    as_of: date | None = None,
) -> FaceNote:
    as_of = as_of or date.today()
    today = as_of.isoformat()
    flags: list[str] = []

    def is_current(d: Decision) -> bool:
        # Calendar year, the same rule as the deadline itself: 365 days loses a day across Feb 29
        # and sends a decision whose deadline is today to OLD CLAIMS with no deadline task.
        return _plus_year(dated(d)) >= today

    private = [r for r in facts.prior_reps if r.kind in ("attorney", "agent")]
    # Newest by signed date; on a tie (or no dates) the last in document order, as before.
    newest = max(reversed(private), key=lambda r: r.signed or "") if private else None
    prior = f"Prior rep {newest.name}" if newest else "No prior rep"
    lines = [f"FA {fee_pct if fee_pct is not None else '?'}%; {prior}", "*" * 44]

    lines.append(f"DOB: {_short(facts.dob)}")
    if intake_dob and facts.dob and intake_dob != facts.dob:
        # No dates in the flag: flags reach staff tasks, the case file and the orchestrator's prompt.
        swapped = intake_dob[:4] == facts.dob[:4] and intake_dob[5:7] == facts.dob[8:10] and intake_dob[8:10] == facts.dob[5:7]
        how = " (the day and month look swapped)" if swapped else ""
        flags.append(f"DOB mismatch: the intake / 21-22a date of birth differs from the DD-214{how}. File a corrected 21-22a.")
    first = facts.service_periods[0].start if facts.service_periods else None
    lines.append(f"Service Era: {service_era(first)}")
    for sp in facts.service_periods:
        discharge = DISCHARGE_LABEL.get(sp.discharge or "", "Discharge unknown")
        comp = "" if sp.component in (None, "active") else f" {sp.component.title()}"
        line = f"{(sp.branch or '?').title()}{comp} {_ym(sp.start)} - {_ym(sp.end)}, {discharge}"
        if sp.discharge in NON_HONORABLE:
            line += "  ** FLAG: non-qualifying discharge for this period **"
            flags.append(f"Non-honorable discharge for the {sp.start} to {sp.end} period.")
        lines.append(line)
    lines.append(f"MOS: {'; '.join(facts.mos) if facts.mos else '(not found)'}")
    combined = facts.combined_rating if facts.combined_rating is not None else 0
    lines.append(f"SC at time of signing {firm} - {combined}%")
    lines.append(THICK)
    sc = sorted(facts.sc_conditions, key=lambda c: -(c.rating_pct or 0))
    lines.append(
        f"SC ({combined}%)|"
        + "".join(f" {cond_name(c.name)} {c.rating_pct}% |" for c in sc).rstrip("|").rstrip()
    )
    lines.append(THICK)
    lines.append(
        f"{firm} Filed 0966 Intent on {_short(itf_date) if itf_date else '(not filed yet)'}"
    )
    lines.append(THIN)

    def dated(d: Decision) -> str:
        return d.notified or d.decision_date

    current = sorted((d for d in facts.decisions if is_current(d)), key=dated, reverse=True)
    deadlines = []
    n = 0
    for d in current:
        n += 1
        conds = "; ".join(cond_name(i.condition) for i in d.issues)
        deadline = _plus_year(dated(d))
        block = [f"{n}. {cond_name(conds)}"]
        if d.form:
            block.append(f"   {d.form} filed {_short(d.filed)}")
        block += [
            f"   R.D. {_short(dated(d))}",
            f"   DEADLINE TO FILE AMA APPEAL {_short(deadline)}",
        ]
        lines += block + [THIN]
        deadlines.append(
            {
                "deadline": deadline,
                "decision_date": dated(d),
                "conditions": [i.condition for i in d.issues],
            }
        )
    for pf in facts.pending_filings:
        n += 1
        lines += [
            f"{n}. {'; '.join(cond_name(c) for c in pf.conditions)}: pending",
            f"   {pf.form} filed {_short(pf.filed)}",
            THIN,
        ]

    latest: dict[str, Decision] = {}
    for d in sorted(facts.decisions, key=dated):
        for issue in d.issues:
            latest[issue.condition] = d
    old = [(c, d) for c, d in latest.items() if not is_current(d)]
    if old:
        lines += [WAVE, "OLD CLAIMS", WAVE]
        for i, (cond, d) in enumerate(sorted(old, key=lambda cd: dated(cd[1]), reverse=True), 1):
            lines += [f"{i}. {cond_name(cond)} R.D. {_short(dated(d))}", WAVE]
    flags += facts.problems
    return FaceNote(text="\n".join(lines), flags=flags, deadlines=deadlines)
