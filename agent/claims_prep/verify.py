"""`verify` (L24, L27): code checks every face-note line against the C-file pages its facts cite.

A line passes when it has source facts and each one holds:
  path          the fact's cited page shows its key values (`missing`)
  case:<field>  the firm's own record exists (the fee agreement's terms, the ITF date)
  none:<type>:<kind>  "nothing found" holds: every document of that type has a fact of that kind
                recorded from it (so a DD-214 in the file fails a "DOB: (unknown)" line)
Separator lines have no sources and are skipped.

Matching normalizes first: dates in every way documents write them (ISO, MM/DD/YYYY, YYYYMMDD,
"March 14, 2024"), service months (YYYY-MM, YYYYMM, MM/YYYY), percentages ("10%", "10 percent")
and condition names (`normalize_condition` and its synonyms). A rating is matched to its
condition: the first percentage after the condition's name must be the fact's. Values are
anchored to their labels (a DOB after "date of birth", a start after "entered", an end after
"separation date"), the MOS and a representative's name must be the whole field value, and a
decision must list every condition the page decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from agent.cfile.extract import _DISCHARGES
from agent.cfile.facenote import FaceNote
from agent.cfile.vbms import CFile
from agent.claims_prep.facts import Fact
from agent.intake.conditions import SYNONYMS, normalize_condition

_PCT = re.compile(r"(\d{1,3})\s*(?:%|percent)")
_OUTCOME = re.compile(r"\b(?:granted|increased|established|denied|continued|confirmed|deferred)\b")
_OUTCOMES = {"granted": "granted", "increased": "granted", "established": "granted", "denied": "denied",
             "continued": "denied", "confirmed": "denied", "deferred": "deferred"}  # fmt: skip


@dataclass(frozen=True)
class Failure:
    line: int
    text: str
    problem: str

    def __str__(self) -> str:
        return f"line {self.line} {self.text.strip()!r}: {self.problem}"


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def date_forms(iso: str) -> list[str]:
    d = date.fromisoformat(iso)
    month = d.strftime("%B").lower()
    return [iso, f"{d.month:02d}/{d.day:02d}/{d.year}", f"{d.month}/{d.day}/{d.year}", d.strftime("%Y%m%d"),
            f"{month} {d.day}, {d.year}", f"{month} {d.day} {d.year}", f"{month[:3]} {d.day}, {d.year}",
            f"{d.day} {month} {d.year}"]  # fmt: skip


def month_forms(ym: str) -> list[str]:
    year, month = ym.split("-")
    name = date(int(year), int(month), 1).strftime("%B").lower()
    return [ym, f"{year}{month}", f"{month}/{year}", f"{name} {year}"]


def _found(page: str, form: str, after: str = "", label: str = "") -> bool:
    """`form` as a whole token: 1/2/2004 is not inside 11/2/2004, nor 06/2004 inside 12/06/2004.
    With `label` (a regex), only right after it."""
    return re.search(rf"{label}(?<![\d/]){re.escape(form)}{after}(?![\d/])", page) is not None


def _has_date(page: str, iso: str, label: str = "") -> bool:
    return any(_found(page, f, label=label) for f in date_forms(iso))


def _has_month(page: str, ym: str, label: str = "") -> bool:
    """YYYYMM may run on into a day (the DD-214's YYYYMMDD)."""
    return any(_found(page, f, r"(?:\d\d)?" if f.isdigit() else "", label) for f in month_forms(ym))


# The labels a value must follow (a DOB is not just any date on the DD-214). `[^:\d]{0,40}:?\s*`
# skips the rest of the label: "date entered active duty this period (yyyymmdd): 20040601".
def _label(*names: str) -> str:
    return rf"(?:{'|'.join(names)})[^:\d]{{0,40}}:?\s*"


_DOB = _label("date of birth", r"\bdob", r"\bborn(?: on)?")
_START = _label("entered", r"\bfrom")
_END = _label("separation date", "released", r"\bto", r"\bthrough")
_DECIDED = re.compile(rf"service connection for (.+?) is {_OUTCOME.pattern}")
# A label's value runs to the next numbered DD-214 block ("12a. ") or the next label of the form.
_NEXT = r"(?=\s+\d{1,2}[a-z]?\.\s|\s+(?:type of|date|revocation|veteran)\b|\s*$)"


def _field_is(page: str, label: str, value: str) -> bool:
    """`value` is the whole value after `label` (the MOS is "88m motor transport operator", not
    "88m"; the representative is "alan smith", not "smith")."""
    return re.search(rf"{label}[^:]{{0,20}}:\s*{re.escape(value)}[.,;]?{_NEXT}", page) is not None


def mentions(page: str, condition: str) -> list[int]:
    """Where the page names the condition (its canonical name or a synonym), as end offsets."""
    canon = normalize_condition(condition)
    phrases = {canon, condition.lower(), *(p for p in SYNONYMS.get(canon, []) if len(p) > 3)}
    return [m.end() for p in phrases for m in re.finditer(rf"(?<![a-z]){re.escape(p)}(?![a-z])", page)]


def _pct_after(page: str, at: int, window: int = 80) -> int | None:
    m = _PCT.search(page, at, at + window)
    return int(m.group(1)) if m else None


def _outcome_after(page: str, at: int, window: int = 40) -> str | None:
    m = _OUTCOME.search(page, at, at + window)
    return _OUTCOMES[m.group()] if m else None


def discharges(page: str) -> set[str]:
    """The characters of discharge a page states; a longer phrase hides the shorter one inside it
    ("other than honorable" is not also "honorable")."""
    text, found = page.upper(), set()
    for phrase, code in _DISCHARGES:
        if phrase in text:
            found.add(code)
            text = text.replace(phrase, " ")
    return found


def _rated(page: str, condition: str, pct: int) -> bool:
    return any(_pct_after(page, at) == pct for at in mentions(page, condition))


def missing(f: Fact, page_text: str) -> list[str]:
    """The fact's key values its cited page doesn't show (empty: the cite holds)."""
    page, out = _norm(page_text), []

    def need(ok: bool, what: str) -> None:
        if not ok:
            out.append(what)

    if f.kind == "dob":
        need(_has_date(page, f.dob, _DOB), f"{f.dob} as the date of birth")
    elif f.kind == "service_period":
        need(f.branch.lower() in page, f.branch)
        need(_has_month(page, f.start, _START), f"{f.start} as the entry date")
        if f.end:
            need(_has_month(page, f.end, _END), f"{f.end} as the separation date")
        else:
            need("separation date" not in page, "no separation date (the page has one: record `end`)")
    elif f.kind == "discharge":
        need(f.character in discharges(page), f"discharge {f.character}")
        need(_has_month(page, f.period_start, _START), f"the period starting {f.period_start}")
    elif f.kind == "mos":
        labeled = "specialty" in page
        need(_field_is(page, "specialty", _norm(f.mos)) if labeled else _found(page, _norm(f.mos)),
             f"{f.mos} as the whole MOS (code and title)")  # fmt: skip
    elif f.kind == "rated_condition":
        need(_rated(page, f.condition, f.pct), f"{f.condition} {f.pct}%")
    elif f.kind == "combined_rating":
        need(any(_pct_after(page, m.end(), 40) == f.pct for m in re.finditer("combined", page)),
             f"combined rating {f.pct}%")  # fmt: skip
    elif f.kind == "decision":
        need(_has_date(page, f.date), f.date)
        if f.form:
            need(f.form.lower() in page, f"form {f.form}")
        if f.filed:
            need(_has_date(page, f.filed), f"filed {f.filed}")
        listed = {i.condition for i in f.issues}
        for decided in _DECIDED.findall(page):
            need(normalize_condition(decided) in listed, f"every decided issue (record {decided!r} too)")
        for issue in f.issues:
            at = mentions(page, issue.condition)
            need(any(_outcome_after(page, a) == issue.outcome for a in at), f"{issue.condition} {issue.outcome}")
            if issue.outcome == "granted" and issue.pct is not None:
                need(_rated(page, issue.condition, issue.pct), f"{issue.condition} {issue.pct}%")
    elif f.kind == "notification_letter":
        need(_has_date(page, f.date), f.date)
        need(_has_date(page, f.decision_date), f"decision {f.decision_date}")
    elif f.kind == "prior_representative":
        labeled = "representative:" in page
        need(_field_is(page, "representative", _norm(f.name)) if labeled else _found(page, _norm(f.name)),
             f"{f.name} as the whole representative name")  # fmt: skip
        typed = {"vso": "organization" in page, "agent": "agent" in page,
                 "attorney": "attorney" in page and "organization" not in page}  # fmt: skip
        need(typed[f.rep_type], f"a {f.rep_type}")
        if f.signed:
            need(_has_date(page, f.signed), f"signed {f.signed}")
        if f.revoked:
            need(_has_date(page, f.revoked) and "revok" in page, f"revoked {f.revoked}")
        else:
            need("revok" not in page, "no revocation details (the page has them: record `revoked`)")
    elif f.kind == "pending_filing":
        need(f.form.lower() in page, f.form)
        need(_has_date(page, f.filed), f"filed {f.filed}")
        for c in f.conditions:
            need(bool(mentions(page, c)), c)
    return out


def check(note: FaceNote, cites: dict[str, Fact], table: list[Fact], cfile: CFile, case: dict[str, bool]) -> list[Failure]:
    """Every failing line of the note, with what to fix."""
    failures, cited_docs = [], {}
    for f in table:
        cited_docs.setdefault(f.cite.doc_id, set()).add(f.kind)
    for n, line in enumerate(note.lines, 1):
        if line.sources is None:
            continue
        if not line.sources:
            failures.append(Failure(n, line.text, "no source fact"))
        for src in line.sources:
            if src.startswith("case:"):
                if not case.get(src[5:]):
                    failures.append(Failure(n, line.text, f"the case file has no {src[5:]} on record"))
            elif src.startswith("none:"):
                doc_type, kind = src[5:].split(":")
                lacking = [d.doc_id for d in cfile.docs if d.type == doc_type and kind not in cited_docs.get(d.doc_id, set())]
                if lacking:
                    failures.append(Failure(n, line.text, f"says nothing was found, but {doc_type} {', '.join(lacking)} "
                                            f"has no {kind} fact recorded from it: read it and record it"))  # fmt: skip
            else:
                f = cites[src]
                gaps = missing(f, cfile.owner(f.cite.page).page(f.cite.page))
                if gaps:
                    failures.append(Failure(n, line.text, f"fact {f.id} cites {f.cite}, which does not show "
                                            f"{'; '.join(gaps)}: re-record or re-cite fact {f.id}"))  # fmt: skip
    return failures
