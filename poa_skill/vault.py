"""Encrypted store for the veteran's identity data and saved signature.

The point of the design: the agent (the LLM) never sees an SSN or date of birth. The user types
them into a secure form the host app renders outside the chat; the host writes them here; the
agent's tools only ever get back masked values ("***-**-6789") and a list of what's missing.
The PDF filler reads the real values straight from the vault.

At rest every session file is Fernet-encrypted (AES-128-CBC + HMAC-SHA256) with a key from
POA_VAULT_KEY, or a key file generated on first run under the data directory (gitignored).
A production deployment would swap this for a KMS-backed store; the interface stays the same.
"""

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography.fernet import Fernet

from poa_skill.form_21_22a import BRANCHES
from poa_skill.pdf.transforms import us_state_code

DEFAULT_DATA_DIR = Path(os.environ.get("POA_DATA_DIR", ".data"))


def load_key(data_dir: Path = DEFAULT_DATA_DIR) -> bytes:
    env = os.environ.get("POA_VAULT_KEY")
    if env:
        return env.encode()
    key_file = data_dir / "vault.key"
    if not key_file.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(Fernet.generate_key())
        key_file.chmod(0o600)
    return key_file.read_bytes()


# ── Field catalog: the ONLY fields a secure-capture request can ask for ─────────────────────
# sensitivity: "secret" = never shown to the agent beyond a mask; "private" = partially masked;
# "plain" = the agent may see it (it uses the name in conversation).


class FieldError(ValueError):
    pass


def _ssn(v: str) -> str:
    d = re.sub(r"\D", "", v)
    if len(d) != 9:
        raise FieldError("Social Security number must be 9 digits")
    if d[:3] in ("000", "666") or d[0] == "9" or d[3:5] == "00" or d[5:] == "0000":
        raise FieldError("That isn't a valid Social Security number")
    return d


def _dob(v: str) -> str:
    try:
        d = date.fromisoformat(v.strip())
    except ValueError as e:
        raise FieldError("Date of birth must be YYYY-MM-DD") from e
    if not (date(1900, 1, 1) <= d <= date.today()):
        raise FieldError("Date of birth is out of range")
    return d.isoformat()


def _digits(n: int | tuple[int, ...], label: str):
    sizes = (n,) if isinstance(n, int) else n

    def check(v: str) -> str:
        d = re.sub(r"\D", "", v)
        if d and len(d) not in sizes:
            raise FieldError(f"{label} must be {' or '.join(map(str, sizes))} digits")
        return d

    return check


def _phone(v: str) -> str:
    d = re.sub(r"\D", "", v)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if d and len(d) != 10:
        raise FieldError("Phone number must be a 10-digit US number")
    return d


def _branch(v: str) -> str:
    k = v.strip().lower().replace(" ", "_")
    if k not in BRANCHES:
        raise FieldError(f"Branch must be one of: {', '.join(BRANCHES)}")
    return k


def _state(v: str) -> str:
    s = us_state_code(v)
    if not re.fullmatch(r"[A-Z]{2}", s):
        raise FieldError("State must be a US state")
    return s


def _email(v: str) -> str:
    v = v.strip()
    if v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
        raise FieldError("That email address doesn't look right")
    return v


def _text(max_len: int):
    def check(v: str) -> str:
        v = v.strip()
        if len(v) > max_len:
            raise FieldError(f"Keep it under {max_len} characters")
        return v

    return check


@dataclass(frozen=True)
class FieldSpec:
    label: str
    sensitivity: str  # secret | private | plain
    input_type: str  # what the secure form renders: text | ssn | date | select | email | tel
    validate: object
    options: tuple[str, ...] = ()


FIELDS: dict[str, FieldSpec] = {
    "first_name": FieldSpec("First name", "plain", "text", _text(40)),
    "middle_initial": FieldSpec("Middle initial", "plain", "text", _text(1)),
    "last_name": FieldSpec("Last name", "plain", "text", _text(40)),
    "ssn": FieldSpec("Social Security number", "secret", "ssn", _ssn),
    "date_of_birth": FieldSpec("Date of birth", "secret", "date", _dob),
    "va_file_number": FieldSpec(
        "VA file number (if you have one)", "secret", "text", _digits((8, 9), "VA file number")
    ),
    "service_number": FieldSpec(
        "Service number (only if you served before 1974)", "secret", "text", _text(10)
    ),
    "branch": FieldSpec("Branch of service", "plain", "select", _branch, tuple(BRANCHES)),
    "address.line1": FieldSpec("Street address", "private", "text", _text(30)),
    "address.line2": FieldSpec("Apt or unit", "private", "text", _text(5)),
    "address.city": FieldSpec("City", "plain", "text", _text(18)),
    "address.state": FieldSpec("State", "plain", "text", _state),
    "address.zip": FieldSpec("ZIP code", "private", "text", _digits((5, 9), "ZIP code")),
    "phone": FieldSpec("Phone", "private", "tel", _phone),
    "email": FieldSpec("Email", "private", "email", _email),
}


def _mask(name: str, value: str) -> str:
    spec = FIELDS[name]
    if not value:
        return ""
    if spec.sensitivity == "plain":
        return value
    if name == "ssn":
        return f"***-**-{value[-4:]}"
    if name == "date_of_birth":
        return "**/**/" + value[:4]
    if name == "email":
        user, _, domain = value.partition("@")
        return f"{user[:1]}***@{domain}"
    if name == "address.line1":
        return re.sub(r"[^\s]", "*", value[:-4]) + value[-4:] if len(value) > 4 else "****"
    return "*" * max(0, len(value) - 4) + value[-4:]


class Vault:
    """One session's encrypted record: {"fields": {...}, "signature": data-URI or None}."""

    def __init__(
        self, session_id: str, data_dir: Path = DEFAULT_DATA_DIR, key: bytes | None = None
    ):
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", session_id):
            raise ValueError("bad session id")
        self.path = data_dir / "vault" / f"{session_id}.bin"
        self._key = key or load_key(data_dir)
        self._fernet = Fernet(self._key)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"fields": {}, "signature": None}
        return json.loads(self._fernet.decrypt(self.path.read_bytes()))

    def _save(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(self._fernet.encrypt(json.dumps(rec).encode()))
        self.path.chmod(0o600)

    # ── host-side writers (called from the secure form / signature pad, never by the agent) ──
    def put(self, values: dict[str, str]) -> dict[str, str]:
        """Validate and store. Returns {field: error} for anything rejected (nothing stored
        for those); valid fields are saved even if others fail."""
        rec = self._load()
        errors = {}
        for name, raw in values.items():
            if name not in FIELDS:
                errors[name] = "unknown field"
                continue
            try:
                rec["fields"][name] = FIELDS[name].validate(str(raw or ""))
            except FieldError as e:
                errors[name] = str(e)
        self._save(rec)
        return errors

    def save_signature(self, data_uri: str) -> None:
        if not data_uri.startswith("data:image/png;base64,"):
            raise FieldError("signature must be a PNG data URI")
        rec = self._load()
        rec["signature"] = data_uri
        self._save(rec)

    # ── readers ────────────────────────────────────────────────────────────────────────────
    def veteran(self) -> dict:
        """Nested dict for the form mapping. Host/filler only: contains raw PII."""
        out: dict = {}
        for name, value in self._load()["fields"].items():
            if "." in name:
                head, tail = name.split(".", 1)
                out.setdefault(head, {})[tail] = value
            else:
                out[name] = value
        return out

    def signature(self) -> str | None:
        return self._load()["signature"]

    def masked(self) -> dict[str, str]:
        """What the agent is allowed to see."""
        return {n: _mask(n, v) for n, v in self._load()["fields"].items() if v}

    def fingerprint(self) -> str:
        """A keyed hash (HMAC with the vault key) of the identity fields: tells whether a draft
        is stale without storing anything an attacker could brute-force back into an SSN."""
        data = json.dumps(self._load()["fields"], sort_keys=True).encode()
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    def has_signature(self) -> bool:
        return bool(self._load()["signature"])
