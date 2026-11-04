"""Document store + audit log.

Filled PDFs contain the veteran's SSN, so they are encrypted at rest with the vault key, the same
as the vault. The audit log is append-only JSONL and never holds PII: it records who did what,
when, and content hashes, which is what makes a click-to-sign adoption defensible under
ESIGN/UETA (intent to sign, consent to sign electronically, record of the signed document).
"""

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from poa_skill.vault import DEFAULT_DATA_DIR, load_key

# The clock and the ID source. A host that needs repeatable runs replaces them (the agent's eval
# pins them: agent/clock.py); otherwise the real clock and random IDs.
LIVE_CLOCK = {"now": lambda: datetime.now(UTC), "token_hex": secrets.token_hex}
CLOCK = dict(LIVE_CLOCK)


def now_iso() -> str:
    return CLOCK["now"]().isoformat(timespec="seconds")


def today_iso() -> str:
    """Today's local date: the date a signature carries."""
    return CLOCK["now"]().astimezone().date().isoformat()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@dataclass
class Document:
    id: str
    session_id: str
    form_id: str
    edition: str
    status: str  # draft | signed | countersigned | superseded
    consents: dict
    missing: list[str]
    created_at: str
    updated_at: str
    version: int = 1
    signed_at: str | None = None
    signature_audit: dict = field(default_factory=dict)
    terms: dict = field(default_factory=dict)  # fee agreement: {"fee_pct": N}
    countersigned_at: str | None = None
    countersign_audit: dict = field(default_factory=dict)
    vault_hmac: str = ""  # Vault.fingerprint() of the data this draft was rendered from


class DocumentStore:
    def __init__(
        self, session_id: str, data_dir: Path = DEFAULT_DATA_DIR, key: bytes | None = None
    ):
        self.session_id = session_id
        self.dir = data_dir / "documents" / session_id
        self.audit_path = data_dir / "audit.jsonl"
        self._fernet = Fernet(key or load_key(data_dir))

    # ── records ────────────────────────────────────────────────────────────────────────────
    def new_id(self) -> str:
        return "doc_" + CLOCK["token_hex"](6)

    def save(self, doc: Document, pdf: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{doc.id}.pdf.bin").write_bytes(self._fernet.encrypt(pdf))
        (self.dir / f"{doc.id}.json").write_text(json.dumps(asdict(doc), indent=2))

    def get(self, doc_id: str) -> Document | None:
        p = self.dir / f"{doc_id}.json"
        if not doc_id.startswith("doc_") or not p.exists():
            return None
        return Document(**json.loads(p.read_text()))

    def save_version(self, doc: Document, label: str, pdf: bytes) -> None:
        """A later version (e.g. "countersigned") beside the one `save` wrote, which stays as is."""
        (self.dir / f"{doc.id}.{label}.pdf.bin").write_bytes(self._fernet.encrypt(pdf))
        (self.dir / f"{doc.id}.json").write_text(json.dumps(asdict(doc), indent=2))

    def pdf(self, doc_id: str, label: str | None = None) -> bytes:
        name = f"{doc_id}.{label}.pdf.bin" if label else f"{doc_id}.pdf.bin"
        return self._fernet.decrypt((self.dir / name).read_bytes())

    def all(self) -> list[Document]:
        if not self.dir.exists():
            return []
        return sorted(
            (Document(**json.loads(p.read_text())) for p in self.dir.glob("doc_*.json")),
            key=lambda d: d.created_at,
        )

    # ── audit ──────────────────────────────────────────────────────────────────────────────
    def audit(self, event: str, **details) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        line = {"at": now_iso(), "session": self.session_id, "event": event, **details}
        with self.audit_path.open("a") as f:
            f.write(json.dumps(line) + "\n")
