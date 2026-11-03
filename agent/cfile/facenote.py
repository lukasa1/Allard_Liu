"""Render the firm's face-note template from CfileFacts (deterministic: no LLM).

Template and rules follow the firm's face-note format, simplified:
  - header: fee % and prior rep (none if the form has revocation details), DOB, service era, branch/dates/discharge per period,
    MOS, combined rating at signing, the SC list (highest first), the firm's intent-to-file date
  - numbered lines: decisions whose notification letter is under a year old, newest first, with
    the filing form, the decision date (dated by the notification letter, since deadlines run
    from it) and the AMA appeal deadline (one year later); filings with no decision yet get
    their own line
  - OLD CLAIMS: conditions whose latest decision is more than a year old, one per line
Not covered yet: following conditions back through older decisions on the same line, Board
appeals, deferrals and proposed reductions on their own lines.

Every line carries the fact paths it came from (`Line.sources`), so claims prep's `verify` can
check each line against the C-file pages its facts cite.

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


@dataclass(frozen=True)
class Line:
    """One face-note line and the fact paths it came from (L24). `sources` is None for a pure
    separator. A path names a CfileFacts field ("dob", "decisions.0", "decisions.0.notified"); a
    derived line (service era, an appeal deadline) lists the facts it was derived from. Two other
    kinds of source: "case:<field>" (the firm's own records: the fee agreement, the ITF) and
    "none:<doc type>:<fact kind>" (a line that states something is absent, e.g. no code sheet)."""

    text: str
    sources: tuple[str, ...] | None = ()


@dataclass
class FaceNote:
    lines: list[Line]
    flags: list[str] = field(default_factory=list)
    deadlines: list[dict] = field(default_factory=list)  # {deadline, decision_date, conditions}

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def _sep(text: str) -> Line:
    return Line(text, None)


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

    def dated(d: Decision) -> str:
        return d.notified or d.decision_date

    def is_current(d: Decision) -> bool:
        # Calendar year, the same rule as the deadline itself: 365 days loses a day across Feb 29
        # and sends a decision whose deadline is today to OLD CLAIMS with no deadline task.
        return _plus_year(dated(d)) >= today

    def decision_src(i: int) -> tuple[str, ...]:
        """A decision dated by its notification letter cites both."""
        return (f"decisions.{i}",) + ((f"decisions.{i}.notified",) if facts.decisions[i].notified else ())

    # The firm's SOP: an appointment form (21-22 or 21-22a) with revocation details is not a prior
    # rep. Newest by signed date; on a tie (or no dates) the last in document order.
    active = [(i, r) for i, r in enumerate(facts.prior_reps) if not r.revoked]
    if active:
        i, newest = max(reversed(active), key=lambda ir: ir[1].signed or "")
        prior, prior_src = f"Prior rep {newest.name}", (f"prior_reps.{i}",)
    else:
        prior = "No prior rep"
        prior_src = (*(f"prior_reps.{i}" for i in range(len(facts.prior_reps))), "none:poa_form:prior_representative")
    lines = [
        Line(f"FA {fee_pct if fee_pct is not None else '?'}%; {prior}", ("case:fee_agreement", *prior_src)),
        _sep("*" * 44),
    ]

    lines.append(Line(f"DOB: {_short(facts.dob)}", ("dob",) if facts.dob else ("none:dd214:dob",)))
    if intake_dob and facts.dob and intake_dob != facts.dob:
        # No dates in the flag: flags reach staff tasks, the case file and the orchestrator's prompt.
        swapped = intake_dob[:4] == facts.dob[:4] and intake_dob[5:7] == facts.dob[8:10] and intake_dob[8:10] == facts.dob[5:7]
        how = " (the day and month look swapped)" if swapped else ""
        flags.append(f"DOB mismatch: the intake / 21-22a date of birth differs from the DD-214{how}. File a corrected 21-22a.")
    periods = facts.service_periods
    first = periods[0].start if periods else None
    lines.append(Line(f"Service Era: {service_era(first)}", ("service_periods.0",) if periods else ("none:dd214:service_period",)))
    for i, sp in enumerate(periods):
        discharge = DISCHARGE_LABEL.get(sp.discharge or "", "Discharge unknown")
        comp = "" if sp.component in (None, "active") else f" {sp.component.title()}"
        text = f"{(sp.branch or '?').title()}{comp} {_ym(sp.start)} - {_ym(sp.end)}, {discharge}"
        if sp.discharge in NON_HONORABLE:
            text += "  ** FLAG: non-qualifying discharge for this period **"
            flags.append(f"Non-honorable discharge for the {sp.start} to {sp.end} period.")
        src = (f"service_periods.{i}",) + ((f"service_periods.{i}.discharge",) if sp.discharge else ())
        lines.append(Line(text, src))
    mos_src = tuple(f"mos.{i}" for i in range(len(facts.mos))) or ("none:dd214:mos",)
    lines.append(Line(f"MOS: {'; '.join(facts.mos) if facts.mos else '(not found)'}", mos_src))
    combined = facts.combined_rating if facts.combined_rating is not None else 0
    rating_src = ("combined_rating",) if facts.combined_rating is not None else ("none:rating_decision:combined_rating",)
    lines.append(Line(f"SC at time of signing {firm} - {combined}%", rating_src))
    lines.append(_sep(THICK))
    sc = sorted(enumerate(facts.sc_conditions), key=lambda ic: -(ic[1].rating_pct or 0))
    lines.append(Line(
        f"SC ({combined}%)|" + "".join(f" {cond_name(c.name)} {c.rating_pct}% |" for _, c in sc).rstrip("|").rstrip(),
        rating_src + tuple(f"sc_conditions.{i}" for i, _ in sc),
    ))  # fmt: skip
    lines.append(_sep(THICK))
    itf = _short(itf_date) if itf_date else "(not filed yet)"
    lines.append(Line(f"{firm} Filed 0966 Intent on {itf}", ("case:itf",)))
    lines.append(_sep(THIN))

    current = sorted((i for i, d in enumerate(facts.decisions) if is_current(d)),
                     key=lambda i: dated(facts.decisions[i]), reverse=True)  # fmt: skip
    deadlines = []
    n = 0
    for i in current:
        d, src = facts.decisions[i], decision_src(i)
        n += 1
        conds = "; ".join(cond_name(issue.condition) for issue in d.issues)
        deadline = _plus_year(dated(d))
        lines.append(Line(f"{n}. {cond_name(conds)}", (f"decisions.{i}",)))
        if d.form:
            lines.append(Line(f"   {d.form} filed {_short(d.filed)}", (f"decisions.{i}",)))
        lines += [
            Line(f"   R.D. {_short(dated(d))}", src),
            Line(f"   DEADLINE TO FILE AMA APPEAL {_short(deadline)}", src),
            _sep(THIN),
        ]
        deadlines.append({"deadline": deadline, "decision_date": dated(d), "conditions": [x.condition for x in d.issues]})
    for i, pf in enumerate(facts.pending_filings):
        n += 1
        src = (f"pending_filings.{i}",)
        lines += [
            Line(f"{n}. {'; '.join(cond_name(c) for c in pf.conditions)}: pending", src),
            Line(f"   {pf.form} filed {_short(pf.filed)}", src),
            _sep(THIN),
        ]

    latest: dict[str, int] = {}
    for i in sorted(range(len(facts.decisions)), key=lambda i: dated(facts.decisions[i])):
        for issue in facts.decisions[i].issues:
            latest[issue.condition] = i
    old = [(c, i) for c, i in latest.items() if not is_current(facts.decisions[i])]
    if old:
        lines += [_sep(WAVE), _sep("OLD CLAIMS"), _sep(WAVE)]
        for k, (cond, i) in enumerate(sorted(old, key=lambda ci: dated(facts.decisions[ci[1]]), reverse=True), 1):
            lines += [Line(f"{k}. {cond_name(cond)} R.D. {_short(dated(facts.decisions[i]))}", decision_src(i)), _sep(WAVE)]
    flags += facts.problems
    return FaceNote(lines=lines, flags=flags, deadlines=deadlines)
