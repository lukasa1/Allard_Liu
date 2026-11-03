import io
import json
from pathlib import Path

import pypdf

from poa_skill import form_21_22a as form
from poa_skill.pdf.fill import UnknownFormField, fill_acroform
from poa_skill.service import load_representative

REP = load_representative()
VET = {
    "first_name": "Jordan", "middle_initial": "Q", "last_name": "Testveteran",
    "ssn": "123456789", "date_of_birth": "1988-04-09", "branch": "marine_corps",
    "va_file_number": "", "address": {"line1": "100 Main St", "line2": "4B", "city": "Milwaukee",
    "state": "WI", "zip": "532021234"}, "phone": "4145550100", "email": "jordan@example.com",
}  # fmt: skip


def _fields(pdf: bytes) -> dict:
    return {
        k.split(".")[-1]: v.get("/V")
        for k, v in pypdf.PdfReader(io.BytesIO(pdf)).get_fields().items()
    }


def test_every_mapped_field_exists_in_the_blank():
    # strict=True inside render_draft raises if VA renamed any field.
    form.render_draft(VET, REP, form.Consents(True, True))


def test_veteran_and_firm_values_land_in_the_right_boxes():
    f = _fields(form.render_draft(VET, REP, form.Consents(True, False)))
    assert f["Veterans_Last_Name[0]"] == "TESTVETERAN"
    assert f["SocialSecurityNumber_LastFourNumbers[2]"] == "6789"  # page-3 header
    assert f["MailingAddress_ZIPOrPostalCode_LastFourNumbers[0]"] == "1234"
    assert f["Last_Name[0]"] == "1"
    assert f["MailingAddress_NumberAndStreet[2]"] == "PO BOX 100"
    assert f["Telephone_Middle_Three_Numbers[1]"] == "555"
    assert f["Provide_The_Name_Of_The_Firm_Or_Organization_Here[0]"] == "Law Firm"
    assert "Attorney 3" in f["Provide_The_Names_Of_The_Individuals_Here[0]"]
    assert f["AuthorizationForRepAccessToRecords[0]"] == "/1"
    assert f.get("AuthorizationForRepActClaimantsBehalf[0]") in (None, "/Off")


def test_radio_buttons_are_visibly_selected():
    pdf = form.render_draft(VET, REP, form.Consents(False, False))
    selected = {}
    for a in pypdf.PdfReader(io.BytesIO(pdf)).pages[0]["/Annots"]:
        a = a.get_object()
        if a.get("/AS") not in (None, "/Off") and "/Parent" in a:
            selected[str(a["/Parent"].get_object()["/T"])] = (
                a["/AS"],
                a["/Parent"].get_object()["/V"],
            )
    assert selected["RadioButtonList[1]"] == ("/3", "/3")  # Marine Corps
    assert selected["RadioButtonList[0]"] == ("/0", "/0")  # Attorney


def test_missing_lists_required_fields_and_unanswered_consents():
    missing = form.missing_fields({"first_name": "A"}, form.Consents())
    assert "Social Security number" in missing
    assert any("Item 20" in m for m in missing) and any("Item 22" in m for m in missing)
    assert form.missing_fields(VET, form.Consents(False, False)) == []


def test_strict_fill_rejects_unknown_field_names():
    try:
        fill_acroform(form.BLANK_PDF.read_bytes(), {"not_a_field": "x"}, strict=True)
    except UnknownFormField as e:
        assert e.missing == ["not_a_field"]
    else:
        raise AssertionError("expected UnknownFormField")


def test_representative_config_is_valid_json_with_required_keys():
    rep = json.loads(Path("config/representative.json").read_text())
    for k in ("first_name", "last_name", "type", "address", "phone", "firm_name"):
        assert rep[k]
