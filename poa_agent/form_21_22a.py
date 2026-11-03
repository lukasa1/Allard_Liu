"""VA Form 21-22a (Appointment of Individual as Claimant's Representative, JUL 2023 edition).

Maps three inputs onto the blank's AcroForm fields:
  veteran        the veteran's identity (from the encrypted vault, see vault.py)
  representative the appointed attorney/agent and firm (config/representative.json)
  consents       the veteran's explicit answers to Items 20 and 22

Field names below were read from the VA blank (forms/VBA-21-22A-ARE.pdf) with pypdf. The
mapping runs strict: if VA ships an edition that renames a field, fill raises instead of
producing a form with silent blanks.

Section II (claimant other than the veteran) is out of scope: the veteran is the claimant.
"""

from dataclasses import dataclass
from pathlib import Path

from poa_agent.pdf import transforms as t
from poa_agent.pdf.fill import fill_acroform
from poa_agent.pdf.sign import stamp_signature, stamp_text

BLANK_PDF = Path(__file__).parent / "forms" / "VBA-21-22A-ARE.pdf"
FORM_ID = "va-21-22a"
EDITION = "JUL 2023"

_P0 = "form1[0].#subform[0]."
_P1 = "form1[0].#subform[1]."
_P2 = "form1[0].#subform[2]."

# Signature widgets (partial /T names, unique across the form).
VETERAN_SIG_FIELD = "SignatureField1[3]"  # 23A, page 3: the signature that matters
REP_SIG_FIELD = "SignatureField1[2]"  # 25A, signed later by the representative
SEC_14_630_SIG_FIELDS = ("SignatureField1[0]", "SignatureField1[1]")  # 17A / 18A

# Item 6 radio states, in the order the boxes are printed.
BRANCHES = {
    "army": "/0",
    "navy": "/1",
    "air_force": "/2",
    "marine_corps": "/3",
    "coast_guard": "/4",
    "space_force": "/5",
    "noaa": "/6",
    "usphs": "/7",
}
# Item 16B radio states.
REP_TYPES = {"attorney": "/0", "agent": "/1", "individual_14_630": "/2", "vso_representative": "/3"}

CHECKED = "/1"

# Required for a clean, fileable 21-22a: field -> plain-language label (drives `missing`).
REQUIRED_VETERAN_FIELDS = {
    "first_name": "first name",
    "last_name": "last name",
    "ssn": "Social Security number",
    "date_of_birth": "date of birth",
    "branch": "branch of service",
    "address.line1": "street address",
    "address.city": "city",
    "address.state": "state",
    "address.zip": "ZIP code",
}


@dataclass
class Consents:
    """The veteran's own answers. None means "not asked yet" and blocks preparing the form."""

    authorize_7332_records: bool | None = None  # Item 20
    authorize_address_change: bool | None = None  # Item 22


def _get(d: dict, dotted: str):
    for part in dotted.split("."):
        d = (d or {}).get(part) if isinstance(d, dict) else None
    return d


def missing_veteran_fields(veteran: dict) -> list[str]:
    return [label for key, label in REQUIRED_VETERAN_FIELDS.items() if not _get(veteran, key)]


def missing_fields(veteran: dict, consents: Consents) -> list[str]:
    missing = missing_veteran_fields(veteran)
    if consents.authorize_7332_records is None:
        missing.append("answer to Item 20 (sensitive records access)")
    if consents.authorize_address_change is None:
        missing.append("answer to Item 22 (address changes)")
    return missing


def _ssn_fields(ssn: str | None) -> dict[str, str]:
    a, b, c = t.split_ssn(ssn)
    out = {}
    # Item 2 on page 1, plus the "VETERAN'S SOCIAL SECURITY NO." header on pages 2 and 3.
    for prefix, i in ((_P0, 0), (_P1, 1), (_P2, 2)):
        out[f"{prefix}SocialSecurityNumber_FirstThreeNumbers[{i}]"] = a
        out[f"{prefix}SocialSecurityNumber_SecondTwoNumbers[{i}]"] = b
        out[f"{prefix}SocialSecurityNumber_LastFourNumbers[{i}]"] = c
    return out


def _address_fields(prefix: str, i: int, addr: dict | None) -> dict[str, str]:
    addr = addr or {}
    z5, z4 = t.split_zip(addr.get("zip"))
    return {
        f"{prefix}MailingAddress_NumberAndStreet[{i}]": t.fit(
            (addr.get("line1") or "").upper(), 30, "street"
        ),
        f"{prefix}MailingAddress_ApartmentOrUnitNumber[{i}]": t.fit(
            (addr.get("line2") or "").upper(), 5, "apt"
        ),
        f"{prefix}MailingAddress_City[{i}]": t.fit((addr.get("city") or "").upper(), 18, "city"),
        f"{prefix}MailingAddress_StateOrProvince[{i}]": t.us_state_code(addr.get("state")),
        f"{prefix}MailingAddress_Country[{i}]": t.us_country(addr),
        f"{prefix}MailingAddress_ZIPOrPostalCode_FirstFiveNumbers[{i}]": z5,
        f"{prefix}MailingAddress_ZIPOrPostalCode_LastFourNumbers[{i}]": z4,
    }


def _phone_fields(prefix: str, area: int, mid: int, last: int, phone: str | None) -> dict:
    a, b, c = t.split_phone(phone)
    return {
        f"{prefix}Telephone_Number_Area_Code[{area}]": a,
        f"{prefix}Telephone_Middle_Three_Numbers[{mid}]": b,
        f"{prefix}Telephone_Last_Four_Numbers[{last}]": c,
    }


def build_fields(veteran: dict, rep: dict, consents: Consents) -> dict[str, str]:
    v = veteran
    f: dict[str, str] = {}

    # ── Section I: veteran ────────────────────────────────────────────────────────────────
    f[_P0 + "Veterans_First_Name[0]"] = t.person_name(v.get("first_name"), 12, "first name")
    f[_P0 + "Veterans_Middle_Initial[0]"] = t.person_name(v.get("middle_initial"), 1, "MI")
    f[_P0 + "Veterans_Last_Name[0]"] = t.person_name(v.get("last_name"), 18, "last name")
    f.update(_ssn_fields(v.get("ssn")))
    # Item 3 (VA file number) is the widget VA named "...Service_Number...[0]"; item 5 is [1].
    f[_P0 + "Veterans_Service_Number_If_Applicable[0]"] = t.fit(
        t._digits(v.get("va_file_number")), 9, "VA file number"
    )
    f[_P0 + "Veterans_Service_Number_If_Applicable[1]"] = t.fit(
        v.get("service_number"), 10, "service number"
    )
    m, d, y = t.split_dob(v.get("date_of_birth"))
    f[_P0 + "Date_Of_Birth_Month[0]"], f[_P0 + "Date_Of_Birth_Day[0]"] = m, d
    f[_P0 + "Date_Of_Birth_Year[0]"] = y
    branch = BRANCHES.get((v.get("branch") or "").lower())
    if branch:
        f[_P0 + "RadioButtonList[1]"] = branch
    f.update(_address_fields(_P0, 0, v.get("address")))
    f.update(_phone_fields(_P0, 1, 0, 1, v.get("phone")))  # item 8 widgets carry these indexes
    f[_P0 + "E_Mail_Address_Optional[1]"] = v.get("email") or ""  # item 9

    # ── Section III: appointed representative ─────────────────────────────────────────────
    f[_P0 + "Name_Of_Individual_Appointed_As_Representative_First_Name[0]"] = t.person_name(
        rep.get("first_name"), 12, "rep first name"
    )
    f[_P0 + "Middle_Initial[0]"] = t.person_name(rep.get("middle_initial"), 1, "rep MI")
    f[_P0 + "Last_Name[0]"] = t.person_name(rep.get("last_name"), 18, "rep last name")
    f[_P0 + "RadioButtonList[0]"] = REP_TYPES[rep.get("type", "attorney")]
    f.update(_address_fields(_P1, 2, rep.get("address")))
    f.update(_phone_fields(_P1, 2, 1, 2, rep.get("phone")))
    f[_P1 + "E_Mail_Address_Of_Individual_Appointed_As_Claimants_Representative_Optional[0]"] = (
        rep.get("email") or ""
    )

    # ── Section IV: authorizations ────────────────────────────────────────────────────────
    box19 = (
        _P1
        + "Checkbox_I_Authorize_VA_To_Disclose_All_My_Records_Other_Than_As_Provided_In_Items_20_And_21"
    )
    if rep.get("authorize_affiliated_it_access"):
        f[box19 + "[0]"] = CHECKED
        f[_P1 + "Provide_The_Name_Of_The_Firm_Or_Organization_Here[0]"] = rep.get("firm_name", "")
    if rep.get("authorize_affiliated_staff"):
        f[box19 + "[1]"] = CHECKED
        f[_P1 + "Provide_The_Names_Of_The_Individuals_Here[0]"] = ", ".join(
            rep.get("affiliated_staff") or []
        )
    if consents.authorize_7332_records:
        f[_P1 + "AuthorizationForRepAccessToRecords[0]"] = CHECKED
    if consents.authorize_address_change:
        f[_P1 + "AuthorizationForRepActClaimantsBehalf[0]"] = CHECKED
    return f


def render_draft(veteran: dict, rep: dict, consents: Consents) -> bytes:
    """The unsigned draft: every field filled, 17A/18A marked N/A when Section 14.630 doesn't
    apply (the firm's practice), 23A left empty for the veteran's click-to-sign."""
    pdf = fill_acroform(BLANK_PDF.read_bytes(), build_fields(veteran, rep, consents), strict=True)
    if not rep.get("representation_under_14_630"):
        for name in SEC_14_630_SIG_FIELDS:
            pdf = stamp_text(pdf, name, "N/A")
    return pdf


def sign_draft(draft_pdf: bytes, signature_data_uri: str, signed_on_iso: str) -> bytes:
    """Stamp the veteran's saved signature into 23A and date 23B (MM/DD/YYYY)."""
    m, d, y = t.split_dob(signed_on_iso)
    dated = fill_acroform(
        draft_pdf,
        {
            _P2 + "Date_Signed_Month[3]": m,
            _P2 + "Date_Signed_Day[3]": d,
            _P2 + "Date_Signed_Year[3]": y,
        },
        strict=True,
    )
    return stamp_signature(dated, VETERAN_SIG_FIELD, signature_data_uri)
