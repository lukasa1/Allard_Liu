"""The signing workflow for the representation documents, shared by the agent's tools and the
host app: VA Form 21-22a and the (synthetic) fee agreement, each a `FormKind`.

Who can do what is the security model:
  agent  asks for secure capture, prepares/edits the draft, offers it for signature.
  user   types PII into the secure form, draws a signature, clicks Sign.
  staff  countersigns a signed document (one action for both documents in the demo).
The agent has no path to raw PII and no way to sign: `sign()` is only reachable from the host's
click handler, which records the user's own intent, and `countersign()` from the staff panel.
"""

import json
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from poa_skill import fee_agreement
from poa_skill import form_21_22a as form
from poa_skill.documents import Document, DocumentStore, now_iso, sha256
from poa_skill.vault import DEFAULT_DATA_DIR, FIELDS, Vault

REP_CONFIG = Path(__file__).resolve().parent.parent / "config" / "representative.json"

# Shown on the Sign button's card and recorded verbatim in the audit trail, one per form.
ESIGN_CONSENT = (
    "By clicking Sign, I adopt my saved signature as my signature on this VA Form 21-22a, "
    "appointing the representative named in Item 16A, and I agree to sign electronically."
)
FEE_ESIGN_CONSENT = (
    "By clicking Sign, I adopt my saved signature as my signature on this Attorney Fee Agreement "
    "and Conditions of Costs, I agree to its fee and cost terms, and I agree to sign electronically."
)

# Fields the agent or the user may change on a draft without the secure form. Secret fields
# (SSN, date of birth, file/service numbers) only change through a new secure-capture request.
EDITABLE = {n for n, s in FIELDS.items() if s.sensitivity != "secret"}
CONSENT_KEYS = ("authorize_7332_records", "authorize_address_change")


class WorkflowError(ValueError):
    pass


@dataclass(frozen=True)
class FormKind:
    """One signable document: how it is rendered, what it needs, how it is signed and
    countersigned, and the e-sign consent the signer is shown."""

    key: str  # "21-22a" | "fee_agreement"
    label: str
    form_id: str
    edition: str
    consent: str
    missing: Callable[[dict, "Document"], list[str]]  # (veteran, doc) -> plain-language gaps
    render: Callable[[dict, dict, "Document"], bytes]  # (veteran, rep, doc) -> draft PDF
    sign: Callable[[bytes, str, str], bytes]  # (draft, signature data URI, ISO date)
    countersign: Callable[[bytes, str, str], bytes]  # (signed, attorney name, ISO date)


FORMS: dict[str, FormKind] = {
    "21-22a": FormKind(
        "21-22a", "VA 21-22a", form.FORM_ID, form.EDITION, ESIGN_CONSENT,
        missing=lambda v, d: form.missing_fields(v, form.Consents(**d.consents)),
        render=lambda v, rep, d: form.render_draft(v, rep, form.Consents(**d.consents)),
        sign=form.sign_draft, countersign=form.countersign,
    ),
    "fee_agreement": FormKind(
        "fee_agreement", fee_agreement.TITLE, fee_agreement.FORM_ID, fee_agreement.EDITION, FEE_ESIGN_CONSENT,
        missing=lambda v, d: fee_agreement.missing_fields(v, d.terms.get("fee_pct")),
        render=lambda v, rep, d: fee_agreement.render_draft(v, rep, d.terms["fee_pct"]),
        sign=fee_agreement.sign_draft, countersign=fee_agreement.countersign,
    ),
}  # fmt: skip
_BY_FORM_ID = {k.form_id: k for k in FORMS.values()}


def kind_of(doc: "Document") -> FormKind:
    return _BY_FORM_ID[doc.form_id]


def load_representative(path: Path = REP_CONFIG) -> dict:
    return json.loads(path.read_text())


class PoaService:
    def __init__(self, session_id: str, data_dir: Path = DEFAULT_DATA_DIR, rep: dict | None = None):
        self.session_id = session_id
        self.data_dir = data_dir
        self.vault = Vault(session_id, data_dir)
        self.docs = DocumentStore(session_id, data_dir)
        self.rep = rep or load_representative()
        self._req_path = data_dir / "requests" / f"{session_id}.json"

    # ── secure capture requests (metadata only, no PII) ─────────────────────────────────────
    def _requests(self) -> dict:
        return json.loads(self._req_path.read_text()) if self._req_path.exists() else {}

    def _save_requests(self, reqs: dict) -> None:
        self._req_path.parent.mkdir(parents=True, exist_ok=True)
        self._req_path.write_text(json.dumps(reqs, indent=2))

    def create_capture_request(self, fields: list[str], purpose: str) -> dict:
        unknown = [f for f in fields if f not in FIELDS]
        if unknown:
            raise WorkflowError(f"unknown fields: {unknown}; allowed: {sorted(FIELDS)}")
        req = {
            "id": "req_" + secrets.token_hex(6),
            "fields": fields,
            "purpose": purpose,
            "status": "pending",
            "created_at": now_iso(),
        }
        reqs = self._requests()
        reqs[req["id"]] = req
        self._save_requests(reqs)
        self.docs.audit("secure_capture_requested", request_id=req["id"], fields=fields)
        return req

    def complete_capture_request(self, request_id: str, values: dict[str, str]) -> dict:
        """Host-side: the secure form posted. Only the request's own fields are accepted."""
        reqs = self._requests()
        req = reqs.get(request_id)
        if not req or req["status"] != "pending":
            raise WorkflowError("no pending secure form with that id")
        accepted = {k: v for k, v in values.items() if k in req["fields"] and str(v).strip()}
        errors = self.vault.put(accepted)
        if not errors:
            req["status"] = "completed"
            req["completed_at"] = now_iso()
            self._save_requests(reqs)
        self.docs.audit(
            "secure_capture_submitted",
            request_id=request_id,
            stored=sorted(set(accepted) - set(errors)),
            rejected=sorted(errors),
        )
        return errors

    def pending_requests(self) -> list[dict]:
        return [r for r in self._requests().values() if r["status"] == "pending"]

    # ── signature ───────────────────────────────────────────────────────────────────────────
    def save_signature(self, data_uri: str) -> None:
        self.vault.save_signature(data_uri)
        self.docs.audit("signature_saved", signature_sha256=sha256(data_uri.encode()))

    # ── draft lifecycle ─────────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        """The agent's view: masked data, what's missing, signature on file, documents."""
        return {
            "captured": self.vault.masked(),
            "missing_for_21_22a": form.missing_veteran_fields(self.vault.veteran()),
            "signature_on_file": self.vault.has_signature(),
            "pending_secure_forms": [r["id"] for r in self.pending_requests()],
            "documents": [self.describe(d) for d in self.docs.all()],
        }

    def describe(self, doc: Document) -> dict:
        return {
            "document_id": doc.id,
            "form": kind_of(doc).label,
            "kind": kind_of(doc).key,
            "status": doc.status,
            "version": doc.version,
            "missing": doc.missing,
            "consents": doc.consents,
            "terms": doc.terms,
            "signed_at": doc.signed_at,
            "countersigned_at": doc.countersigned_at,
        }

    def _render(self, doc: Document) -> bytes:
        kind, veteran = kind_of(doc), self.vault.veteran()
        doc.missing = kind.missing(veteran, doc)
        doc.vault_hmac = self.vault.fingerprint()
        return kind.render(veteran, self.rep, doc)

    def refresh_drafts(self) -> list[Document]:
        """Re-render every unsigned draft whose vault data changed since it was filled (a secure
        form corrected a value), as a new version. Returns the drafts that changed."""
        changed, current = [], self.vault.fingerprint()
        for doc in self.docs.all():
            if doc.status == "draft" and doc.vault_hmac != current:
                doc.version += 1
                doc.updated_at = now_iso()
                self.docs.save(doc, self._render(doc))
                self.docs.audit("draft_refreshed", document_id=doc.id, version=doc.version, missing=doc.missing)
                changed.append(doc)
        return changed

    def prepare(self, consents: dict | None = None, form_key: str = "21-22a", terms: dict | None = None) -> Document:
        """Fill a fresh draft of one form (the 21-22a takes the Item 20/22 consents; the fee
        agreement takes its terms). An earlier unsigned draft of that form is superseded."""
        kind = FORMS[form_key]
        if form_key == "fee_agreement" and not isinstance((terms or {}).get("fee_pct"), int):
            raise WorkflowError("the fee agreement needs its fee percentage first")
        consents = {k: (consents or {}).get(k) for k in CONSENT_KEYS} if form_key == "21-22a" else {}
        for d in self.docs.all():
            if d.status == "draft" and d.form_id == kind.form_id:
                d.status = "superseded"
                self.docs.save(d, self.docs.pdf(d.id))
        ts = now_iso()
        doc = Document(
            id=self.docs.new_id(),
            session_id=self.session_id,
            form_id=kind.form_id,
            edition=kind.edition,
            status="draft",
            consents=consents,
            missing=[],
            created_at=ts,
            updated_at=ts,
            terms=dict(terms or {}),
        )
        pdf = self._render(doc)
        self.docs.save(doc, pdf)
        self.docs.audit("draft_prepared", document_id=doc.id, form=kind.key, missing=doc.missing)
        return doc

    def edit(self, doc_id: str, changes: dict, actor: str) -> Document:
        doc = self._draft(doc_id)
        field_changes = {k: v for k, v in changes.items() if k not in CONSENT_KEYS}
        secret = [k for k in field_changes if k in FIELDS and k not in EDITABLE]
        unknown = [k for k in field_changes if k not in FIELDS]
        if secret:
            raise WorkflowError(f"{secret} can only change through a new secure form")
        if unknown:
            raise WorkflowError(f"unknown fields: {unknown}; editable: {sorted(EDITABLE)}")
        errors = self.vault.put(field_changes)  # collect once: edits update the record too
        if errors:
            raise WorkflowError(f"invalid values: {errors}")
        for k in CONSENT_KEYS if doc.form_id == form.FORM_ID else ():
            if k in changes:
                doc.consents[k] = bool(changes[k])
        doc.version += 1
        doc.updated_at = now_iso()
        self.docs.save(doc, self._render(doc))
        self.docs.audit(
            "draft_edited", document_id=doc.id, actor=actor, fields=sorted(changes),
            version=doc.version,
        )  # fmt: skip
        return doc

    def _draft(self, doc_id: str) -> Document:
        doc = self.docs.get(doc_id)
        if doc is None:
            raise WorkflowError("no such document")
        if doc.status != "draft":
            raise WorkflowError(f"document is {doc.status}; prepare a new draft to change it")
        return doc

    def ready_to_sign(self, doc_id: str) -> tuple[bool, str]:
        doc = self._draft(doc_id)
        if doc.missing:
            return False, "still missing: " + ", ".join(doc.missing)
        if not self.vault.has_signature():
            return False, "no saved signature"
        if doc.vault_hmac and doc.vault_hmac != self.vault.fingerprint():
            return False, "the secure-form data changed after this draft was filled: refresh the draft first"
        return True, "ready"

    def sign(self, doc_id: str, *, consent_text: str, ip: str, user_agent: str) -> Document:
        """HOST-ONLY. Called from the user's click on Sign, never from an agent tool."""
        ok, why = self.ready_to_sign(doc_id)
        if not ok:
            raise WorkflowError(why)
        doc = self.docs.get(doc_id)
        kind = kind_of(doc)
        if consent_text != kind.consent:
            raise WorkflowError("the signer must be shown the current e-sign consent")
        draft = self.docs.pdf(doc_id)
        signature = self.vault.signature()
        signed = kind.sign(draft, signature, date.today().isoformat())
        doc.status = "signed"
        doc.signed_at = now_iso()
        doc.updated_at = doc.signed_at
        doc.signature_audit = {
            "method": "click_to_sign_saved_signature",
            "consent_text": consent_text,
            "signer_ip": ip,
            "user_agent": user_agent[:300],
            "signature_sha256": sha256(signature.encode()),
            "draft_sha256": sha256(draft),
            "signed_pdf_sha256": sha256(signed),
        }
        self.docs.save(doc, signed)
        self.docs.audit("document_signed", document_id=doc.id, **doc.signature_audit)
        return doc

    def countersign(self, doc_id: str, *, attorney: str, by: str) -> Document:
        """STAFF-ONLY. Stamp the attorney's countersignature (name and date, as text) onto a copy
        of the signed PDF and save it as a new version. The veteran-signed version and its
        `signed_pdf_sha256` stay unchanged."""
        doc = self.docs.get(doc_id)
        if doc is None or doc.status != "signed":
            raise WorkflowError(f"only a signed document can be countersigned ({doc.status if doc else 'none'})")
        signed = self.docs.pdf(doc_id)
        stamped = kind_of(doc).countersign(signed, attorney, date.today().isoformat())
        doc.status, doc.version = "countersigned", doc.version + 1
        doc.countersigned_at = doc.updated_at = now_iso()
        doc.countersign_audit = {
            "attorney": attorney,
            "by": by,
            "signed_pdf_sha256": sha256(signed),
            "countersigned_pdf_sha256": sha256(stamped),
        }
        self.docs.save_version(doc, "countersigned", stamped)
        self.docs.audit("document_countersigned", document_id=doc.id, version=doc.version, **doc.countersign_audit)
        return doc

    def live(self, form_key: str) -> Document | None:
        """The form's current document (the newest that isn't superseded), or None."""
        docs = [d for d in self.docs.all() if d.form_id == FORMS[form_key].form_id and d.status != "superseded"]
        return docs[-1] if docs else None

    def document_pdf(self, doc_id: str) -> bytes:
        """The latest version: countersigned if it is, else as signed (or the draft)."""
        doc = self.docs.get(doc_id)
        if doc is None:
            raise WorkflowError("no such document")
        return self.docs.pdf(doc_id, "countersigned" if doc.status == "countersigned" else None)

    def document(self, doc_id: str) -> dict:
        doc = self.docs.get(doc_id)
        if doc is None:
            raise WorkflowError("no such document")
        return asdict(doc)
