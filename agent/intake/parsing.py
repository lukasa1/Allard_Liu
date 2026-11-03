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
from itertools import pairwise
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
DISCHARGES = ("honorable", "general", "oth", "bad_conduct", "dishonorable", "uncharacterized")
# Discharge phrases (after hyphens and underscores became spaces), most specific first. Each match
# is blanked out before the next, so "other than honorable" never also reads as "honorable".
_DISCHARGE_RES = [
    # A qualifier before "honorable" makes it non-honorable: OTH is the catch-all code (A1 then
    # sends it to an attorney, which is a review, not a rejection).
    (r"\b(under )?(other than|less than|not|non|un|wasn'?t|was not|isn'?t|is not) ?honorabl[ey]\b", "oth"),
    (r"\bdis ?honorabl[ey]\b", "dishonorable"),
    (r"\b(bad conduct|bcd)\b", "bad_conduct"),
    (r"\bgeneral( discharge)?\b(\W*under honorable( conditions)?\b)?", "general"),
    (r"\b(uncharacterized|entry level( separation)?|els)\b", "uncharacterized"),
    (r"\both\b", "oth"),
    (r"\bhonorabl[ey]\b", "honorable"),
]
_NEGATED = re.compile(r"\b(not|never|no|wasn'?t|isn'?t|nor)\s+(an?\s+|a\s+)?$")
# Stop-rule fields (A1) read free text only when it is plain. A hedge makes an answer unsure; a
# qualifier left over next to a discharge, or discharge words code can't read, need the model.
HEDGE = re.compile(
    _UNSURE.pattern + r"|\b(i think|i believe|i guess|i suppose|probably|maybe|possibly|perhaps|might|"
    r"pretty sure|fairly sure|kind of|sort of|if i remember|i'?m not certain)\b",
    re.IGNORECASE,
)
_QUALIFIER = re.compile(
    r"\b(not|no|never|less|other|than|non|un|wasn'?t|isn'?t|didn'?t|don'?t|weren'?t|except|exactly|quite|almost|nearly|technically|"
    r"but|though|however|upgrad\w*|downgrad\w*|chang\w*|originally|initially|either|or)\b"
)
_DISCHARGE_WORDS = re.compile(
    r"\b(honou?r\w*|dishonou?r\w*|discharg\w*|conduct|misconduct|separat\w*|characteri[sz]\w*|"
    r"chapter\w*|court martial\w*|oth|general|bcd|els)\b"
)


def _scan_discharges(text: str) -> tuple[set[str] | None, str]:
    """(the discharge codes named in `text`, or None when one is negated; the text left after the
    discharge phrases). British spellings ("honourable") read as American."""
    low = re.sub(r"\s+", " ", re.sub(r"[-_/()]", " ", text.lower().replace("honour", "honor"))).strip()
    if low in DISCHARGES:
        return {low}, ""
    found = set()
    for pattern, code in _DISCHARGE_RES:
        for m in re.finditer(pattern, low):
            if _NEGATED.search(low[: m.start()]):
                return None, low  # "not dishonorable", "never got a general": unclear, ask again
            found.add(code)
        low = re.sub(pattern, " ", low)
    return found, low


def _read_discharge(text: str) -> tuple[str | None, str]:
    """(the discharge code named in `text` or None, the text left after the discharge phrases)."""
    found, low = _scan_discharges(text)
    if not found or len(found) != 1 or _UNSURE.search(text):
        return None, low
    return found.pop(), low


def named_discharges(text: str) -> set[str] | None:
    """The discharge codes a plain answer names ({} when none); None when it isn't plain (a
    negation, a hedge or a qualifier), so nothing can be cross-checked against it."""
    found, rest = _scan_discharges(text)
    return None if found is None or HEDGE.search(text) or _QUALIFIER.search(rest) else found


def parse_discharge(text: str) -> str | None:
    """The character of discharge named in `text` (one of DISCHARGES), or None when there is none
    or it isn't clear (two different ones, "not general", "not sure"): then intake asks again."""
    return _read_discharge(text)[0]


def strict_discharge(text: str) -> str | None:
    """A stop-rule reading of the discharge in `text`: None when no discharge is mentioned at all;
    the code when it is plain ("honorable", "OTH", "general under honorable conditions"); else a
    ValueError, so the model passes the discharge it understood as one of DISCHARGES."""
    code, rest = _read_discharge(text)
    if code is None and not _DISCHARGE_WORDS.search(text.lower()):
        return None
    if code is None or _QUALIFIER.search(rest) or HEDGE.search(text):
        raise ValueError(f"the discharge in {text.strip()!r} is not plain enough for code to read")
    return code


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


# A turn after the first word: "No combat, but I was in the Navy", "Nah just kidding, yes".
_TURN = re.compile(r"\b(but|though|although|except|just kidding|kidding|j/?k|actually|wait)\b", re.IGNORECASE)


def parse_bool(text: str) -> bool | None:
    """A leading yes/no first ("Yes I served, not sure what else you need" is a yes; "No idea" is
    not a no); then unsure; then negations ("I did not") before affirmations ("I did"). A no that
    turns into a yes ("Never deployed, but yes I served") or a mix of both is unclear: None."""
    lead_no = _LEAD_NO.match(text)
    if _LEAD_YES.match(text) or _LEAD_OK.match(text):
        rest = text[(_LEAD_YES.match(text) or _LEAD_OK.match(text)).end():]
        return None if _TURN.search(rest) and re.search(r"\b(no|not|never|nope)\b", rest, re.IGNORECASE) else True
    if lead_no:
        rest = text[lead_no.end():]
        if _UNSURE.search(text) or _TURN.search(rest) or _YES.search(rest) or _LEAD_YES.search(rest):
            return None  # "No, I'm not sure" is unsure; "No combat, but I was in the Navy" is not a no
        return False
    if _UNSURE.search(text):
        return None
    neg, yes = _NEG.search(text), _YES.search(text)
    if neg and yes:
        return None  # "I never deployed but I served"
    if neg:
        return False
    return True if yes else None


# Plain answers a stop-rule bool accepts as free text (after _plain() normalised it); anything
# else ("I haven't served since 2008", "I'm not a disabled veteran yet") needs the model's value.
_PLAIN_BOOL = {
    True: re.compile(r"(yes|yeah|yep|yup|correct|true)( (i (do|did|have|am|was|served)|i am a veteran))?"
                     r"|i (do|did|have|am|was|served)|i am a veteran"),
    False: re.compile(r"(no|nope|nah|false)( (i (do|did|have|am) not( serve)?|i never (did|served)|i am not a veteran))?"
                      r"|i (do|did|have|am) not( serve)?|i never served|never|i am not a veteran"),
}


def _plain(text: str) -> str:
    low = re.sub(r"[’`]", "'", text.lower())
    low = re.sub(r"\bi'?m\b", "i am", re.sub(r"\b(do|did|have|has|was|is|are)n'?t\b", r"\1 not", low))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]", " ", low)).strip()


def plain_value(qtype: str, text: str) -> Any:
    """A stop-rule field's value from free text, only when the answer is plain: a bare yes/no, a
    bare rating ("70", "70%"), service periods whose discharge is plain. Raises ValueError."""
    low = _plain(text)
    match qtype:
        case "bool":
            for value, pattern in _PLAIN_BOOL.items():
                if pattern.fullmatch(low):
                    return value
        case "int":
            if m := re.fullmatch(r"(\d{1,3}) ?(%|percent)?", low):
                return int(m.group(1))
        case "service_periods" | "service_periods_append":
            periods = parse_service_periods(text, strict=True)
            if periods is not None:
                return periods
    raise ValueError(f"{text.strip()!r} is not a plain answer")


def parse_service_periods(text: str, strict: bool = False) -> list[ServicePeriod] | None:
    """Periods named in `text` (branch and two dates each). `strict` (a stop-rule reading): a
    discharge must be plain (strict_discharge raises otherwise)."""
    periods: list[ServicePeriod] = []
    read = strict_discharge if strict else parse_discharge
    for chunk in (c for part in re.split(r";|\n", text) for c in _split_on_branches(part)):
        low = chunk.lower()
        dates = _dates(low)
        branch = next(
            (canon for word, canon in _BRANCHES.items() if re.search(rf"\b{word}\b", low)), None
        )
        if branch is None or len(dates) < 2:
            continue
        discharge = read(chunk)
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
        if len(periods) > 1 and re.search(r"\b(both|all)\b", text, re.IGNORECASE):
            # "Army 2004 to 2008 and Navy 2010 to 2014, both honorable": one discharge for all
            named = {p.discharge for p in periods} - {None}
            if len(named) == 1:
                periods = [p.model_copy(update={"discharge": p.discharge or next(iter(named))}) for p in periods]
        return periods
    return [] if _NONE.match(text) else None


def _split_on_branches(chunk: str) -> list[str]:
    """ "Army 2004 to 2008 and Navy 2010 to 2014": one chunk per branch named, when it has the
    dates for more than one period. A single period ("Army National Guard, 2005 to 2011") stays."""
    starts = [m.start() for m in _BRANCH_RE.finditer(chunk)]
    if len(starts) < 2 or len(_dates(chunk.lower())) < 4:
        return [chunk]
    cuts = [0] + starts[1:] + [len(chunk)]
    return [chunk[a:b] for a, b in pairwise(cuts)]


def parse_rated_conditions(text: str) -> list[RatedCondition] | None:
    found = re.findall(r"([A-Za-z][A-Za-z '/-]*?)\s*(?:at\s+)?(\d{1,3})\s*(?:%|percent)", text)
    if not found:
        return [] if _NONE.match(text) else None
    return [  # "No, but tinnitus at 10%": the name is "tinnitus"
        RatedCondition(name=re.sub(r"^(no\W+)?(but|and)\s+", "", name.strip(), flags=re.IGNORECASE), rating_pct=int(pct))
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
        case "int":  # "I'm not 100, I'm 70" or "70, maybe 100 soon" is unclear: ask again
            numbers = set(re.findall(r"\d+", text))
            if len(numbers) != 1 or re.search(r"\b(not|isn'?t|wasn'?t|never|maybe|hope|soon)\b", text, re.IGNORECASE):
                return None
            return int(numbers.pop())
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


_FILLER = {
    "i", "im", "i'm", "it", "its", "it's", "that", "this", "what", "which", "else", "the", "a", "to", "be", "just", "really", "honestly", "um", "uh", "sorry", "maybe", "so", "well", "about", "any", "of", "off", "top", "my", "head", "exactly", "rest", "other", "others", "more", "anything",
}


def _is_only_unsure(text: str) -> bool:
    """ "I don't know" / "not sure, honestly": an unsure phrase and nothing else of substance.
    "Not sure, maybe 11B" and "Back pain, I don't know the cause" carry a value."""
    if not _UNSURE.search(text):
        return False
    rest = _UNSURE.sub(" ", text.lower())
    return not [w for w in re.findall(r"[a-z0-9']+", rest) if w not in _FILLER]


def _norm_period(p: Any, strict: bool) -> Any:
    """Map an LLM's free wording ("Honorable", "Active Duty", "Other Than Honorable") to the enums.
    `strict`: a discharge must be plain or one of DISCHARGES (or null)."""
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
    if dis and strict:
        out["discharge"] = strict_discharge(dis)
        if out["discharge"] is None:
            raise ValueError(f"discharge {dis!r} is not one of {DISCHARGES} (pass null if not known yet)")
    elif dis:
        out["discharge"] = parse_discharge(dis) or dis  # unreadable: the model validation refuses it
    return out


def coerce(qtype: str, value: Any, options: tuple[str, ...] = (), strict: bool = False) -> Any:
    """Validate and normalise a value for a field type. Raises ValueError if it doesn't fit.
    `strict` (a stop-rule field, A1): free text counts only when it is plain (plain_value)."""
    if isinstance(value, str) and qtype not in ("str", "narrative", "enum"):
        stripped = value.strip()
        if stripped[:1] in "[{" or stripped in ("true", "false", "null") or stripped.isdigit():
            value = json.loads(stripped)
        elif strict:
            value = plain_value(qtype, stripped)
        else:
            value = parse_text(qtype, stripped, options)
    if value is None:
        raise ValueError("no value")
    match qtype:
        case "bool":
            if not isinstance(value, bool):
                raise ValueError(f"expected a boolean, got {value!r}")  # noqa: TRY004 (callers catch ValueError)
            return value
        case "int":
            if isinstance(value, bool):
                raise ValueError("expected an integer")  # noqa: TRY004 (callers catch ValueError)
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
                p if isinstance(p, ServicePeriod) else ServicePeriod.model_validate(_norm_period(p, strict))
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
