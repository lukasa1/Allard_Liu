"""
AcroForm text/checkbox/radio filling via pypdf. All pypdf coupling lives here and in sign.py.
Keys in `values` are fully-qualified PDF field names (what PdfReader.get_fields() returns);
checkbox/radio values are the literal export token (e.g. "/1").

Adapted from an earlier form engine.
"""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject


class UnknownFormField(ValueError):
    """A mapping addressed field names the blank does not carry. Raised under strict=True so a
    new VA form edition (which can rename fields) never ships a PDF with silent blanks."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"{len(missing)} field name(s) not in this PDF: {', '.join(missing[:6])}")


def field_names(pdf_bytes: bytes) -> set[str]:
    return set((PdfReader(BytesIO(pdf_bytes)).get_fields() or {}).keys())


def _qualified_name(obj) -> str:
    parts = []
    while obj is not None:
        if "/T" in obj:
            parts.insert(0, str(obj["/T"]))
        obj = obj.get("/Parent")
        obj = obj.get_object() if obj is not None else None
    return ".".join(parts)


def _select_radio_appearances(writer: PdfWriter, values: dict[str, str]) -> None:
    """pypdf writes a radio group's /V as a text string ("(/0)", not the name /0) and leaves each
    kid widget's /AS untouched, so viewers show no box selected. Store /V as a name and point
    every kid's /AS at the chosen state or /Off."""
    for page in writer.pages:
        for annot in page.get("/Annots") or []:
            w = annot.get_object()
            parent = w.get("/Parent")
            if parent is None or "/T" in w:
                continue
            group = _qualified_name(parent.get_object())
            if group not in values:
                continue
            states = [s for s in (w.get("/AP", {}).get("/N", {}) or {}) if s != "/Off"]
            if not states:
                continue
            chosen = values[group]
            parent.get_object()[NameObject("/V")] = NameObject(chosen)
            w[NameObject("/AS")] = NameObject(states[0] if states[0] == chosen else "/Off")


def fill_acroform(pdf_bytes: bytes, values: dict[str, str], *, strict: bool = False) -> bytes:
    """Fill AcroForm fields and set /NeedAppearances so values render in every viewer and print.

    Empty/None values are dropped (the field stays blank). strict=True raises UnknownFormField
    when any non-empty value targets a name absent from the PDF (pypdf would silently no-op it).
    """
    clean = {k: v for k, v in values.items() if v is not None and v != ""}
    if strict and clean:
        missing = sorted(k for k in clean if k not in field_names(pdf_bytes))
        if missing:
            raise UnknownFormField(missing)
    # clone_from (not .append): keeps the original /AcroForm field tree intact.
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf_bytes)))
    # Fill on every page: VA forms repeat some fields (the SSN page header) across pages.
    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, clean, auto_regenerate=False)
        except Exception:  # noqa: BLE001, S112 (a page without those fields just no-ops)
            continue
    _select_radio_appearances(writer, clean)
    # Some PDFs carry an orphan twin of a field in /Fields; set /V on every same-name entry so
    # the field tree and the page widget agree.
    acro = writer._root_object.get("/AcroForm")
    if acro is not None:
        for ref in acro.get_object().get("/Fields") or []:
            o = ref.get_object()
            v = clean.get(str(o.get("/T")))
            if v is not None:
                o[NameObject("/V")] = (
                    NameObject(v)
                    if isinstance(v, str) and v.startswith("/")
                    else TextStringObject(v)
                )
    # The load-bearing gotcha: VA forms are LiveCycle XFA hybrids. We fill the AcroForm layer,
    # but XFA-aware viewers (Chrome/PDFium, Acrobat) prefer the XFA datasets, which still hold
    # the original empty values, so the filled form renders blank. Dropping /XFA demotes the
    # file to a plain AcroForm PDF and every viewer shows what we wrote.
    acro = writer._root_object.get("/AcroForm")
    if acro is not None:
        acro = acro.get_object()
        if "/XFA" in acro:
            del acro["/XFA"]
    # Without /NeedAppearances pypdf writes /V but not /AP, so some viewers (and printing) would
    # still show blanks. This tells conformant viewers to regenerate appearances.
    writer.set_need_appearances_writer(True)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
