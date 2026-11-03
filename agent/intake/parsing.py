"""Turn an answer into a typed value for a question's field type.

Two callers:
- `coerce` validates what any brain (LLM or offline) produced and normalises it, raising
  ValueError when the value doesn't fit the field type.
- `parse_text` is the offline brain's rule-based reader of free text. It only understands
  plain, direct answers; real variation in how people talk is what the LLM brain is for.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .conditions import normalize_condition, normalize_conditions
from .schema import RatedCondition, ServicePeriod

_UNSURE = re.compile(
    r"\b(not sure|unsure|don'?t know|do not know|don'?t remember|can'?t remember|no idea|no clue)\b",
    re.IGNORECASE,
)
_LEAD_YES = re.compile(r"^\W*(yes|yeah|yep|yup|sure|correct|absolutely)\b", re.IGNORECASE)
_LEAD_NO = re.compile(  # "No idea" is unsure; "No problem" / "No worries" are a yes
    r"^\W*(no|nope|never|nah|not yet)\b(?!\s+(idea|clue|problem|worries))", re.IGNORECASE
)
_LEAD_OK = re.compile(r"^\W*no (problem|worries)\b", re.IGNORECASE)
_NEG = re.compile(
    r"\b(i don'?t|i do not|i didn'?t|i did not|i haven'?t|i have not|i'?m not|i am not|not really|not yet|never|nope|none)\b",
    re.IGNORECASE,
)
_YES = re.compile(  # "I did" / "I am" only as a whole answer: "I'm confused" is not a yes
    r"\b(yes|yeah|yep|yup|correct|absolutely|i served|i'?m a veteran|i am a veteran)\b"
    r"|\b(i do|i did|i have|i am|i was)\s*([.!,;]|$)",
    re.IGNORECASE,
)
_NONE = re.compile(
    r"^\s*(no|none|nope|nothing|n/a|no other|that'?s (it|all)|not that i know)\b(?!\s+(idea|clue))",
    re.IGNORECASE,
)

_BRANCHES = {
    "air national guard": "air force",  # its component ("national guard") is read separately
    "army national guard": "army",
    "marine corps": "marine corps",
    "marines": "marine corps",
    "marine": "marine corps",
    "air force": "air force",
    "space force": "space force",
    "coast guard": "coast guard",
    "army": "army",
    "navy": "navy",
}
_BRANCH_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_BRANCHES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_DISCHARGES = [  # longest first, so "other than honorable" never reads as "honorable"
    ("other than honorable", "oth"),
    ("under other than honorable", "oth"),
    ("oth", "oth"),
    ("bad conduct", "bad_conduct"),
    ("dishonorable", "dishonorable"),
    ("general under honorable", "general"),
    ("general", "general"),
    ("uncharacterized", "uncharacterized"),
    ("entry level", "uncharacterized"),
    ("honorable", "honorable"),
]
_COMPONENTS = [
    ("national guard", "guard"),
    ("guard", "guard"),
    ("reserves", "reserve"),
    ("reserve", "reserve"),
    ("active", "active"),
]
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}  # fmt: skip
_DATE = re.compile(
    r"(?P<mdy>\b\d{1,2}/\d{1,2}/(?:19|20)\d{2}\b)"
    r"|(?P<ym>\b(?:19|20)\d{2}-\d{2}\b)"
    r"|(?P<my>\b\d{1,2}/(?:19|20)\d{2}\b)"
    r"|(?P<name>\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}\b)"
    r"|(?P<year>\b(?:19|20)\d{2}\b)"
)


def _dates(low: str) -> list[tuple[str, bool]]:
    """Dates in order of appearance as (YYYY-MM or YYYY, is_year_only). Accepts 2004-06, 6/2004,
    June 2004 and a bare 2004."""
    out = []
    for m in _DATE.finditer(low):
        if m.group("mdy"):  # 06/15/2004: keep the month, drop the day
            month, _day, year = m.group("mdy").split("/")
            if 1 <= int(month) <= 12:
                out.append((f"{int(year):04d}-{int(month):02d}", False))
        elif m.group("ym"):
            if 1 <= int(m.group("ym")[5:]) <= 12:  # an invalid month is not a date: re-ask
                out.append((m.group("ym"), False))
        elif m.group("my"):
            month, year = m.group("my").split("/")
            if 1 <= int(month) <= 12:
                out.append((f"{int(year):04d}-{int(month):02d}", False))
        elif m.group("name"):
            word, year = m.group("name").split()
            out.append((f"{year}-{_MONTHS[word[:3]]:02d}", False))
        else:
            out.append((m.group("year"), True))
    return out


def _phrase_code(table: list[tuple[str, str]], low: str) -> str | None:
    """First table entry whose phrase appears as whole words ("oth" must not match "both")."""
    return next((code for phrase, code in table if re.search(rf"\b{re.escape(phrase)}\b", low)), None)


def parse_bool(text: str) -> bool | None:
    """A leading yes/no first ("Yes I served, not sure what else you need" is a yes; "No idea" is
    not a no); then unsure; then negations ("I did not") before affirmations ("I did")."""
    if _LEAD_YES.match(text) or _LEAD_OK.match(text):
        return True
    if _LEAD_NO.match(text):
        return None if _UNSURE.search(text) else False  # "No, I'm not sure" is unsure
    if _UNSURE.search(text):
        return None
    if _NEG.search(text):
        return False
    if _YES.search(text):
        return True
    return None


def parse_service_periods(text: str) -> list[ServicePeriod] | None:
    periods: list[ServicePeriod] = []
    for chunk in (c for part in re.split(r";|\n", text) for c in _split_on_branches(part)):
        low = chunk.lower()
        dates = _dates(low)
        branch = next(
            (canon for word, canon in _BRANCHES.items() if re.search(rf"\b{word}\b", low)), None
        )
        if branch is None or len(dates) < 2:
            continue
        discharge = _phrase_code(_DISCHARGES, low)
        rest = low.replace("coast guard", "")  # so "Coast Guard" isn't read as the National Guard
        component = next(
            (code for phrase, code in _COMPONENTS if re.search(rf"\b{phrase}\b", rest)), "active"
        )
        periods.append(
            ServicePeriod(
                branch=branch,
                component=component,
                start=dates[0][0] + ("-01" if dates[0][1] else ""),  # a bare year: from January
                end=dates[1][0] + ("-12" if dates[1][1] else ""),  # ... to December
                discharge=discharge,
            )
        )
    if periods:  # "No other active duty, but Navy reserve 2014 to 2016" still has a period
        return periods
    return [] if _NONE.match(text) else None


def _split_on_branches(chunk: str) -> list[str]:
    """ "Army 2004 to 2008 and Navy 2010 to 2014": one chunk per branch named, when it has the
    dates for more than one period. A single period ("Army National Guard, 2005 to 2011") stays."""
    starts = [m.start() for m in _BRANCH_RE.finditer(chunk)]
    if len(starts) < 2 or len(_dates(chunk.lower())) < 4:
        return [chunk]
    cuts = [0] + starts[1:] + [len(chunk)]
    return [chunk[a:b] for a, b in zip(cuts, cuts[1:])]


def parse_rated_conditions(text: str) -> list[RatedCondition] | None:
    found = re.findall(r"([A-Za-z][A-Za-z '/-]*?)\s*(?:at\s+)?(\d{1,3})\s*(?:%|percent)", text)
    if not found:
        return [] if _NONE.match(text) else None
    return [  # "No, but tinnitus at 10%": the name is "tinnitus"
        RatedCondition(name=re.sub(r"^(no\W+)?(but|and)\s+", "", name.strip(), flags=re.I), rating_pct=int(pct))
        for name, pct in found
    ]


def parse_list(text: str) -> list[str] | None:
    """Items of a list answer. "None" is []; "No, but my knees hurt" keeps what follows the "but";
    an answer that is only "I don't know" is None (unreadable, so the brain marks it declined)."""
    if _is_only_unsure(text):  # "No idea, honestly": unreadable, so the brain marks it declined
        return None
    if _NONE.match(text):
        but = re.search(r"\bbut\b", text, re.IGNORECASE)
        if not but:
            return []
        text = text[but.end():]
    parts = [p.strip().strip(".") for p in re.split(r",|;|\band\b|\n", text)]
    items = [p for p in parts if p and not _is_only_unsure(p)]
    return items or (None if any(parts) else [])


def parse_text(qtype: str, text: str, options: tuple[str, ...] = ()) -> Any:
    """Rule-based reading of a plain answer. Returns None when the answer can't be read."""
    text = text.strip()
    if not text:
        return None
    match qtype:
        case "bool":
            return parse_bool(text)
        case "int":
            m = re.search(r"\d+", text)
            return int(m.group()) if m else None
        case "str":
            return None if _is_only_unsure(text) else text.rstrip(".")
        case "enum":
            low = text.lower()
            found = [(m.start(), opt) for opt in options for m in re.finditer(rf"\b{re.escape(opt)}\b", low)]
            # "never married" is not "married": an option preceded by a negation doesn't count
            found = [(i, opt) for i, opt in found if not re.search(r"\b(never|not)\s+$", low[:i])]
            if not found and "single" in options and re.search(r"\bnever (been )?married\b", low):
                return "single"
            return min(found)[1] if found else None
        case "list_str" | "conditions":
            return parse_list(text)
        case "service_periods" | "service_periods_append":
            return parse_service_periods(text)
        case "conditions_rated":
            return parse_rated_conditions(text)
        case "narrative":
            return text
    raise ValueError(f"unknown question type {qtype!r}")


_FILLER = set(
    "i im i'm it its it's that this what which else the a to be just really honestly um uh "
    "sorry maybe so well about any of off top my head exactly rest other others more anything".split()
)


def _is_only_unsure(text: str) -> bool:
    """ "I don't know" / "not sure, honestly": an unsure phrase and nothing else of substance.
    "Not sure, maybe 11B" and "Back pain, I don't know the cause" carry a value."""
    if not _UNSURE.search(text):
        return False
    rest = _UNSURE.sub(" ", text.lower())
    return not [w for w in re.findall(r"[a-z0-9']+", rest) if w not in _FILLER]


def _norm_period(p: Any) -> Any:
    """Map an LLM's free wording ("Honorable", "Active Duty", "Other Than Honorable") to the enums."""
    if not isinstance(p, dict):
        return p
    out = dict(p)
    for key in ("branch", "component", "discharge"):
        if isinstance(out.get(key), str):
            out[key] = out[key].strip().lower()
    comp = out.get("component")
    if comp:
        out["component"] = _phrase_code(_COMPONENTS, comp) or comp
    if out.get("branch") in _BRANCHES:
        out["branch"] = _BRANCHES[out["branch"]]
    dis = out.get("discharge")
    if dis:
        out["discharge"] = _phrase_code(_DISCHARGES, dis.replace("_", " ")) or dis
    return out


def coerce(qtype: str, value: Any, options: tuple[str, ...] = ()) -> Any:
    """Validate and normalise a value for a field type. Raises ValueError if it doesn't fit."""
    if isinstance(value, str) and qtype not in ("str", "narrative", "enum"):
        stripped = value.strip()
        if stripped[:1] in "[{" or stripped in ("true", "false", "null") or stripped.isdigit():
            value = json.loads(stripped)
        else:
            value = parse_text(qtype, stripped, options)
    if value is None:
        raise ValueError("no value")
    match qtype:
        case "bool":
            if not isinstance(value, bool):
                raise ValueError(f"expected a boolean, got {value!r}")
            return value
        case "int":
            if isinstance(value, bool):
                raise ValueError("expected an integer")
            number = int(value)
            if not 0 <= number <= 100:
                raise ValueError("rating must be 0-100")
            return number
        case "str" | "narrative":
            text = str(value).strip()
            if not text:
                raise ValueError("empty answer")
            if qtype == "str" and _is_only_unsure(text):
                raise ValueError("an unsure answer is not a value")
            return text
        case "enum":
            text = str(value).strip().lower()
            if text not in options:
                parsed = parse_text("enum", text, options)
                if parsed is None:
                    raise ValueError(f"{value!r} is not one of {options}")
                text = parsed
            return text
        case "list_str" | "conditions":
            items = [str(v).strip() for v in value if str(v).strip()]
            kept = [v for v in items if not _is_only_unsure(v)]
            if items and not kept:
                raise ValueError("an unsure answer is not a list item")
            return kept if qtype == "list_str" else normalize_conditions(kept)
        case "service_periods" | "service_periods_append":
            return [
                p if isinstance(p, ServicePeriod) else ServicePeriod.model_validate(_norm_period(p))
                for p in value
            ]
        case "conditions_rated":
            items = [
                c if isinstance(c, RatedCondition) else RatedCondition.model_validate(c)
                for c in value
            ]
            out: list[RatedCondition] = []
            for c in items:  # normalise each name; a duplicate keeps the first rating given
                name = normalize_condition(c.name)
                if name and name not in {o.name for o in out}:
                    out.append(RatedCondition(name=name, rating_pct=c.rating_pct))
            return out
    raise ValueError(f"unknown question type {qtype!r}")
