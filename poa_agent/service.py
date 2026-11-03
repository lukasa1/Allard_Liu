"""The 21-22a workflow, shared by the agent's tools (tools.py) and the host app (demo/server.py).

Who can do what is the security model:
  agent  asks for secure capture, prepares/edits the draft, offers it for signature.
  user   types PII into the secure form, draws a signature, clicks Sign.
The agent has no path to raw PII and no way to sign: `sign()` is only reachable from the host's
click handler, which records the user's own intent.
"""

import json
import secrets
from dataclasses import asdict
from datetime import date
from pathlib import Path

from poa_agent import form_21_22a as form
from poa_agent.documents import Document, DocumentStore, now_iso, sha256
from poa_agent.vault import DEFAULT_DATA_DIR, FIELDS, Vault

REP_CONFIG = Path(__file__).resolve().parent.parent / "config" / "representative.json"

# Shown on the Sign button's card and recorded verbatim in the audit trail.
ESIGN_CONSENT = (
    "By clicking Sign, I adopt my saved signature as my signature on this VA Form 21-22a, "
    "appointing the representative named in Item 16A, and I agree to sign electronically."
)

# Fields the agent or the user may change on a draft without the secure form. Secret fields
# (SSN, date of birth, file/service numbers) only change through a new secure-capture request.
EDITABLE = {n for n, s in FIELDS.items() if s.sensitivity != "secret"}
CONSENT_KEYS = ("authorize_7332_records", "authorize_address_change")


class WorkflowError(ValueError):
    pass


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
            "form": "VA 21-22a",
            "status": doc.status,
            "version": doc.version,
            "missing": doc.missing,
            "consents": doc.consents,
            "signed_at": doc.signed_at,
        }

    def _render(self, doc: Document) -> bytes:
        consents = form.Consents(**doc.consents)
        veteran = self.vault.veteran()
        doc.missing = form.missing_fields(veteran, consents)
        return form.render_draft(veteran, self.rep, consents)

    def prepare(self, consents: dict) -> Document:
        """Fill a fresh draft. Any earlier unsigned draft is superseded so only one is live."""
        consents = {k: consents.get(k) for k in CONSENT_KEYS}
        for d in self.docs.all():
            if d.status == "draft":
                d.status = "superseded"
                self.docs.save(d, self.docs.pdf(d.id))
        ts = now_iso()
        doc = Document(
            id=self.docs.new_id(),
            session_id=self.session_id,
            form_id=form.FORM_ID,
            edition=form.EDITION,
            status="draft",
            consents=consents,
            missing=[],
            created_at=ts,
            updated_at=ts,
        )
        pdf = self._render(doc)
        self.docs.save(doc, pdf)
        self.docs.audit("draft_prepared", document_id=doc.id, missing=doc.missing)
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
        for k in CONSENT_KEYS:
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
        return True, "ready"

    def sign(self, doc_id: str, *, consent_text: str, ip: str, user_agent: str) -> Document:
        """HOST-ONLY. Called from the user's click on Sign, never from an agent tool."""
        ok, why = self.ready_to_sign(doc_id)
        if not ok:
            raise WorkflowError(why)
        if consent_text != ESIGN_CONSENT:
            raise WorkflowError("the signer must be shown the current e-sign consent")
        doc = self.docs.get(doc_id)
        draft = self.docs.pdf(doc_id)
        signature = self.vault.signature()
        signed = form.sign_draft(draft, signature, date.today().isoformat())
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

    def document_pdf(self, doc_id: str) -> bytes:
        if self.docs.get(doc_id) is None:
            raise WorkflowError("no such document")
        return self.docs.pdf(doc_id)

    def document(self, doc_id: str) -> dict:
        doc = self.docs.get(doc_id)
        if doc is None:
            raise WorkflowError("no such document")
        return asdict(doc)
