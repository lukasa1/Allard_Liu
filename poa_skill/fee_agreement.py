"""A GENERIC, SYNTHETIC attorney fee agreement plus conditions of costs.

Written for this demo from 38 CFR 14.636 and plain contingency-fee terms. It uses no real firm's
wording or names: the firm and attorney come from config/representative.json (placeholders).
It is not legal advice and not any firm's actual agreement.

The PDF is generated (no AcroForm). The last page is always the signature page, with fixed
places for the client's drawn signature and date and for the attorney's countersignature stamp.
"""

from io import BytesIO

from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from poa_skill.pdf.sign import stamp_signature_at, stamp_text_at

FORM_ID = "fee-agreement"
EDITION = "synthetic v1"
TITLE = "Attorney Fee Agreement and Conditions of Costs"
VA_WITHHOLDING_MAX_PCT = 20  # 38 CFR 14.636(h): VA pays the attorney directly only up to 20%
REQUIRED_CLIENT_FIELDS = {"first_name": "first name", "last_name": "last name"}
# 38 CFR 14.636(g)(1): the agreement must show the VA file number; with none, the SSN is the claim
# number. Either one is enough (`va_file_number` first).
CLAIM_NUMBER_FIELDS = ("va_file_number", "ssn")
CLAIM_NUMBER_LABEL = "VA file number or Social Security number"

# Signature page (points, bottom-left origin): [x0, y0, x1, y1].
CLIENT_SIG = [72, 560, 330, 590]
CLIENT_DATE = [400, 560, 540, 590]
ATTORNEY_SIG = [72, 440, 330, 470]
ATTORNEY_DATE = [400, 440, 540, 470]

_W, _H = LETTER
_MARGIN = 72
_FONT, _BOLD, _SIZE, _LEAD = "Times-Roman", "Times-Bold", 11, 14


def missing_fields(client: dict, fee_pct: int | None = 0) -> list[str]:
    gaps = [label for key, label in REQUIRED_CLIENT_FIELDS.items() if not client.get(key)]
    if not claim_number(client):
        gaps.append(CLAIM_NUMBER_LABEL)
    if fee_pct is None:
        gaps.append("fee percentage")
    return gaps


def claim_number(client: dict) -> str:
    """The VA file number line (14.636(g)(1)): the file number, else the SSN as the claim number.
    Raw PII from the vault: it goes only into the encrypted PDF."""
    if file_no := "".join(c for c in client.get("va_file_number") or "" if c.isdigit()):
        return f"VA file number: {file_no}"
    ssn = "".join(c for c in client.get("ssn") or "" if c.isdigit())
    return f"VA claim number (Social Security number): {ssn[:3]}-{ssn[3:5]}-{ssn[5:]}" if len(ssn) == 9 else ""


def _name(person: dict) -> str:
    parts = (person.get("first_name"), person.get("middle_initial"), person.get("last_name"))
    return " ".join(p for p in parts if p)


def sections(client: dict, rep: dict, fee_pct: int) -> list[tuple[str, str]]:
    """The agreement's text, as (heading, paragraph) pairs."""
    firm, attorney = rep.get("firm_name", "the Firm"), _name(rep)
    if fee_pct <= VA_WITHHOLDING_MAX_PCT:
        payment = (
            f"Because the fee is {fee_pct}% or less of past-due benefits and is contingent on a "
            "favorable result, the parties ask VA to withhold the fee from the past-due benefits "
            "and pay it directly to the Attorney (38 CFR 14.636(h)). The Client pays nothing out "
            "of pocket for the fee."
        )
    else:
        payment = (
            f"Because the fee is more than {VA_WITHHOLDING_MAX_PCT}% of past-due benefits, VA will "
            "not withhold it or pay the Attorney directly (38 CFR 14.636(h)). VA pays all "
            "past-due benefits to the Client, and the Client pays the fee directly to the Firm "
            "within 30 days of receiving them."
        )
    return [
        ("Parties", (
            f"This agreement is between {_name(client)} (the Client) and {attorney} of {firm} (the "
            "Attorney), who the Client appoints on VA Form 21-22a to represent the Client in claims "
            f"for VA benefits. {claim_number(client) or 'VA file number: (none on file)'}."
        )),
        ("Fee", (
            f"The fee is {fee_pct}% of any past-due benefits VA awards the Client on the claims the "
            "Attorney handles. It is a contingent fee: if VA awards no past-due benefits, the Client "
            "owes no fee. The Attorney charges only for services after VA's notice of its initial "
            "decision on a claim, as 38 CFR 14.636(c) requires."
        )),
        ("How the fee is paid", payment),
        ("Conditions of costs", (
            "Costs are not fees. Costs are out-of-pocket expenses such as fees for copies of private "
            "medical records or an independent medical opinion. The Attorney will ask the Client "
            "before incurring any cost. Approved costs are repaid from past-due benefits if any are "
            "awarded; if none are awarded, the Firm waives them. The Firm does not charge for its own "
            "overhead (postage, copying, telephone)."
        )),
        ("Ending the representation", (
            "The Client may discharge the Attorney at any time by telling the Firm in writing. Any fee "
            "for work already done is limited to what 38 CFR 14.636 allows."
        )),
        ("No guarantee", "The Attorney cannot promise any result, rating, amount or date. VA alone decides the claims."),
        ("Filing with VA", (
            "Within 30 days of signing, the Attorney sends a copy of this agreement to VA's Office of "
            "General Counsel, as 38 CFR 14.636(g) requires."
        )),
    ]


def render_draft(client: dict, rep: dict, fee_pct: int) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(TITLE)
    y = _H - _MARGIN

    def line(text: str, font: str = _FONT, size: float = _SIZE) -> None:
        nonlocal y
        if y < _MARGIN:
            c.showPage()
            y = _H - _MARGIN
        c.setFont(font, size)
        c.drawString(_MARGIN, y, text)
        y -= size + 3

    line(TITLE, _BOLD, 15)
    line("Synthetic sample for a demonstration: not a real firm's agreement.", _FONT, 9)
    y -= 8
    for heading, text in sections(client, rep, fee_pct):
        line(heading, _BOLD)
        for chunk in simpleSplit(text, _FONT, _SIZE, _W - 2 * _MARGIN):
            line(chunk)
        y -= 6
    c.showPage()  # the signature page: fixed places for both signatures
    c.setFont(_BOLD, 13)
    c.drawString(_MARGIN, _H - _MARGIN, "Signatures")
    c.setFont(_FONT, _SIZE)
    c.drawString(_MARGIN, 640, f"Fee: {fee_pct}% of past-due benefits, contingent. See page 1.")
    for label, sig, date in (("Client", CLIENT_SIG, CLIENT_DATE), ("Attorney", ATTORNEY_SIG, ATTORNEY_DATE)):
        c.line(sig[0], sig[1], sig[2], sig[1])
        c.line(date[0], date[1], date[2], date[1])
        who = _name(client) if label == "Client" else f"{_name(rep)}, {rep.get('firm_name', '')}"
        c.drawString(sig[0], sig[1] - 14, f"{label} signature: {who}")
        if label == "Client" and claim_number(client):
            c.drawString(sig[0], sig[1] - 28, claim_number(client))
        c.drawString(date[0], date[1] - 14, "Date")
    c.save()
    return buf.getvalue()


def _last_page(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages) - 1


def sign_draft(draft_pdf: bytes, signature_data_uri: str, signed_on_iso: str) -> bytes:
    page = _last_page(draft_pdf)
    dated = stamp_text_at(draft_pdf, page, CLIENT_DATE, _us_date(signed_on_iso), indent=4)
    return stamp_signature_at(dated, page, CLIENT_SIG, signature_data_uri)


def countersign(signed_pdf: bytes, attorney_name: str, signed_on_iso: str) -> bytes:
    page = _last_page(signed_pdf)
    stamped = stamp_text_at(signed_pdf, page, ATTORNEY_SIG, f"/s/ {attorney_name}", indent=4)
    return stamp_text_at(stamped, page, ATTORNEY_DATE, _us_date(signed_on_iso), indent=4)


def _us_date(iso: str) -> str:
    y, m, d = iso[:10].split("-")
    return f"{m}/{d}/{y}"
