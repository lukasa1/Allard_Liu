"""VA Lighthouse API tools, in three interchangeable modes (LIGHTHOUSE_MODE):

  stub      responses built from the synthetic personas, in VA's response shapes. No keys.
            The eval uses this, because it lets us design the cases (incomplete records, ...).
  recorded  responses saved from the real sandbox (`intake lighthouse-record`), replayed from
            agent/data/lighthouse_recorded/. No keys, and anyone can run it.
  sandbox   live calls to https://sandbox-api.va.gov with OAuth access tokens. Keys stay in .env:
            the Lighthouse terms forbid embedding credentials in open-source projects.

APIs used (Benefits Claims v1 and VSHE v2 are "Open" for third parties; Benefits Documents is
VA-internal, so the C-file comes from agent/cfile's stub instead):
  VSHE v2            GET /status, /service_history, /disability_rating, /permanent_and_total_disability
  Benefits Claims v1 GET /claims, GET /forms/2122/active, POST /forms/2122 (21-22 or 21-22a)
                     + PUT /forms/2122/{id} (the signed PDF), POST /forms/0966 (intent to file)

Sandbox mode status: written against the saved OpenAPI specs, NOT yet exercised against the live
sandbox (we don't have credentials yet). The OAuth login flow is not built: set access tokens you
obtained from the sandbox's OAuth flow in VA_VSHE_ACCESS_TOKEN / VA_CLAIMS_ACCESS_TOKEN.

A static token speaks for ONE person, whatever ICN we pass: VSHE and the claims endpoints read the
veteran from the token, and a representative's token without the X-VA-SSN / X-VA-First-Name /
X-VA-Last-Name / X-VA-Birth-Date headers makes VA treat the representative as the claimant. So
sandbox mode needs VA_TOKEN_ICN (the token user's ICN) and refuses any other case ICN. The
representative-token header flow is not built (it needs the SSN, which stays in the POA vault).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from agent.lighthouse import stub
from agent.lighthouse.records import VaRecords
from agent.personas import Persona, load_personas

RECORDED_DIR = Path(__file__).resolve().parent.parent / "data" / "lighthouse_recorded"
SANDBOX_BASE = "https://sandbox-api.va.gov/services"
VSHE_ENDPOINTS = {
    "veteran_status": "/veteran_verification/v2/status",
    "service_history": "/veteran_verification/v2/service_history",
    "disability_rating": "/veteran_verification/v2/disability_rating",
    "permanent_and_total": "/veteran_verification/v2/permanent_and_total_disability",
}
CLAIMS_ENDPOINTS = {
    "claims": "/claims/v1/claims",
    "active_poa": "/claims/v1/forms/2122/active",
}
MODES = ("stub", "recorded", "sandbox")
POA_STATUSES = ("pending", "submitted", "updated", "errored")


class LighthouseError(RuntimeError):
    pass


class Lighthouse(Protocol):
    mode: str

    def test_veterans(self) -> list[dict[str, str]]:
        """Who can 'sign in with VA' in this mode: [{icn, name, summary}]. Empty for sandbox."""
        ...

    def fetch_records(self, icn: str) -> VaRecords: ...

    def submit_poa(
        self, icn: str, representative: dict[str, Any], signed_pdf: bytes | None = None
    ) -> dict[str, Any]:
        """Benefits Claims v1 POST /forms/2122, then PUT /forms/2122/{id} with the signed PDF.

        Returns {"status": pending|submitted|updated|errored, "id", "signed_pdf_uploaded",
        "raw": POST response, "raw_upload": PUT response or None} (+ "upload_error" if the PUT
        failed after the POST: the POA then exists at VA as `pending`, so don't POST again).
        """
        ...

    def submit_intent_to_file(self, icn: str) -> dict[str, Any]:
        """Benefits Claims v1 POST /forms/0966 (compensation).

        Returns {"date": "YYYY-MM-DD", "expires": "YYYY-MM-DD" | None, "status": active|duplicate,
        "raw": response}. "duplicate" means an ITF was already active; `date` is that one's.
        """
        ...


def _poa_payload(representative: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": {
            "type": "form/21-22",
            "attributes": {"serviceOrganization": {"poaCode": representative.get("poa_code", "")}},
        }
    }


def _poa_result(
    post: dict[str, Any], put: dict[str, Any] | None = None, upload_error: str | None = None
) -> dict[str, Any]:
    data = (put or post).get("data") or {}
    status = str((data.get("attributes") or {}).get("status") or "").lower()
    out = {
        "status": status if status in POA_STATUSES else "errored",
        "id": data.get("id") or (post.get("data") or {}).get("id"),
        "signed_pdf_uploaded": put is not None,
        "raw": post,
        "raw_upload": put,
    }
    if upload_error:
        out["upload_error"] = upload_error
    return out


def _iso_date(value: Any) -> str | None:
    """VA sends "2025-02-07T09:17:18-06:00" (or a plain date); keep VA's own calendar date."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10]).isoformat()
    except ValueError:
        return None


def _itf_result(resp: dict[str, Any]) -> dict[str, Any]:
    attrs = (resp.get("data") or {}).get("attributes") or {}
    created = _iso_date(attrs.get("creation_date"))
    if created is None:
        raise LighthouseError(
            f"0966 response has no usable creation_date: {attrs.get('creation_date')!r}"
        )
    return {
        "date": created,
        "expires": _iso_date(attrs.get("expiration_date")),
        "status": str(attrs.get("status") or "unknown").lower(),
        "raw": resp,
    }


# ------------------------------------------------------------------------------------- stub


class StubLighthouse:
    mode = "stub"

    def __init__(self, personas: list[Persona] | None = None) -> None:
        self.personas = {p.icn: p for p in (personas or load_personas())}
        self.submissions: list[dict[str, Any]] = []

    def persona(self, icn: str) -> Persona:
        if icn not in self.personas:
            raise LighthouseError(f"no test veteran with ICN {icn}")
        return self.personas[icn]

    def test_veterans(self) -> list[dict[str, str]]:
        return [
            {"icn": p.icn, "name": p.display_name, "persona": p.id, "summary": p.summary}
            for p in self.personas.values()
        ]

    def fetch_records(self, icn: str) -> VaRecords:
        p = self.persona(icn)
        return VaRecords(
            icn=icn,
            mode=self.mode,
            veteran_status=stub.veteran_status(p),
            service_history=stub.service_history(p),
            disability_rating=stub.disability_rating(p),
            permanent_and_total=stub.permanent_and_total(p),
            claims=stub.claims(p),
            active_poa=stub.active_poa(p),
        )

    def submit_poa(
        self, icn: str, representative: dict[str, Any], signed_pdf: bytes | None = None
    ) -> dict[str, Any]:
        self.persona(icn)
        payload = _poa_payload(representative)
        self.submissions.append({"endpoint": "POST /forms/2122", "icn": icn, "payload": payload})
        poa_id = stub._uuid(icn, "poa", str(len(self.submissions)))
        code = representative.get("poa_code", "")

        def resp(status: str) -> dict[str, Any]:
            return {
                "data": {
                    "id": poa_id,
                    "type": "claims_api_power_of_attorneys",
                    "attributes": {
                        "date_request_accepted": date.today().isoformat(),
                        "previous_poa": None,
                        "representative": {"service_organization": {"poa_code": code}},
                        "status": status,
                    },
                }
            }

        # Like VA: without the signed PDF the POA stays `pending`.
        if signed_pdf is None:
            return _poa_result(resp("pending"))
        put = f"PUT /forms/2122/{poa_id}"
        self.submissions.append({"endpoint": put, "icn": icn, "pdf_bytes": len(signed_pdf)})
        return _poa_result(resp("pending"), resp("submitted"))

    def submit_intent_to_file(self, icn: str) -> dict[str, Any]:
        self.persona(icn)
        now = datetime.now().astimezone().replace(microsecond=0)  # VA sends a datetime w/ offset
        self.submissions.append({"endpoint": "POST /forms/0966", "icn": icn})
        return _itf_result({
            "data": {
                "id": stub._uuid(icn, "itf", str(len(self.submissions))),
                "type": "intent_to_file",
                "attributes": {
                    "creation_date": now.isoformat(),
                    "expiration_date": (now + timedelta(days=365)).isoformat(),
                    "type": "compensation",
                    "status": "active",
                },
            }
        })  # fmt: skip


# ------------------------------------------------------------------------------------- recorded


class RecordedLighthouse(StubLighthouse):
    """Replays saved sandbox responses: RECORDED_DIR/<icn>/<endpoint>.json (+ index.json).

    Submissions (POA, ITF) are answered by the stub, since replaying a POST proves nothing.
    """

    mode = "recorded"

    def __init__(self, directory: Path = RECORDED_DIR) -> None:
        super().__init__(personas=[])
        self.directory = directory

    def test_veterans(self) -> list[dict[str, str]]:
        index = self.directory / "index.json"
        return json.loads(index.read_text()) if index.exists() else []

    def fetch_records(self, icn: str) -> VaRecords:
        if not re.fullmatch(r"[0-9A-Za-z]{6,32}", icn or ""):
            raise LighthouseError("bad ICN")
        folder = self.directory / icn
        if not folder.is_dir():
            raise LighthouseError(f"no recorded responses for ICN {icn} in {self.directory}")
        kwargs: dict[str, Any] = {}
        for name in list(VSHE_ENDPOINTS) + list(CLAIMS_ENDPOINTS):
            f = folder / f"{name}.json"
            kwargs[name] = json.loads(f.read_text()) if f.exists() else None
        return VaRecords(icn=icn, mode=self.mode, **kwargs)

    def persona(self, icn: str):
        return None


# ------------------------------------------------------------------------------------- sandbox


class SandboxLighthouse:
    mode = "sandbox"

    def __init__(self, client=None) -> None:
        import httpx

        self.vshe_token = os.environ.get("VA_VSHE_ACCESS_TOKEN", "")
        self.claims_token = os.environ.get("VA_CLAIMS_ACCESS_TOKEN", "")
        self.token_icn = os.environ.get("VA_TOKEN_ICN", "").strip()
        if not (self.vshe_token or self.claims_token):
            raise LighthouseError(
                "LIGHTHOUSE_MODE=sandbox needs VA_VSHE_ACCESS_TOKEN and/or VA_CLAIMS_ACCESS_TOKEN "
                "in .env (see .env.example)."
            )
        self.http = client or httpx.Client(base_url=SANDBOX_BASE, timeout=20.0)

    def test_veterans(self) -> list[dict[str, str]]:
        # The tokens speak for one test user only: that's the only veteran who can "sign in".
        if not self.token_icn:
            return []
        return [{"icn": self.token_icn, "name": "Sandbox token user", "persona": "",
                 "summary": "The VA sandbox test user the access tokens belong to."}]  # fmt: skip

    def _check_icn(self, icn: str) -> None:
        if not self.token_icn:
            raise LighthouseError(
                "LIGHTHOUSE_MODE=sandbox needs VA_TOKEN_ICN (the ICN of the tokens' user) in .env: "
                "the tokens, not the ICN we pass, decide whose records are read and filed."
            )
        if icn != self.token_icn:
            raise LighthouseError(
                f"case ICN {icn} is not the access tokens' user ({self.token_icn}); refusing to "
                "read or file under someone else's identity."
            )

    def _get(self, path: str, token: str) -> dict[str, Any] | None:
        try:
            r = self.http.get(path, headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 404:
                return None
            if r.status_code >= 400:
                raise LighthouseError(_http_error("GET", path, r))
            return r.json()
        except LighthouseError:
            raise
        except Exception as exc:  # timeouts, connection errors, bad JSON
            raise LighthouseError(f"GET {path}: {type(exc).__name__}") from exc

    def fetch_records(self, icn: str) -> VaRecords:
        self._check_icn(icn)
        rec = VaRecords(icn=icn, mode=self.mode)
        calls = [(n, p, self.vshe_token) for n, p in VSHE_ENDPOINTS.items()]
        calls += [(n, p, self.claims_token) for n, p in CLAIMS_ENDPOINTS.items()]
        for name, path, token in calls:
            if not token:
                rec.errors[name] = "no access token configured"
                continue
            try:
                setattr(rec, name, self._get(path, token))
            except Exception as exc:  # one failed endpoint shouldn't lose the others
                rec.errors[name] = str(exc)
        # VSHE /status echoes the token user's ICN as data.id: a second guard against a mix-up.
        echoed = ((rec.veteran_status or {}).get("data") or {}).get("id")
        if echoed and echoed != icn:
            raise LighthouseError(f"VA returned records for ICN {echoed}, not {icn}")
        return rec

    def _send(self, method: str, path: str, **kw) -> dict[str, Any]:
        if not self.claims_token:
            raise LighthouseError("no VA_CLAIMS_ACCESS_TOKEN configured")
        try:
            headers = {"Authorization": f"Bearer {self.claims_token}"}
            r = self.http.request(method, path, headers=headers, **kw)
            if r.status_code >= 400:
                raise LighthouseError(_http_error(method, path, r))
            return r.json()
        except LighthouseError:
            raise
        except Exception as exc:  # timeouts, connection errors, bad JSON
            raise LighthouseError(f"{method} {path}: {type(exc).__name__}") from exc

    def submit_poa(
        self, icn: str, representative: dict[str, Any], signed_pdf: bytes | None = None
    ) -> dict[str, Any]:
        self._check_icn(icn)
        if not (representative.get("poa_code") or "").strip():
            raise LighthouseError(
                "the representative has no poa_code (VA's accreditation POA code); "
                "POST /forms/2122 requires serviceOrganization.poaCode"
            )
        post = self._send("POST", "/claims/v1/forms/2122", json=_poa_payload(representative))
        poa_id = (post.get("data") or {}).get("id")
        if signed_pdf is None or not poa_id:
            return _poa_result(post)  # VA keeps it `pending` until the signed PDF arrives
        try:
            files = {"attachment": ("21-22a.pdf", signed_pdf, "application/pdf")}
            put = self._send("PUT", f"/claims/v1/forms/2122/{poa_id}", files=files)
        except LighthouseError as exc:
            return _poa_result(post, upload_error=str(exc))
        return _poa_result(post, put)

    def submit_intent_to_file(self, icn: str) -> dict[str, Any]:
        self._check_icn(icn)
        return _itf_result(
            self._send(
                "POST",
                "/claims/v1/forms/0966",
                json={"data": {"type": "form/0966", "attributes": {"type": "compensation"}}},
            )
        )


def _http_error(method: str, path: str, r) -> str:
    """'POST /x: HTTP 422: detail (source); ...' using VA's `errors` (or `message`) body."""
    msg = f"{method} {path}: HTTP {r.status_code}"
    try:
        body = r.json()
    except ValueError:  # not JSON
        return msg
    if not isinstance(body, dict):
        return msg
    details = []
    for e in body.get("errors") or []:
        if isinstance(e, dict):
            d = str(e.get("detail") or e.get("title") or "").strip()
            src = e.get("source")
            src = src.get("pointer") if isinstance(src, dict) else src
            details.append(f"{d} ({src})" if src and d else d or str(src or ""))
        else:
            details.append(str(e))
    if not details and body.get("message"):
        details.append(str(body["message"]))
    details = [d for d in details if d]
    return f"{msg}: {'; '.join(details)[:500]}" if details else msg


def make_lighthouse(mode: str | None = None) -> Lighthouse:
    mode = (mode or os.environ.get("LIGHTHOUSE_MODE") or "stub").strip().lower()
    if mode == "stub":
        return StubLighthouse()
    if mode == "recorded":
        return RecordedLighthouse()
    if mode == "sandbox":
        return SandboxLighthouse()
    raise LighthouseError(f"LIGHTHOUSE_MODE must be one of {MODES}, got {mode!r}")


def record_sandbox(icn: str, label: str, directory: Path = RECORDED_DIR) -> Path:
    """Save one sandbox test user's responses for `recorded` mode. Run after signing up.

    `icn` must be VA_TOKEN_ICN (fetch_records refuses others), so nobody's data is filed under
    another ICN.
    """
    rec = SandboxLighthouse().fetch_records(icn)
    folder = directory / icn
    folder.mkdir(parents=True, exist_ok=True)
    for name in list(VSHE_ENDPOINTS) + list(CLAIMS_ENDPOINTS):
        value = getattr(rec, name)
        if value is not None:
            (folder / f"{name}.json").write_text(json.dumps(value, indent=2))
    index_path = directory / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else []
    index = [e for e in index if e["icn"] != icn] + [
        {"icn": icn, "name": label, "persona": "", "summary": "Recorded from the VA sandbox."}
    ]
    index_path.write_text(json.dumps(index, indent=2))
    return folder
