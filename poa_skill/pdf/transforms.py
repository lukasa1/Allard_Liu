"""Shared, blank-safe transforms binding canonical values to split PDF fields. Every helper
returns empty strings on None/blank input so a missing value just leaves the PDF field blank.

Adapted from an earlier form engine."""

import logging

logger = logging.getLogger(__name__)


def _digits(s: str | None) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def fit(value: str | None, max_chars: int | None, field: str = "") -> str:
    """Blank-safe truncate to a PDF widget's capacity. The VA forms' comb fields carry a
    /MaxLen the viewer enforces by CLIPPING — a value that overflows would render truncated
    with no trace, so when truncation actually happens we log a warning naming the field
    instead of losing it silently."""
    s = "" if value is None else str(value)
    if max_chars and len(s) > max_chars:
        logger.warning(
            "form fill: %s truncated from %d to %d chars", field or "field", len(s), max_chars
        )
        return s[:max_chars]
    return s


def person_name(value: str | None, max_chars: int | None = None, field: str = "") -> str:
    """A name the way VA forms want it: ALL CAPS (per the forms' own instructions), fitted
    to the widget's comb capacity (first-name boxes are 12 chars, last-name 18, middle
    initial 1 across the ARE-edition forms — verified /MaxLen)."""
    return fit(("" if value is None else str(value)).strip().upper(), max_chars, field)


def us_phone(p: str | None) -> str:
    """'+12406723689' or '240-672-3689' -> '(240) 672-3689' for single free-text phone widgets.
    Anything that isn't a 10-digit US number passes through as bare digits (readable beats
    dropped)."""
    d = _us10(p)
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return d


# VA state boxes are 2-char widgets: "California" gets truncated to "Ca" by the viewer.
# Normalize free text to the USPS code at the form boundary.
_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY", "district of columbia": "DC", "puerto rico": "PR", "guam": "GU",
    "american samoa": "AS", "u.s. virgin islands": "VI", "virgin islands": "VI",
    "northern mariana islands": "MP",
}  # fmt: skip


def us_state_code(state: str | None) -> str:
    """'California' → 'CA'; a 2-letter code passes through; unknown values pass through
    UNCHANGED (an odd value beats a silently dropped one)."""
    s = (state or "").strip()
    if len(s) == 2:
        return s.upper()
    return _STATE_CODES.get(s.lower(), s)


def us_country(addr: dict | None) -> str:
    """Country for a VA mailing-address block: 2-char boxes, so 'US', never 'USA'. Defaults to
    'US' for any captured address. Blank address -> blank box."""
    addr = addr or {}
    if not addr.get("line1"):
        return ""
    c = (addr.get("country") or "US").strip().upper()
    return "US" if c in ("USA", "UNITED STATES", "U.S.", "U.S.A.") else c[:2]


def split_ssn(ssn: str | None) -> tuple[str, str, str]:
    d = _digits(ssn)
    return (d[:3], d[3:5], d[5:9]) if len(d) >= 9 else ("", "", "")


def split_dob(iso: str | None) -> tuple[str, str, str]:
    """ISO YYYY-MM-DD → (MM, DD, YYYY)."""
    parts = (iso or "").split("-")
    if len(parts) == 3 and all(parts):
        y, m, d = parts
        return (m.zfill(2), d.zfill(2), y)
    return ("", "", "")


def split_zip(z: str | None) -> tuple[str, str]:
    d = _digits(z)
    return (d[:5], d[5:9]) if len(d) >= 5 else ("", "")


def _us10(p: str | None) -> str:
    d = _digits(p)
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def split_phone(p: str | None) -> tuple[str, str, str]:
    """'+1 555-555-0100' -> ('555', '555', '0100'). A leading US country code is dropped."""
    d = _us10(p)
    return (d[:3], d[3:6], d[6:10]) if len(d) >= 10 else ("", "", "")


def us_date(iso: str | None) -> str:
    """ISO YYYY-MM-DD → MM/DD/YYYY (for single date text fields)."""
    m, d, y = split_dob(iso)
    return f"{m}/{d}/{y}" if y else ""
