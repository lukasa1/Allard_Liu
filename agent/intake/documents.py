"""The case's representation documents (L20) and the host-side actions on them.

Each case has one PoaService (poa_skill: the encrypted vault, the document store, the audit log)
named after the case. Intake's tools prepare and show documents; only these host actions, called
from the veteran's clicks or the staff panel, ever capture ID numbers, sign or countersign. Each
records its effect on the case file and becomes an event for intake's next turn (`rt.event`).
"""

from __future__ import annotations

from datetime import date, timedelta

from agent.casefile import Answer, CaseFile, DocState, Task
from agent.intake.checklist import VAULT_FIELD
from poa_skill.service import FORMS, PoaService, load_representative

FORM_KEYS = tuple(FORMS)  # "21-22a", "fee_agreement"
OGC_DAYS = 30  # 38 CFR 14.636(g): the fee agreement goes to VA OGC within 30 days of signing
OGC_TASK = "Send the fee agreement to VA OGC within 30 days of signing (38 CFR 14.636(g))"


def service(rt, case_id: str) -> PoaService:
    return PoaService(f"case-{case_id}", data_dir=rt.store.path.parent)


def attorney_name() -> str:
    rep = load_representative()
    return " ".join(p for p in (rep.get("first_name"), rep.get("last_name")) if p)


def submit_secure_form(rt, case_id: str, request_id: str, values: dict[str, str]) -> dict[str, str]:
    """The veteran submitted a secure form. Values go to the vault; the case file gets only the
    masked contact fields (source "secure form"). Returns {field: error} for rejected values."""
    svc = service(rt, case_id)
    errors = svc.complete_capture_request(request_id, values)
    masked = svc.vault.masked()
    stored = sorted(k for k in values if k in masked and k not in errors)

    def apply(case: CaseFile) -> None:
        for question, name in VAULT_FIELD.items():
            if name in stored:
                case.answers[question] = Answer(value=masked[name], source="secure form")

    rt.event(case_id, "secure_form_submitted", {"request_id": request_id, "stored": stored,
             "rejected": sorted(errors)}, actor="veteran", apply=apply)  # fmt: skip
    return errors


def save_signature(rt, case_id: str, data_uri: str) -> None:
    service(rt, case_id).save_signature(data_uri)
    rt.event(case_id, "signature_saved", {}, actor="veteran")


def sign(rt, case_id: str, form: str, consent_text: str, ip: str = "", user_agent: str = "") -> None:
    """The veteran clicked Sign on `form`'s Sign card (the only way a document is signed)."""
    svc = service(rt, case_id)
    doc = svc.live(form)
    if doc is None:
        raise ValueError(f"no {form} to sign")
    doc = svc.sign(doc.id, consent_text=consent_text, ip=ip, user_agent=user_agent)

    def apply(case: CaseFile) -> None:
        case.documents[form] = DocState(document_id=doc.id, signed_at=doc.signed_at)

    rt.event(case_id, "signed", {"form": form, "document_id": doc.id}, actor="veteran", apply=apply)


def countersign(rt, case_id: str, by: str) -> None:
    """Staff: the attorney countersigns both documents in one action (D6). Each gets a stamped
    new version; the case records who and when, and a deadline task tracks the OGC fax."""
    svc, attorney = service(rt, case_id), attorney_name()
    docs = {f: svc.live(f) for f in FORM_KEYS}
    if not all(d and d.status == "signed" for d in docs.values()):
        raise ValueError("both documents must be signed by the veteran first")
    done = {f: svc.countersign(d.id, attorney=attorney, by=by) for f, d in docs.items()}

    def apply(case: CaseFile) -> None:
        for f, d in done.items():
            state = case.documents.setdefault(f, DocState(document_id=d.id, signed_at=d.signed_at))
            state.countersigned_at, state.countersigned_by = d.countersigned_at, by
        due = date.fromisoformat(done["fee_agreement"].signed_at[:10]) + timedelta(days=OGC_DAYS)
        if "fee_agreement" not in case.filings:
            case.tasks.append(Task(kind="deadline", text=OGC_TASK, due=due.isoformat()))

    rt.event(case_id, "countersigned", {"by": by, "attorney": attorney, "forms": list(done)},
             actor="staff", apply=apply)  # fmt: skip

