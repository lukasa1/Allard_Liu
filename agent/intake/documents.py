"""The case's representation documents and the host-side actions on them.

Each case has one PoaService (poa_skill: the encrypted vault, the document store, the audit log)
named after the case. Intake's tools prepare and show documents; only these host actions, called
from the veteran's clicks or the staff panel, ever capture ID numbers, sign or countersign. Each
records its effect on the case file and becomes an event for intake's next turn (`rt.event`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from agent import clock
from agent.casefile import Answer, CaseFile, DocState, Task
from agent.intake.checklist import VAULT_FIELD, fee_pct
from poa_skill.service import FORMS, PoaService, kind_of, load_representative
from poa_skill.tools import preview_card

FORM_KEYS = tuple(FORMS)  # "21-22a", "fee_agreement"
OGC_DAYS = 30  # 38 CFR 14.636(g): the fee agreement goes to VA OGC within 30 days of signing
OGC_TASK = "Send the fee agreement to VA OGC within 30 days of signing (38 CFR 14.636(g))"


def service(rt, case_id: str) -> PoaService:
    return PoaService(f"case-{case_id}", data_dir=rt.store.path.parent)


def attorney_name() -> str:
    rep = load_representative()
    return " ".join(p for p in (rep.get("first_name"), rep.get("last_name")) if p)


def masked_answers(svc: PoaService, stored: list[str], source: str) -> Callable[[CaseFile], None]:
    """A case-file patch: the masked contact fields just written to the vault, as answers."""
    masked = svc.vault.masked()

    def apply(case: CaseFile) -> None:
        for question, name in VAULT_FIELD.items():
            if name in stored and name in masked:
                case.answers[question] = Answer(value=masked[name], source=source)

    return apply


def refresh_drafts(rt, case_id: str, svc: PoaService, post=None) -> list[str]:
    """Re-render the unsigned drafts the vault change made stale; each gets a new preview card
    (so a Sign card shown before is no longer the newest: the veteran reviews the change first).
    `post`: an agent turn's card list (posted after its reply); by default, posted now."""
    changed = svc.refresh_drafts()
    for doc in changed:
        card = preview_card(svc, doc)
        post(card) if post else rt.post_card(case_id, "intake", card)
    return [kind_of(d).key for d in changed]


def sign_card_open(rt, case_id: str, form: str, shown: tuple[str, int] | None = None) -> bool:
    """The form's newest card is a Sign card for its current draft (a preview after it, from
    update_draft or a secure-form correction, means the veteran must review the change first)."""
    cards = [o.payload for o in rt.updates(case_id) if o.kind == "card"
             and o.payload.get("form") == form and o.payload["type"] in ("sign_button", "document_preview")]  # fmt: skip
    live = service(rt, case_id).live(form)
    # The version too: update_draft edits a draft in place (same id, new version), and its new preview
    # card is posted after the turn's reply, so until then the old Sign card is still the newest.
    # `shown`: the (document_id, version) of the card the veteran clicked, which must be that newest
    # card: a Sign card for a newer version can arrive with its preview just before a click on the old one.
    newest = cards[-1] if cards else {}
    on_card = (newest.get("document_id"), newest.get("version"))
    return bool(live) and newest.get("type") == "sign_button" and on_card == (live.id, live.version) \
        and (shown is None or tuple(shown) == on_card)


def signed_change_task(svc: PoaService, before: dict, keys: list[str], how: str) -> Task | None:
    """A staff task when a vault change (`keys`, vs. the vault `before` it) touches a document
    already signed: a signed document never changes, so a person decides whether it is re-signed.
    Shared by the secure form and update_draft."""
    after = svc.vault.veteran()
    changed = [k for k in keys if _dotted(before, k) not in (None, "", _dotted(after, k))]
    signed = [f for f in FORM_KEYS if changed and (d := svc.live(f)) and d.status != "draft"]
    if not signed:
        return None
    return Task(kind="staff", text=f"The veteran changed {', '.join(changed)} {how} after signing the "
                f"{' and '.join(signed)}: the signed version still has the old values. Check whether it "
                "needs a new signature.")  # fmt: skip


def fee_change_task(svc: PoaService, case: CaseFile) -> Task | None:
    """A staff task when the fee the rules give now differs from the signed fee agreement's (prior
    representation re-recorded after signing). Added once per new fee."""
    doc = svc.live("fee_agreement")
    signed, pct = (doc.terms.get("fee_pct") if doc and doc.status != "draft" else None), fee_pct(case)
    if signed is None or pct == signed:
        return None
    text = (f"Fee mismatch: the signed fee agreement says {signed}%, but the firm's rules now give "
            f"{'no fee yet (prior representation unknown)' if pct is None else f'{pct}%'} after prior "
            "representation was re-recorded. Decide whether a new fee agreement is needed.")  # fmt: skip
    return None if any(t.text == text for t in case.tasks) else Task(kind="staff", text=text)


def submit_secure_form(rt, case_id: str, request_id: str, values: dict[str, str]) -> dict[str, str]:
    """The veteran submitted a secure form. Values go to the vault; the case file gets only the
    masked contact fields (source "secure form"); live drafts are re-rendered. A value changed after
    a document was signed gets a staff task (the signed version keeps the old one). Returns
    {field: error} for rejected values."""
    svc = service(rt, case_id)
    before = svc.vault.veteran()
    errors = svc.complete_capture_request(request_id, values)
    stored = sorted(k for k in values if k in svc.vault.masked() and k not in errors)
    refreshed = refresh_drafts(rt, case_id, svc)
    task = signed_change_task(svc, before, stored, "on a secure form")
    answers = masked_answers(svc, stored, "secure form")

    def apply(case: CaseFile) -> None:
        answers(case)
        if task:
            case.tasks.append(task)

    rt.event(case_id, "secure_form_submitted", {"request_id": request_id, "stored": stored,
             "rejected": sorted(errors), "drafts_refreshed": refreshed}, actor="veteran",
             apply=apply)  # fmt: skip
    return errors


def _dotted(d: dict, name: str):
    for part in name.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def save_signature(rt, case_id: str, data_uri: str) -> None:
    service(rt, case_id).save_signature(data_uri)
    rt.event(case_id, "signature_saved", {}, actor="veteran")


def sign(rt, case_id: str, form: str, consent_text: str, ip: str = "", user_agent: str = "",
         shown: tuple[str, int] | None = None) -> None:
    """The veteran clicked Sign on `form`'s Sign card (the only way a document is signed). `shown`:
    the (document_id, version) on that card; the draft must still be exactly that one."""
    svc = service(rt, case_id)
    doc = svc.live(form)
    if doc is None:
        raise ValueError(f"no {form} to sign")
    if shown is not None and (doc.id, doc.version) != tuple(shown):
        raise ValueError("the document changed after this Sign button was shown: review the new version")
    if form == "fee_agreement" and doc.terms.get("fee_pct") != fee_pct(rt.store.get_case(case_id)):
        raise ValueError("the fee terms changed since this draft was shown (prior representation was "
                         "re-recorded): the fee agreement must be prepared again")  # fmt: skip
    doc = svc.sign(doc.id, consent_text=consent_text, ip=ip, user_agent=user_agent,
                   expected_version=shown[1] if shown is not None else None)

    def apply(case: CaseFile) -> None:
        case.documents[form] = DocState(document_id=doc.id, signed_at=doc.signed_at)

    rt.event(case_id, "signed", {"form": form, "document_id": doc.id}, actor="veteran", apply=apply)


def countersign(rt, case_id: str, by: str) -> None:
    """Staff: the attorney countersigns both documents in one action. Each gets a stamped
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
        due = date.fromisoformat(clock.local_date(done["fee_agreement"].signed_at)) + timedelta(days=OGC_DAYS)
        if "fee_agreement" not in case.filings:
            case.tasks.append(Task(kind="deadline", text=OGC_TASK, due=due.isoformat()))

    rt.event(case_id, "countersigned", {"by": by, "attorney": attorney, "forms": list(done)},
             actor="staff", apply=apply)  # fmt: skip

