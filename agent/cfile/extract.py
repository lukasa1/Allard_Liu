"""Read C-file PDFs into CfileFacts.

Pipeline (the same shape as the firm's manual method: find the documents by name, read each one,
then assemble the note):
  1. text      pypdf text of each document (first pages only for very long ones)
  2. triage    keep only documents a face note uses: DD-214s, rating decisions (narrative + code
               sheet), notification letters, filing forms, 21-22 / 21-22a. Everything else
               (treatment records, ...) is skipped, which keeps the LLM cost per C-file small.
  3. extract   per document: DocumentFacts. OfflineExtractor reads the synthetic layout with
               regexes (no key needed); DSPyExtractor reads any layout with an LLM.
  4. merge     deterministic: link letters to decisions by date, filing forms to decisions by the
               evidence list, take the code sheet from the newest decision.

Real C-files contain PII and medical records. SSNs are stripped from the text before any
extractor sees it (a face note never needs one); the DOB stays, because the face note shows it.
With real data this must still run only on infrastructure covered by the firm's BAA (Bedrock);
the synthetic files are fine anywhere.
"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Literal, Protocol, get_args

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from pypdf import PdfReader

from agent.cfile.facts import CfileFacts, Decision, Issue, Outcome, PendingFiling, PriorRep
from agent.intake.conditions import normalize_condition
from agent.intake.schema import Discharge, RatedCondition, ServicePeriod

MAX_CHARS = 12000  # per document sent to the LLM
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


def pdf_text(data: bytes, max_pages: int = 8) -> str:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        # Many "encrypted" PDFs only restrict printing; a real password fails below.
        reader.decrypt("")
    return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])


def triage(text: str) -> DocType:
    head = text[:1500]
    for doc_type, pattern in _TRIAGE:
        if pattern.search(head):
            return doc_type  # type: ignore[return-value]
    return "other"


class DocumentFacts(BaseModel):
    doc_type: DocType = "other"
    dob: str | None = Field(None, description="YYYY-MM-DD (DD-214)")
    service_period: ServicePeriod | None = Field(
        None, description="DD-214: branch, component, start/end YYYY-MM, discharge"
    )
    mos: list[str] = Field(default_factory=list, description="DD-214 primary specialty")
    decision_date: str | None = Field(
        None, description="YYYY-MM-DD; for letters, the decision the letter is about"
    )
    letter_date: str | None = Field(None, description="notification letter's own date, YYYY-MM-DD")
    issues: list[Issue] = Field(
        default_factory=list, description="rating decision: each condition decided"
    )
    evidence_form: str | None = Field(
        None, description="filing form named in the evidence list, e.g. 526EZ, 0995"
    )
    evidence_received: str | None = Field(
        None, description="YYYY-MM-DD the filing form was received"
    )
    combined_rating: int | None = Field(None, description="code sheet combined evaluation")
    sc_conditions: list[RatedCondition] = Field(
        default_factory=list, description="code sheet service-connected list"
    )
    form: str | None = Field(None, description="claim form id, e.g. 526EZ")
    filed: str | None = Field(
        None, description="claim form date received, or 21-22/21-22a date signed, YYYY-MM-DD"
    )
    conditions: list[str] = Field(default_factory=list, description="claim form claimed conditions")
    rep_name: str | None = None
    rep_kind: Literal["attorney", "agent", "vso"] | None = None

    # Models write values the way documents do ("Honorable", "Active Duty", "Granted", "70%").
    # Map them here: a strict schema turns one odd value into a parse error that loses the document.
    @field_validator("dob", "decision_date", "letter_date", "evidence_received", "filed", mode="before")
    @classmethod
    def _dates(cls, v):
        return _iso(str(v)) if v else None

    @field_validator("doc_type", mode="before")
    @classmethod
    def _doc_type(cls, v):
        if not isinstance(v, str):
            return v
        return _DOC_TYPES.get(re.sub(r"[^a-z0-9]", "", v.lower()), "other")

    @field_validator("combined_rating", mode="before")
    @classmethod
    def _combined(cls, v):
        return _pct(v)

    @field_validator("service_period", mode="before")
    @classmethod
    def _period(cls, v):
        if not isinstance(v, dict):
            return v
        v = dict(v)
        for key, fix in (("branch", _branch), ("component", _component), ("discharge", _discharge),
                         ("start", _ym), ("end", _ym)):  # fmt: skip
            if isinstance(v.get(key), str):
                v[key] = fix(v[key])
        return v

    @field_validator("issues", "sc_conditions", "mos", "conditions", mode="before")
    @classmethod
    def _lists(cls, v, info):
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(";") if s.strip()]
        if info.field_name == "issues":
            return [
                {**i, "outcome": _outcome(i.get("outcome")), "pct": _pct(i.get("pct"))}
                if isinstance(i, dict) else i
                for i in v
            ]  # fmt: skip
        if info.field_name == "sc_conditions":
            return [
                {**c, "rating_pct": _pct(c.get("rating_pct"))} if isinstance(c, dict) else c
                for c in v
            ]
        return v

    @field_validator("form", "evidence_form", mode="before")
    @classmethod
    def _forms(cls, v):
        return _form_id(v)

    # Issues whose outcome or condition can't be read: dropped from the facts, named in the note's
    # flags, so one odd issue doesn't cost the whole rating decision.
    _unparsed_issues: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="wrap")
    @classmethod
    def _drop_bad_issues(cls, data, handler):
        bad: list[str] = []
        if isinstance(data, dict) and isinstance(data.get("issues"), list):
            good = []
            for i in data["issues"]:
                if isinstance(i, dict):
                    i = {**i, "outcome": _outcome(i.get("outcome")), "pct": _pct(i.get("pct"))}
                    if i["outcome"] not in get_args(Outcome) or not str(i.get("condition") or "").strip():
                        bad.append(str(i.get("condition") or "an issue"))
                        continue
                good.append(i)
            data = {**data, "issues": good}
        out = handler(data)
        out._unparsed_issues = bad
        return out

    @field_validator("rep_kind", mode="before")
    @classmethod
    def _rep_kind(cls, v):
        if not isinstance(v, str):
            return v
        low = v.lower()
        if "organization" in low or "vso" in low:
            return "vso"
        return "agent" if "agent" in low else ("attorney" if "attorney" in low else None)


class Extractor(Protocol):
    def extract(self, text: str, doc_type: DocType) -> DocumentFacts: ...


# ------------------------------------------------------------------------------- offline (regex)


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


_DOC_TYPES = {t.replace("_", ""): t for t in get_args(DocType)} | {
    "dd214form": "dd214", "letter": "notification_letter", "decisionletter": "notification_letter",
    "codesheet": "rating_decision", "2122": "poa_form", "2122a": "poa_form",
}  # fmt: skip


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


def _component(v: str) -> str | None:
    low = v.lower()
    pairs = (("reserve", "reserve"), ("guard", "guard"), ("active", "active"), ("regular", "active"))
    for key, comp in pairs:
        if key in low:
            return comp
    return None


def _discharge(v: str) -> str | None:
    if v.strip().lower() in get_args(Discharge):
        return v.strip().lower()
    upper = v.upper()
    return next((code for k, code in _DISCHARGES if k in upper), None)


def _ym(v: str) -> str | None:
    """Service dates are YYYY-MM; models also write full dates or YYYYMM."""
    v = v.strip()
    if re.fullmatch(r"\d{4}-\d{2}", v):
        return v
    if re.fullmatch(r"\d{6}", v):
        return f"{v[:4]}-{v[4:]}"
    iso = _iso(v)
    return iso[:7] if iso else None


def _field(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


_BRANCHES = {"ARMY": "army", "NAVY": "navy", "AIR FORCE": "air force", "MARINE CORPS": "marine corps",
             "COAST GUARD": "coast guard", "SPACE FORCE": "space force"}  # fmt: skip
_DISCHARGES = [("OTHER THAN HONORABLE", "oth"), ("BAD CONDUCT", "bad_conduct"), ("DISHONORABLE", "dishonorable"),
               ("GENERAL", "general"), ("UNDER HONORABLE", "general"), ("UNCHARACTERIZED", "uncharacterized"),
               ("HONORABLE", "honorable")]  # fmt: skip


class OfflineExtractor:
    """Reads the synthetic C-file layout (agent/cfile/synth.py). Not meant for real documents."""

    def extract(self, text: str, doc_type: DocType) -> DocumentFacts:
        f = DocumentFacts(doc_type=doc_type)
        if doc_type == "dd214":
            dob = _field(r"DATE OF BIRTH \(YYYYMMDD\):\s*(\d{8})", text)
            f.dob = _iso(dob) if dob else None
            dept = _field(r"COMPONENT AND BRANCH:\s*(.+)$", text) or ""
            branch_part, _, comp = dept.partition(" - ")
            start = _field(r"DATE ENTERED .*?:\s*(\d{6})", text)
            end = _field(r"SEPARATION DATE .*?:\s*(\d{6})", text)
            character = (_field(r"CHARACTER OF SERVICE:\s*(.+)$", text) or "").upper()
            f.service_period = ServicePeriod(
                branch=_BRANCHES.get(branch_part.strip().upper()),
                component=(comp.strip().lower() or "active")
                if comp.strip().lower() in ("active", "reserve", "guard")
                else "active",
                start=f"{start[:4]}-{start[4:6]}" if start else None,
                end=f"{end[:4]}-{end[4:6]}" if end else None,
                discharge=next((code for k, code in _DISCHARGES if k in character), None),
            )
            mos = _field(r"PRIMARY SPECIALTY:\s*(.+)$", text)
            f.mos = [mos] if mos else []
        elif doc_type == "rating_decision":
            f.decision_date = _iso(_field(r"DECISION DATE:\s*(.+)$", text) or "")
            ev = re.search(r"VA Form 21-(\w+), received (\d{2}/\d{2}/\d{4})", text)
            if ev:
                f.evidence_form, f.evidence_received = ev.group(1), _iso(ev.group(2))
            for cond, outcome, pct in re.findall(
                r"Service connection for (.+?) is (granted|denied|deferred)(?: with an evaluation of (\d+) percent)?\.",
                text,
            ):
                f.issues.append(
                    Issue(
                        condition=normalize_condition(cond),
                        outcome=outcome,
                        pct=int(pct) if pct else None,
                    )
                )
            combined = _field(r"COMBINED EVALUATION:\s*(\d+)%", text)
            f.combined_rating = int(combined) if combined else None
            sc = _field(r"SERVICE CONNECTED:\s*(.+)$", text) or ""
            for name, pct in re.findall(r"([A-Z][A-Z '/-]+?) (\d+)%", sc):
                f.sc_conditions.append(
                    RatedCondition(name=normalize_condition(name.lower()), rating_pct=int(pct))
                )
        elif doc_type == "notification_letter":
            f.letter_date = _iso(_field(r"Date of this letter:\s*(.+)$", text) or "")
            f.decision_date = _iso(_field(r"rating decision dated (.+?) *$", text) or "")
        elif doc_type == "claim_form":
            f.form = _field(r"VA FORM 21-(\w+)", text)
            f.filed = _iso(_field(r"DATE RECEIVED:\s*(\S+)", text) or "")
            conds = _field(r"CLAIMED CONDITIONS:\s*(.+)$", text) or ""
            f.conditions = [normalize_condition(c) for c in conds.split(";") if c.strip()]
        elif doc_type == "poa_form":
            f.rep_name = _field(r"^REPRESENTATIVE:\s*(.+)$", text)
            f.filed = _iso(_field(r"DATE SIGNED:\s*(\S+)", text) or "")
            kind = (_field(r"TYPE OF REPRESENTATIVE:\s*(.+)$", text) or "").lower()
            f.rep_kind = (
                "vso" if "organization" in kind else ("agent" if "agent" in kind else "attorney")
            )
        return f


# ------------------------------------------------------------------------------- DSPy


def _normalize(f: DocumentFacts) -> DocumentFacts:
    """Condition names as the offline path writes them, so merge and scoring compare alike."""
    for issue in f.issues:
        issue.condition = normalize_condition(issue.condition)
    for c in f.sc_conditions:
        c.name = normalize_condition(c.name)
    f.conditions = [normalize_condition(c) for c in f.conditions if c.strip()]
    return f


def make_dspy_extractor(lm):
    import dspy

    class ExtractCfileDocument(dspy.Signature):
        """Read one document from a veteran's VA claims file (C-file) and extract the facts a law
        firm's face note needs. Copy dates exactly (YYYY-MM-DD). Use plain VA condition names in
        lowercase ("tinnitus", "left knee condition"). Leave a field empty when the document does
        not state it; never guess."""

        doc_type_hint: str = dspy.InputField(desc="what a keyword triage thinks this document is")
        document_text: str = dspy.InputField()
        facts: DocumentFacts = dspy.OutputField()

    class DSPyExtractor:
        def __init__(self) -> None:
            # C-file text is PII: keep it out of DSPy's on-disk response cache. A per-call
            # option (dspy 3.4 reads `cache` off the call) rather than lm.copy(cache=False): a copy
            # loses the caller's history and a custom engine (DummyLM.copy swaps it out).
            self.predict = dspy.Predict(ExtractCfileDocument, cache=False)

        def extract(self, text: str, doc_type: DocType) -> DocumentFacts:
            with dspy.context(lm=lm):
                pred = self.predict(doc_type_hint=doc_type, document_text=text[:MAX_CHARS])
            facts: DocumentFacts = pred.facts
            if facts.doc_type == "other" and doc_type != "other":
                facts.doc_type = doc_type
            return _normalize(facts)

    return DSPyExtractor()


# ------------------------------------------------------------------------------- merge


def _has_period(sp: ServicePeriod | None) -> bool:
    # A letter asking for a DD-214 triages as one and reads as an empty period.
    return bool(sp and (sp.branch or sp.start or sp.end))


def merge(docs: list[DocumentFacts], names: list[str] | None = None) -> CfileFacts:
    """`names` label documents in `problems` (default "document N")."""
    names = names or [f"document {i}" for i in range(1, len(docs) + 1)]
    out = CfileFacts()
    seen_periods = set()
    for d, name in zip(docs, names, strict=True):
        if d._unparsed_issues:
            out.problems.append(
                f"{name}: could not read the decision on {', '.join(d._unparsed_issues)}. Check it by hand."
            )
        if d.doc_type == "dd214":
            if not (_has_period(d.service_period) or d.dob or d.mos):
                out.problems.append(
                    f"DD-214 unreadable (no key facts found): {name}. Read it by hand."
                )
                continue
            out.dob = out.dob or d.dob
            if _has_period(d.service_period):
                key = (d.service_period.branch, d.service_period.start, d.service_period.end)
                if key not in seen_periods:
                    seen_periods.add(key)
                    out.service_periods.append(d.service_period)
            out.mos += [m for m in d.mos if m not in out.mos]
        elif d.doc_type == "rating_decision" and not d.decision_date:
            # Never drop a decision quietly: its appeal deadline would vanish from the note.
            if d.issues or d.combined_rating is not None or d.sc_conditions:
                out.problems.append(
                    f"Rating decision with no readable decision date: {name}. Its appeal deadline "
                    "is not on the note; check it by hand."
                )
            else:
                out.problems.append(
                    f"Rating decision unreadable (no key facts found): {name}. Read it by hand."
                )
        elif d.doc_type == "poa_form" and d.rep_name:
            out.prior_reps.append(
                PriorRep(name=d.rep_name, kind=d.rep_kind or "attorney", signed=d.filed)
            )
    out.service_periods.sort(key=lambda p: p.start or "")

    letters = {
        d.decision_date: d.letter_date
        for d in docs
        if d.doc_type == "notification_letter" and d.decision_date
    }
    decisions = sorted(
        (d for d in docs if d.doc_type == "rating_decision" and d.decision_date),
        key=lambda d: d.decision_date or "",
    )
    for d in decisions:
        out.decisions.append(
            Decision(
                decision_date=d.decision_date or "",
                notified=letters.get(d.decision_date),
                form=d.evidence_form,
                filed=d.evidence_received,
                issues=d.issues,
            )
        )
    if decisions:
        newest = decisions[-1]
        out.combined_rating = newest.combined_rating
        out.sc_conditions = newest.sc_conditions

    decided_filings = {(d.evidence_form, d.evidence_received) for d in decisions}
    for d in docs:
        if (
            d.doc_type == "claim_form"
            and d.form
            and d.filed
            and (d.form, d.filed) not in decided_filings
        ):
            out.pending_filings.append(
                PendingFiling(form=d.form, filed=d.filed, conditions=d.conditions)
            )
    return out


def extract_cfile(
    pdfs: list[bytes], extractor: Extractor, names: list[str] | None = None
) -> tuple[CfileFacts, list[DocumentFacts], int]:
    """Returns (merged facts, per-document facts, number of documents skipped).

    Skipped: triaged out, or unreadable (corrupt or encrypted PDF, model output that won't parse).
    One bad document must not cost the whole note, so errors are caught per document; unreadable
    ones are listed in `facts.problems`, which the face note shows as flags."""
    names = names or [f"document {i}" for i in range(1, len(pdfs) + 1)]
    per_doc, read_names, unreadable, skipped = [], [], [], 0
    for data, name in zip(pdfs, names, strict=True):
        try:
            text = strip_ssns(pdf_text(data))
            if len(re.sub(r"\s", "", text)) < 50:  # most VBMS documents are scans
                skipped += 1
                unreadable.append(f"{name} has no text layer (a scan?). Read it by hand or OCR it.")
                continue
            doc_type = triage(text)
            if doc_type == "other":
                skipped += 1
                continue
            per_doc.append(extractor.extract(text, doc_type))
            read_names.append(name)
        except Exception as exc:
            skipped += 1
            unreadable.append(f"Could not read {name} ({type(exc).__name__}). Read it by hand.")
    facts = merge(per_doc, read_names)
    facts.problems = unreadable + facts.problems
    return facts, per_doc, skipped
