"""
Signature overlay. /Sig AcroForm fields can't be "filled" as text: we draw the captured signature
(a drawn-PNG data URI) onto an overlay page at the /Sig widget's /Rect and merge it over the page.
This is a VISUAL signature plus an ESIGN/UETA adoption audit record (see documents.py), not a
cryptographic signature. Adjacent date fields are ordinary text fields (filled in fill.py).

Adapted from an earlier form engine.
"""

import base64
from io import BytesIO

from PIL import Image, ImageFilter
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Cap the stamped width so a short-and-wide rect (the 21-22a's ~350x25pt signature lines)
# yields a pen-sized signature, not a page-wide banner.
_MAX_SIG_WIDTH_PT = 160.0
# Breathing room around the ink so strokes don't touch the rect edges.
_INK_PAD_FRAC = 0.04
# Below this pt-per-source-px fit scale, capture strokes (~2.5 CSS px) thin to hairlines:
# dilate the alpha so the stamped stroke keeps ~1pt of visual weight.
_EMBOLDEN_SCALE = 0.12


def find_sig_widget(pdf_bytes: bytes, field_name: str) -> tuple[int, list[float]] | None:
    """Return (page_index, [x0,y0,x1,y1]) for the named signature widget, or None.
    `field_name` is the widget's partial name (/T), e.g. "SignatureField1[3]"."""
    reader = PdfReader(BytesIO(pdf_bytes))
    for pi, page in enumerate(reader.pages):
        for annot in page.get("/Annots") or []:
            o = annot.get_object()
            if o.get("/FT") in ("/Sig", "/Tx") and str(o.get("/T")) == field_name:
                return pi, [float(x) for x in o.get("/Rect")]
    return None


def decode_drawn(data_uri: str) -> Image.Image:
    raw = base64.b64decode(data_uri.split(",", 1)[1] if "," in data_uri else data_uri)
    return Image.open(BytesIO(raw)).convert("RGBA")


def trim_to_ink(img: Image.Image) -> Image.Image | None:
    """Crop to the alpha bounding box (+ a small pad), or None if the canvas holds no ink.

    Capture pads upload their full canvas; without trimming, canvas geometry (not the
    signature) decides the stamped size, and a tall phone canvas shrinks the mark to a dot."""
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return None
    left, top, right, bottom = bbox
    pad_x = max(2, round((right - left) * _INK_PAD_FRAC))
    pad_y = max(2, round((bottom - top) * _INK_PAD_FRAC))
    return img.crop(
        (
            max(0, left - pad_x),
            max(0, top - pad_y),
            min(img.width, right + pad_x),
            min(img.height, bottom + pad_y),
        )
    )


def _embolden(img: Image.Image, scale: float) -> Image.Image:
    """Dilate the ink so heavily downscaled captures keep a visible stroke weight. MaxFilter
    runs on alpha only; the color is re-sampled from the most opaque stroke pixel."""
    if scale >= _EMBOLDEN_SCALE:
        return img
    kernel = min(7, max(3, round(0.5 / scale)))
    if kernel % 2 == 0:
        kernel += 1
    alpha = img.getchannel("A").filter(ImageFilter.MaxFilter(kernel))
    thumb = img.resize((32, 32)) if img.width > 32 and img.height > 32 else img
    alpha_bytes = thumb.getchannel("A").tobytes()
    idx = max(range(len(alpha_bytes)), key=alpha_bytes.__getitem__)
    r, g, b, _ = thumb.getpixel((idx % thumb.width, idx // thumb.width))
    solid = Image.new("RGBA", img.size, (r, g, b, 255))
    solid.putalpha(alpha)
    return solid


def _overlay(pdf_bytes: bytes, page_index: int, draw) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    mb = reader.pages[page_index].mediabox
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(float(mb.width), float(mb.height)))  # bottom-left origin
    draw(c)
    c.save()
    overlay = PdfReader(BytesIO(buf.getvalue())).pages[0]
    writer = PdfWriter(clone_from=reader)
    writer.pages[page_index].merge_page(overlay)  # over=True default: signature on top
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _widget(pdf_bytes: bytes, field_name: str) -> tuple[int, list[float]]:
    loc = find_sig_widget(pdf_bytes, field_name)
    if not loc:
        raise ValueError(f"signature field {field_name!r} not found")
    return loc


def stamp_signature(pdf_bytes: bytes, field_name: str, data_uri: str) -> bytes:
    """Overlay a drawn signature into the named /Sig field's rect. Raises ValueError if the
    field is missing or the image holds no ink: a signing step must never silently no-op."""
    return stamp_signature_at(pdf_bytes, *_widget(pdf_bytes, field_name), data_uri)


def stamp_signature_at(pdf_bytes: bytes, page_index: int, rect: list[float], data_uri: str) -> bytes:
    """Overlay a drawn signature into `rect` ([x0, y0, x1, y1], points) on one page: for
    generated PDFs, which have no signature widgets."""
    x0, y0, x1, y1 = rect
    img = trim_to_ink(decode_drawn(data_uri))
    if img is None:
        raise ValueError("signature image is blank")
    fit_w, fit_h = min(x1 - x0, _MAX_SIG_WIDTH_PT), y1 - y0
    img = _embolden(img, min(fit_w / img.width, fit_h / img.height))

    def draw(c):
        # anchor="sw" seats the signature on the printed line at the rect's left edge.
        c.drawImage(
            ImageReader(img), x0, y0, width=fit_w, height=fit_h,
            preserveAspectRatio=True, anchor="sw", mask="auto",
        )  # fmt: skip

    return _overlay(pdf_bytes, page_index, draw)


def stamp_text(pdf_bytes: bytes, field_name: str, text: str, indent: float = 120) -> bytes:
    """Print plain text (e.g. "N/A", or an attorney's countersignature) into a /Sig field's
    rect: signature boxes can't hold AcroForm text, so an overlay is the only way."""
    return stamp_text_at(pdf_bytes, *_widget(pdf_bytes, field_name), text, indent)


def stamp_text_at(pdf_bytes: bytes, page_index: int, rect: list[float], text: str, indent: float = 0) -> bytes:
    x0, y0, _, y1 = rect
    rh = y1 - y0

    def draw(c):
        c.setFont("Times-Roman", min(14, rh * 0.6))
        c.drawString(x0 + indent, y0 + rh * 0.3, text)

    return _overlay(pdf_bytes, page_index, draw)
