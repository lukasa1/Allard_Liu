"""The intake sub-agent (L14-L21): pass 1 screens, signs and files; pass 2 closes the gaps.

One ReAct turn per veteran message or event (the harness). Working memory lives in the case file,
so every turn starts from it (L15, L18): the checklist is rebuilt from the answers, and the
context shows every known field with its source, the typed list of what is missing, the
documents and the last 12 messages.

Tools: read_skill (harness), kb_search, get_case, record_answer, fill_pdf, request_secure_info,
update_draft, get_signature, submit_va, efax_ogc. The reply output is the only channel to the
veteran. Guards (L17), in code: ID numbers only through the secure form; no tool signs (signing is
the veteran's click, countersigning a staff action: agent/intake/documents.py); filing waits for
the countersign; the fee agreement goes to OGC only once signed and countersigned; the firm's stop
rules run on every answer (checklist.stop_rule).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.casefile import STAGE_NAMES, Answer, CaseFile, DocState, Filing, now
from agent.harness import AgentSpec, Turn, conversation
from agent.ingest import redact_chat
from agent.intake import checklist
from agent.intake.documents import OGC_TASK, service
from agent.kb import kb_tool
from agent.tools.registry import NoArgs, ToolSpec
from poa_skill.fee_agreement import REQUIRED_CLIENT_FIELDS
from poa_skill.form_21_22a import REQUIRED_VETERAN_FIELDS
from poa_skill.service import CONSENT_KEYS, FORMS
from poa_skill.tools import form_card, preview_card
from poa_skill.vault import FIELDS

HISTORY = 12
FormKey = Literal["21-22a", "fee_agreement"]
SecureField = Literal[tuple(FIELDS)]  # type: ignore[valid-type]

INSTRUCTIONS = """You are intake for a law firm that represents veterans before VA. You talk with \
one veteran in a web chat. Your context holds the case file: every known field with its source, the \
checklist of what is still missing, the documents and the recent messages.

Pass 1 (stages 1-2): screen the veteran (read `screen-veteran`), then get the 21-22a and the fee \
agreement signed (`poa-and-fees`), wait for the attorney's countersign, then file the 21-22a and the \
intent to file (`intent-to-file`) and fax the fee agreement to VA's Office of General Counsel.
Pass 2 (stage 4): close the gaps the C-file left (`close-gaps`).

Rules:
- Save every answer the moment you hear it with record_answer, one call per field. Code parses \
simple fields and runs the firm's stop rules; if one fires, tell the veteran kindly and finish.
- Ask one or two questions per message, in plain warm words. Never ask for a Social Security \
number, date of birth, VA file number or service number in chat: request_secure_info opens a secure form.
- Answer general questions only from kb_search. Never give legal advice, predict a rating or an \
outcome, or promise a date. If kb_search has no answer, say a person on the team will follow up.
- You cannot sign anything. get_signature only shows the veteran a Sign card; call it only after \
the veteran has seen the document and clearly said yes.
- Messages starting with [event] come from the app or the staff (a secure form submitted, a \
signature saved, a document signed, the attorney's countersign), not from the veteran.
- When a tool shows the veteran something (a form, a preview, a Sign card), finish the turn and \
let them act."""


def _svc(turn: Turn):
    return service(turn.rt, turn.case_id)


def _part(case: CaseFile) -> str:
    return "pass2" if case.stage >= 4 else "screen"


def _post(turn: Turn, card: dict) -> None:
    turn.rt.post_card(turn.case_id, "intake", card)


# ------------------------------------------------------------------------------ memory


class RecordArgs(BaseModel):
    q: str = Field(description="a checklist id: a question id, confirm:<question id>, or narrative:<condition>:<prompt id>")
    a: str = Field(description="the veteran's answer in their words (or a JSON value for a structured field)")
    unknown: bool = Field(False, description="true when the veteran doesn't know or declines to say")


def record_answer(turn: Turn, args: RecordArgs) -> dict:
    key = args.q.removeprefix("confirm:")
    try:
        value = None if args.unknown else checklist.parse(key, args.a)
    except ValueError as err:
        return {"saved": False, "error": f"could not read {args.a!r} for {key}: {err}. Ask again, or "
                "pass the value as JSON, or set unknown if the veteran doesn't know."}  # fmt: skip
    answer = Answer(value=value, source=f"veteran, chat {now()[11:16]} UTC", raw=args.a, unknown=args.unknown)

    def apply(case: CaseFile) -> None:
        case.answers[key] = answer
        for c in case.conflicts:
            if c.question == key and not c.resolved_at:
                c.resolved_at = answer.at
        checklist.refresh(case)

    case = turn.rt.patch(turn.case_id, apply, actor="intake")
    out: dict[str, Any] = {"saved": key, "value": value, "stage": case.stage}
    if case.stop:
        out["stop_rule"] = case.stop.model_dump()
        out["note"] = f"A firm stop rule fired; the case is {case.side_state}. Tell the veteran kindly and finish."
    else:
        left = case.missing(_part(case)) or []
        out["still_missing"] = {"count": len(left), "next": left[:6]}
    return out


def get_case(turn: Turn) -> dict:
    return {"case": turn.case.memory(), "documents": _svc(turn).status()}


# ------------------------------------------------------------------------------ documents


class FillArgs(BaseModel):
    form: FormKey
    fields: dict[str, bool] = Field(
        default_factory=dict,
        description="21-22a: the veteran's own answers to Item 20 (authorize_7332_records) and Item 22 "
        "(authorize_address_change). Fee agreement: {} (the fee comes from the firm's rules).",
    )


class SecureArgs(BaseModel):
    fields: list[SecureField] = Field(min_length=1)
    purpose: str = Field(min_length=3, description="one plain sentence shown above the form: why you need it")


class DraftArgs(BaseModel):
    form: FormKey
    changes: dict[str, Any] = Field(description='e.g. {"address.city": "Waukesha"}; ID numbers only by secure form')


class FormArgs(BaseModel):
    form: FormKey


def fill_pdf(turn: Turn, args: FillArgs) -> dict:
    svc = _svc(turn)
    if args.form == "21-22a":
        doc = svc.prepare(args.fields)
    else:
        doc = svc.prepare(form_key="fee_agreement", terms={"fee_pct": checklist.fee_pct(turn.case)})
    turn.rt.patch(turn.case_id, lambda c: c.documents.__setitem__(args.form, DocState(document_id=doc.id)), "intake")
    _post(turn, preview_card(svc, doc))
    return {**svc.describe(doc), "note": "The preview is showing. Ask the veteran to check it; call "
            "get_signature only after a clear yes."}  # fmt: skip


def request_secure_info(turn: Turn, args: SecureArgs) -> dict:
    req = _svc(turn).create_capture_request(list(args.fields), args.purpose)
    _post(turn, form_card(req))
    return {"request_id": req["id"], "note": "The secure form is open. Don't ask for these values in "
            "chat; an [event] tells you when it is submitted."}  # fmt: skip


def update_draft(turn: Turn, args: DraftArgs) -> dict:
    svc = _svc(turn)
    doc = svc.live(args.form)
    if doc is None:
        return {"error": f"no {args.form} draft: call fill_pdf first"}
    doc = svc.edit(doc.id, args.changes, actor="intake")
    _post(turn, preview_card(svc, doc))
    return {**svc.describe(doc), "note": "The preview is updated. Ask the veteran to check it again."}


def get_signature(turn: Turn, args: FormArgs) -> dict:
    svc = _svc(turn)
    doc = svc.live(args.form)
    if doc is None or doc.status != "draft":
        return {"error": f"no unsigned {args.form} draft" + ("" if doc else ": call fill_pdf first")}
    if not svc.vault.has_signature():
        _post(turn, {"type": "signature_pad"})
        return {"status": "signature pad open", "note": "Wait for the veteran to draw and save a "
                "signature, then call get_signature again."}  # fmt: skip
    ok, why = svc.ready_to_sign(doc.id)
    if not ok:
        return {"ready": False, "reason": why}
    _post(turn, {"type": "sign_button", "form": args.form, "document_id": doc.id,
                 "consent_text": FORMS[args.form].consent})  # fmt: skip
    return {"ready": True, "note": "The Sign card is showing. Only the veteran's click signs. Wait."}


# ------------------------------------------------------------------------------ filing


class SubmitArgs(BaseModel):
    form: Literal["21-22a", "itf"]


class FaxArgs(BaseModel):
    doc: Literal["fee_agreement"]


def submit_va(turn: Turn, args: SubmitArgs) -> dict:
    """Simulated filing with VA (L21): a fake confirmation number; the ITF date for the ITF."""
    data = {}
    if args.form == "itf":
        today = date.today()
        data = {"itf_date": today.isoformat(), "expires": (today + timedelta(days=365)).isoformat()}
    filing = Filing(confirmation=f"VA-{uuid.uuid4().hex[:10].upper()}", data=data)
    case = turn.rt.patch(turn.case_id, lambda c: c.filings.__setitem__(args.form, filing), "intake")
    return {"filed": args.form, "confirmation": filing.confirmation, **data, "stage": case.stage}


def efax_ogc(turn: Turn, args: FaxArgs) -> dict:
    """Simulated eFax of the countersigned fee agreement to VA's Office of General Counsel."""
    filing = Filing(confirmation=f"FAX-{uuid.uuid4().hex[:10].upper()}", data={"to": "VA Office of General Counsel"})

    def apply(case: CaseFile) -> None:
        case.filings[args.doc] = filing
        for t in case.tasks:
            if t.text == OGC_TASK and t.done_at is None:
                t.done_at = filing.at

    turn.rt.patch(turn.case_id, apply, actor="intake")
    return {"faxed": args.doc, "confirmation": filing.confirmation}


# ------------------------------------------------------------------------------ guard


def _countersigned(case: CaseFile, form: str) -> bool:
    doc = case.documents.get(form)
    return bool(doc and doc.signed_at and doc.countersigned_at)


def guard(turn: Turn, name: str, args: BaseModel) -> str | None:
    case = turn.case
    if name == "record_answer":
        key = args.q.removeprefix("confirm:")
        try:
            checklist.question_type(key)
        except KeyError:
            return f"no checklist field {args.q!r}: use an id from your checklist"
        if key in checklist.SKIP:
            return f"{key} is not asked as a question"
        if key.startswith("narrative:") and key.split(":")[1] not in checklist.record(case).claim_conditions:
            return f"{key.split(':')[1]!r} is not a claimed condition; record claim_conditions first"
        if redact_chat(args.a)[1]:
            return "ID numbers and dates of birth never go in chat or the case file: use request_secure_info"
        if checklist.BANK.by_id.get(key) and checklist.BANK.by_id[key].source == "secure_form" and not args.unknown:
            return f"{key} is collected by the secure form: use request_secure_info"
        return None
    if name == "fill_pdf":
        if case.stop:
            return f"stop rule {case.stop.rule} fired: nothing is prepared"
        if case.stage < 2:
            return f"screening isn't finished: still missing {', '.join(case.missing('screen') or ['(not built)'])}"
        if case.documents.get(args.form) and case.documents[args.form].signed_at:
            return f"the {args.form} is already signed"
        veteran = _svc(turn).vault.veteran()
        needed = REQUIRED_VETERAN_FIELDS if args.form == "21-22a" else REQUIRED_CLIENT_FIELDS
        gaps = [k for k in needed if not _get(veteran, k)]
        if gaps:
            return f"call request_secure_info first for: {', '.join(gaps)}"
        if args.form == "21-22a" and set(args.fields) != set(CONSENT_KEYS):
            return f"ask the veteran about Items 20 and 22 first, then pass both: {', '.join(CONSENT_KEYS)}"
        return None
    if name == "submit_va":
        if args.form in case.filings:
            return f"the {args.form} is already filed ({case.filings[args.form].confirmation})"
        if not _countersigned(case, "21-22a"):
            return "the 21-22a must be countersigned by the attorney first"
        return None
    if name == "efax_ogc":
        if args.doc in case.filings:
            return f"the {args.doc} was already sent ({case.filings[args.doc].confirmation})"
        if not _countersigned(case, "fee_agreement"):
            return "the fee agreement must be signed and countersigned first"
    return None


def _get(d: dict, dotted: str):
    for part in dotted.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


# ------------------------------------------------------------------------------ context


def _fee_line(case: CaseFile) -> str:
    pct = checklist.fee_pct(case)
    if pct is None:
        return "not set yet (prior representation unknown)"
    paid = "VA withholds it and pays the attorney" if pct <= 20 else "the client pays the firm directly"
    return f"{pct}% of past-due benefits, contingent (firm-policy placeholder); {paid}"


def context(turn: Turn) -> str:
    case = turn.rt.patch(turn.case_id, checklist.refresh, actor="intake")  # rebuilt every turn (L18)
    part, status = _part(case), _svc(turn).status()
    known = [f"- {k}: {'UNKNOWN' if a.unknown else json.dumps(a.value)} ({a.source})" for k, a in case.answers.items()]
    items = checklist.missing(case, part)
    docs = [{k: d[k] for k in ("kind", "status", "version", "missing", "consents", "terms")}
            for d in status["documents"] if d["status"] != "superseded"]  # fmt: skip
    this_pass = "Pass 2 (stage 4): close the gaps." if part == "pass2" else "Pass 1 (stages 1-2): screen, sign, file."
    stop = case.stop.rule if case.stop else "none"
    sections = {
        "This pass": f"{this_pass} Goal from the orchestrator: {case.goal}",
        "Case": f"stage {case.stage} ({STAGE_NAMES[case.stage]}); side state: {case.side_state}; stop rule: {stop}",
        "Known fields (value, source)": "\n".join(known) or "(none)",
        f"Missing ({part} checklist, {len(items)} left)": "\n".join(i.model_dump_json() for i in items) or "(none)",
        "Documents": "\n".join([
            f"secure form on file (masked): {json.dumps(status['captured'])}",
            f"signature on file: {status['signature_on_file']}; pending secure forms: {status['pending_secure_forms']}",
            f"documents: {json.dumps(docs)}",
            f"signed / countersigned: {json.dumps({k: v.model_dump() for k, v in case.documents.items()})}",
        ]),
        "Fee": _fee_line(case),
        "Filings": json.dumps({k: v.model_dump() for k, v in case.filings.items()}) if case.filings else "none",
        "Open tasks": "\n".join(f"- {t.text} (due {t.due})" for t in case.tasks if not t.done_at) or "none",
        f"Last {HISTORY} messages": conversation(turn, HISTORY),
    }
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections.items())


def tools(turn: Turn) -> list[ToolSpec]:
    return [
        kb_tool(turn),
        ToolSpec("get_case", "Reload the case file and the documents' status (masked).", NoArgs,
                 lambda a: get_case(turn)),
        ToolSpec("record_answer", "Save one answer the moment the veteran gives it (code parses it, "
                 "keeps the raw text and records the source). Rebuilds the checklist and runs the "
                 "firm's stop rules.", RecordArgs, lambda a: record_answer(turn, a)),
        ToolSpec("fill_pdf", "Fill the 21-22a or the fee agreement from the secure form and the "
                 "firm's details, and show the veteran a preview.", FillArgs, lambda a: fill_pdf(turn, a)),
        ToolSpec("request_secure_info", "Open a secure form outside the chat for ID numbers, date of "
                 "birth, name and contact details. You only ever see masked values.", SecureArgs,
                 lambda a: request_secure_info(turn, a)),
        ToolSpec("update_draft", "Correct fields on an unsigned draft when the veteran asks, and "
                 "refresh the preview.", DraftArgs, lambda a: update_draft(turn, a)),
        ToolSpec("get_signature", "Show the signature pad (if no signature is saved yet) or the Sign "
                 "card for a reviewed draft. Only the veteran's click signs.", FormArgs,
                 lambda a: get_signature(turn, a)),
        ToolSpec("submit_va", "File the countersigned 21-22a, or the intent to file, with VA "
                 "(simulated).", SubmitArgs, lambda a: submit_va(turn, a)),
        ToolSpec("efax_ogc", "Fax the signed and countersigned fee agreement to VA's Office of "
                 "General Counsel (simulated).", FaxArgs, lambda a: efax_ogc(turn, a)),
    ]  # fmt: skip


def spec() -> AgentSpec:
    return AgentSpec(
        name="intake", instructions=INSTRUCTIONS, tools=tools, context=context, guard=guard,
        stop=lambda c: c.stage in (3, 5) or c.parked, max_iters=8, timeout_s=120,
    )  # fmt: skip
