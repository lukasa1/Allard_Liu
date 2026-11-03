"""Generate a synthetic C-file (a folder of PDFs) for a persona, plus the Benefits Documents stub.

Real C-files are one large zip of many PDFs pulled from VBMS. This produces a small, readable
stand-in with the documents a face note is built from (DD-214s, rating decisions with narrative
and code sheet, notification letters, filing forms, prior 21-22a/21-22) plus one irrelevant
document, so the pipeline has to pick what matters. Every value is synthetic.

`DocumentsStub` mimics VA's Benefits Documents API (search a veteran's eFolder, download a
document), which is VA-internal. Once Ben's sample C-files arrive, point `CFILE_DIR` (or
`intake facenote --cfile DIR`) at a folder of real-shaped PDFs instead.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from agent.cfile.facts import CfileFacts, Decision, truth_facts
from agent.intake.schema import RatedCondition
from agent.personas import Persona

BRANCH_UPPER = {
    "army": "ARMY", "navy": "NAVY", "air force": "AIR FORCE", "marine corps": "MARINE CORPS",
    "coast guard": "COAST GUARD", "space force": "SPACE FORCE",
}  # fmt: skip
DISCHARGE_UPPER = {
    "honorable": "HONORABLE", "general": "GENERAL (UNDER HONORABLE CONDITIONS)",
    "oth": "UNDER OTHER THAN HONORABLE CONDITIONS", "bad_conduct": "BAD CONDUCT",
    "dishonorable": "DISHONORABLE", "uncharacterized": "UNCHARACTERIZED",
}  # fmt: skip


def _us(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def _long(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%B %d, %Y").replace(" 0", " ")


def _pdf(title: str, lines: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title)
    y = 740
    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, y, title)
    y -= 24
    c.setFont("Helvetica", 10)
    for line in lines:
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = 740
        c.drawString(54, y, line)
        y -= 15
    c.save()
    return buf.getvalue()


def _code_sheet(decision: Decision, prior: list[RatedCondition]) -> list[RatedCondition]:
    """Service-connected list after this decision: earlier grants plus this decision's."""
    current = {c.name: c.rating_pct for c in prior}
    for issue in decision.issues:
        if issue.outcome == "granted":
            current[issue.condition] = issue.pct
    return [RatedCondition(name=n, rating_pct=v) for n, v in current.items()]


def _combined(conditions: list[RatedCondition]) -> int:
    """VA's combined ratings table ("whole person" method), rounded to the nearest 10."""
    remaining = 100.0
    for pct in sorted((c.rating_pct or 0 for c in conditions), reverse=True):
        remaining -= remaining * pct / 100
    return int(round((100 - remaining) / 10.0) * 10)


def build_documents(p: Persona, facts: CfileFacts | None = None) -> list[tuple[str, str, bytes]]:
    """[(doc_type, subject, pdf_bytes)] for the persona's synthetic C-file."""
    f = facts or truth_facts(p)
    t = p.truth
    name = f"{(t.last_name or '').upper()}, {(t.first_name or '').upper()}"
    ssn = p.identity.get("ssn", "")
    dob = (f.dob or "").replace("-", "")
    docs: list[tuple[str, str, bytes]] = []

    for i, sp in enumerate(f.service_periods):
        mos = f.mos[i] if i < len(f.mos) else (f.mos[-1] if f.mos else "")
        lines = [
            "DD FORM 214 - CERTIFICATE OF RELEASE OR DISCHARGE FROM ACTIVE DUTY",
            f"1. NAME (Last, First): {name}",
            (
                f"2. DEPARTMENT, COMPONENT AND BRANCH: {BRANCH_UPPER.get(sp.branch or '', '')} - "
                f"{(sp.component or 'active').upper()}"
            ),
            f"3. SOCIAL SECURITY NUMBER: {ssn}",
            f"5. DATE OF BIRTH (YYYYMMDD): {dob}",
            f"11. PRIMARY SPECIALTY: {mos}",
            f"12a. DATE ENTERED ACTIVE DUTY THIS PERIOD (YYYYMMDD): {(sp.start or '').replace('-', '')}01",
            f"12b. SEPARATION DATE THIS PERIOD (YYYYMMDD): {(sp.end or '').replace('-', '')}28",
            f"24. CHARACTER OF SERVICE: {DISCHARGE_UPPER.get(sp.discharge or '', 'UNKNOWN')}",
            "28. NARRATIVE REASON FOR SEPARATION: COMPLETION OF REQUIRED SERVICE",
        ]
        docs.append(
            (
                "dd214",
                f"DD 214 Certificate of Release or Discharge ({i + 1})",
                _pdf("DD 214", lines),
            )
        )

    sc: list[RatedCondition] = []
    for d in f.decisions:
        sc = _code_sheet(d, sc)
        decided = [
            f"{n}. Service connection for {iss.condition} is {iss.outcome}"
            + (f" with an evaluation of {iss.pct} percent." if iss.outcome == "granted" else ".")
            for n, iss in enumerate(d.issues, 1)
        ]
        periods = "; ".join(
            f"{(sp.branch or '').title()} from {sp.start} to {sp.end}" for sp in f.service_periods
        )
        lines = [
            "DEPARTMENT OF VETERANS AFFAIRS - RATING DECISION",
            f"NAME OF VETERAN: {name}",
            f"DECISION DATE: {_long(d.decision_date)}",
            "",
            "EVIDENCE:",
            f"- VA Form 21-{d.form or '526EZ'}, received {_us(d.filed)}",
            "- Service treatment records",
            "",
            "DECISION:",
            *decided,
            "",
            "NARRATIVE:",
            f"The veteran served in the {periods}.",
            "",
            "CODE SHEET",
            f"COMBINED EVALUATION: {_combined(sc)}%",
            "SERVICE CONNECTED: " + "; ".join(f"{c.name.upper()} {c.rating_pct}%" for c in sc),
        ]
        docs.append(
            (
                "rating_decision",
                f"Rating Decision {_us(d.decision_date)}",
                _pdf("Rating Decision", lines),
            )
        )
        if d.notified:
            letter_lines = [
                "DEPARTMENT OF VETERANS AFFAIRS",
                f"Date of this letter: {_long(d.notified)}",
                f"Dear {t.first_name} {t.last_name},",
                f"We made a decision on your claim. The rating decision dated {_long(d.decision_date)}",
                "is enclosed. This letter tells you what we decided and how to ask for a review.",
                "You have one year from the date of this letter to request a decision review.",
            ]
            docs.append(
                (
                    "notification_letter",
                    f"Notification Letter {_us(d.notified)}",
                    _pdf("Notification Letter", letter_lines),
                )
            )
        if d.filed:
            claim_lines = [
                f"VA FORM 21-{d.form or '526EZ'} - APPLICATION FOR DISABILITY COMPENSATION",
                f"VETERAN: {name}",
                f"DATE RECEIVED: {_us(d.filed)}",
                "CLAIMED CONDITIONS: " + "; ".join(i.condition for i in d.issues),
            ]
            docs.append(
                (
                    "claim_form",
                    f"VA 21-{d.form or '526EZ'} {_us(d.filed)}",
                    _pdf(f"VA Form 21-{d.form or '526EZ'}", claim_lines),
                )
            )

    for pf in f.pending_filings:
        claim_lines = [
            f"VA FORM 21-{pf.form} - APPLICATION FOR DISABILITY COMPENSATION",
            f"VETERAN: {name}",
            f"DATE RECEIVED: {_us(pf.filed)}",
            "CLAIMED CONDITIONS: " + "; ".join(pf.conditions),
        ]
        docs.append(
            (
                "claim_form",
                f"VA 21-{pf.form} {_us(pf.filed)}",
                _pdf(f"VA Form 21-{pf.form}", claim_lines),
            )
        )

    for rep in f.prior_reps:
        form_id = "21-22" if rep.kind == "vso" else "21-22a"
        kind = {
            "vso": "Veterans Service Organization",
            "attorney": "Attorney",
            "agent": "Claims Agent",
        }[rep.kind]
        lines = [
            f"VA FORM {form_id} - APPOINTMENT OF {'VETERANS SERVICE ORGANIZATION' if rep.kind == 'vso' else 'INDIVIDUAL'} AS CLAIMANT'S REPRESENTATIVE",
            f"VETERAN: {name}",
            f"REPRESENTATIVE: {rep.name}",
            f"TYPE OF REPRESENTATIVE: {kind}",
            f"DATE SIGNED: {_us(rep.signed)}",
        ]
        if rep.revoked:
            lines.append(f"REVOCATION: the claimant revoked this appointment on {_us(rep.revoked)}")
        docs.append(("poa_form", f"VA {form_id} {rep.name}", _pdf(f"VA Form {form_id}", lines)))

    docs.append((
        "other",
        "Service Treatment Records",
        _pdf("Service Treatment Records", ["SICK CALL NOTE", "Patient seen for routine physical. No acute findings.", "Immunizations up to date."]),
    ))  # fmt: skip
    return docs


class DocumentsStub:
    """Stand-in for VA's Benefits Documents API (VA-internal): list and download a C-file."""

    mode = "stub"

    def __init__(self, root: Path) -> None:
        self.root = root

    def _folder(self, icn: str) -> Path:
        return self.root / icn

    @staticmethod
    def _spec_hash(p: Persona) -> str:
        """Everything build_documents reads, so an edited persona doesn't serve a stale C-file."""
        spec = {
            "facts": truth_facts(p).model_dump(),
            "name": [p.truth.first_name, p.truth.last_name],
            "ssn": p.identity.get("ssn", ""),
        }
        return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()

    def ensure(self, p: Persona) -> Path:
        """Write the persona's synthetic C-file; rewrite it when the persona's spec changes.

        The spec hash sits next to index.json (index.json stays the plain search() listing)."""
        folder = self._folder(p.icn)
        index, stamp = folder / "index.json", folder / "spec.sha256"
        spec_hash = self._spec_hash(p)
        if index.exists() and stamp.exists() and stamp.read_text() == spec_hash:
            return folder
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.pdf"):  # documents the new spec may no longer have
            old.unlink()
        entries = []
        for n, (doc_type, subject, pdf) in enumerate(build_documents(p), 1):
            doc_id = hashlib.sha256(f"{p.icn}{n}{subject}".encode()).hexdigest()[:16]
            (folder / f"{doc_id}.pdf").write_bytes(pdf)
            entries.append(
                {"documentId": doc_id, "subject": subject, "docTypeHint": doc_type, "pages": 1}
            )
        index.write_text(json.dumps(entries, indent=2))
        stamp.write_text(spec_hash)
        return folder

    def search(self, icn: str) -> list[dict]:
        index = self._folder(icn) / "index.json"
        if not index.exists():
            return []
        return json.loads(index.read_text())

    def download(self, icn: str, document_id: str) -> bytes:
        path = self._folder(icn) / f"{document_id}.pdf"
        if not path.exists():
            raise FileNotFoundError(document_id)
        return path.read_bytes()
