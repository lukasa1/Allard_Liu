"""C-file text helpers: document typing (triage), SSN stripping, and value normalizers.

Claims prep's tools read the simulated VBMS (agent/cfile/vbms.py), which types each document with
`triage` and runs `strip_ssns` on every page at ingest, so an SSN never reaches a context or a
trace. The normalizers (`_iso`, `_pct`, `_outcome`, `_form_id`, `_branch`, `_ym`) turn the values a
model writes into the typed facts' shapes (agent/claims_prep/facts.py); `verify` reads
`_DISCHARGES` to find a discharge on a page.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

DocType = Literal[
    "dd214", "rating_decision", "notification_letter", "claim_form", "poa_form", "other"
]

_TRIAGE = [
    ("dd214", re.compile(r"certificate of release|dd form 214|dd 214", re.IGNORECASE)),
    # Letters mention "the rating decision", so they are checked before rating decisions.
    (
        "notification_letter",
        re.compile(r"we made a decision|date of this letter|notification letter", re.IGNORECASE),
    ),
    ("rating_decision", re.compile(r"rating decision", re.IGNORECASE)),
    (
        "poa_form",
        re.compile(r"21-22a?\b.*appointment|appointment of .* representative", re.IGNORECASE),
    ),
    (
        "claim_form",
        re.compile(
            r"21-526|21-0995|20-0995|20-0996|10182|application for disability", re.IGNORECASE
        ),
    ),
]


# Separators between SSN digit groups: spaces and newlines (pypdf splits table cells onto their
# own lines), hyphens and dashes, dots.
_SEP = r"[\s\-\u2010-\u2015\u2212.]*"
_SEP1 = r"[\s\-\u2010-\u2015\u2212.]+"
# 3-2-4 with a separator at both breaks, or nine digits run together; a ZIP+4 (94305-1234) is 5-4.
_SSN = re.compile(rf"(?<!\d)(\d{{3}}{_SEP1}\d{{2}}{_SEP1}\d{{4}}|\d{{9}})(?!\d)")
# Next to a label any 9 digits are an SSN, however they are split (even one digit per line). The
# digits must start right after the label, so a masked SSN's neighbouring field (a DOB) stays.
_SSN_LABEL = re.compile(r"\bSSN\b|\bsocial\s+security\b|\bsoc\.?\s*sec\b", re.IGNORECASE)
# No dots here: "DOB 1985.04.07\n2." must not read as nine digits.
_LSEP = r"[\s\-\u2010-\u2015\u2212]*"
_SSN_AFTER_LABEL = re.compile(rf"[^\d]{{0,24}}?(\d(?:{_LSEP}\d){{8}})(?!\d)")


def _starts_with_date(digits: str) -> bool:
    """19850407 + the next field's digit is a DOB, not an SSN."""
    try:
        return 1900 <= int(digits[:4]) <= 2100 and bool(datetime.strptime(digits[:8], "%Y%m%d"))
    except ValueError:
        return False


def strip_ssns(text: str) -> str:
    """Hide SSNs (123-45-6789, 123 45 6789, 123.45.6789, 123456789, split across lines). Dates stay
    (8-digit 19850407, 2021-03-04): they don't have the 3/2/4 shape.

    Both passes read the original text: the replacement says "SSN", and a pass over the output
    would treat it as a label and mask the next field (the DOB)."""
    spans = [m.span() for m in _SSN.finditer(text)]
    for label in _SSN_LABEL.finditer(text):
        m = _SSN_AFTER_LABEL.match(text, label.end())
        if m and m.start(1) - label.end() <= 24 + 3 and not _starts_with_date(re.sub(r"\D", "", m.group(1))):
            spans.append(m.span(1))
    out, pos = [], 0
    for a, b in sorted(spans):
        if a < pos:  # overlapping matches of the same number
            pos = max(pos, b)
            continue
        out += [text[pos:a], "[SSN removed]"]
        pos = b
    return "".join(out) + text[pos:]


def triage(text: str) -> DocType:
    head = text[:1500]
    for doc_type, pattern in _TRIAGE:
        if pattern.search(head):
            return doc_type  # type: ignore[return-value]
    return "other"


_DATE_FORMATS = (
    "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y",
    "%B %d %Y", "%d %B %Y", "%d %b %Y", "%Y%m%d", "%Y-%m-%d",
)  # fmt: skip


def _iso(text: str) -> str | None:
    text = text.strip().rstrip(".")
    # ISO dates with a time part ("2021-03-04T00:00:00", "2021-03-04 00:00:00Z"): models and
    # JSON tooling write these, and a decision without a date has no appeal deadline.
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[T ]\d{1,2}:\d{2}\S*)?$", text)
    if m:
        text = m.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _pct(v):  # "70%", "70 percent", 70.0 -> 70
    if isinstance(v, str):
        m = re.search(r"\d+", v)
        return int(m.group()) if m else None
    if isinstance(v, float):
        return round(v)
    return v


def _outcome(v):
    """Decision words as rating decisions write them. An increase is a grant (of a higher rating);
    "continued" / "confirmed" means no change, which is appealable like a denial."""
    if not isinstance(v, str):
        return v
    low = v.strip().strip(".").lower()
    for word, outcome in (("defer", "deferred"), ("den", "denied"), ("continu", "denied"),
                          ("confirm", "denied"), ("grant", "granted"), ("increas", "granted"),
                          ("establish", "granted")):  # fmt: skip
        if re.search(rf"\b{word}", low):
            return outcome
    return low  # anything else isn't an outcome: the issue is dropped and flagged (below)


def _form_id(v):
    """ "VA Form 21-526EZ", "21-526EZ", "526 EZ" -> "526EZ", so a decided filing matches its form."""
    if not isinstance(v, str):
        return v
    return re.sub(r"^(va\s*)?(form\s*)?(21|20)\s*-\s*", "", v.strip(), flags=re.IGNORECASE).replace(" ", "").upper() or None


def _branch(v: str) -> str | None:
    low = re.sub(r"^(?:u\.?s\.?|united states)\s+", "", v.strip().lower())
    low = {"marines": "marine corps", "usmc": "marine corps", "usaf": "air force"}.get(low, low)
    return low or None


def _ym(v: str) -> str | None:
    """Service dates are YYYY-MM; models also write full dates or YYYYMM."""
    v = v.strip()
    if re.fullmatch(r"\d{4}-\d{2}", v):
        return v
    if re.fullmatch(r"\d{6}", v):
        return f"{v[:4]}-{v[4:]}"
    iso = _iso(v)
    return iso[:7] if iso else None


_DISCHARGES = [("OTHER THAN HONORABLE", "oth"), ("BAD CONDUCT", "bad_conduct"), ("DISHONORABLE", "dishonorable"),
               ("GENERAL", "general"), ("UNDER HONORABLE", "general"), ("UNCHARACTERIZED", "uncharacterized"),
               ("HONORABLE", "honorable")]  # fmt: skip
