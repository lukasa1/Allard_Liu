"""Shared scripts for tests that drive the real claims-prep agent: a case at stage 3, and the
tool calls a correct reading of a persona's synthetic C-file makes (built from its ground truth)."""

from datetime import UTC, datetime

from fake_lm import call

from agent.casefile import CaseFile, Filing
from agent.cfile import vbms
from agent.cfile.facts import truth_facts
from agent.claims_prep.prefill import QUESTIONS
from agent.intake.documents import service
from agent.personas import get_persona

FIRM = "Attorney 1, Law Firm"
ITF = "2026-11-03"


def filed() -> dict[str, Filing]:
    return {"21-22a": Filing(confirmation="A"), "itf": Filing(confirmation="B", data={"itf_date": ITF}),
            "fee_agreement": Filing(confirmation="FAX-1")}  # fmt: skip


def fee_agreement(rt, cid: str, pct: int = 30) -> None:
    """The case's fee agreement with its terms (the face note's header reads the fee from it)."""
    service(rt, cid).prepare(form_key="fee_agreement", terms={"fee_pct": pct})


def case_at_stage_3(rt, persona: str, cid: str = "c1", **fields) -> str:
    cid = rt.store.create_case(CaseFile(case_id=cid, persona_id=persona, stage=3, filings=filed(), **fields)).case_id
    fee_agreement(rt, cid)
    return cid


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def the_cfile(persona: str) -> vbms.CFile:
    """The C-file claims prep will pull: the firm's own 21-22a is filed today."""
    return vbms.pull(persona, (FIRM, _today()))


def cite(doc: vbms.Document) -> dict:
    return {"doc_id": doc.doc_id, "page": doc.first_page}


def truth_batch(persona: str) -> list[dict]:
    """Every fact the face note needs, each citing the page it is on."""
    t, cf = truth_facts(get_persona(persona)), the_cfile(persona)
    of = {k: [d for d in cf.docs if d.type == k] for k in ("dd214", "rating_decision", "notification_letter",
                                                            "claim_form", "poa_form")}  # fmt: skip
    dated = {(d.type, d.date): d for d in cf.docs}
    out: list[dict] = []
    for i, sp in enumerate(t.service_periods):
        c = cite(of["dd214"][i])
        if i == 0 and t.dob:
            out.append({"kind": "dob", "dob": t.dob, "cite": c})
        out += [{"kind": "service_period", "branch": sp.branch, "component": sp.component, "start": sp.start,
                 "end": sp.end, "cite": c},
                {"kind": "discharge", "period_start": sp.start, "character": sp.discharge, "cite": c}]  # fmt: skip
        if i < len(t.mos):
            out.append({"kind": "mos", "mos": t.mos[i], "cite": c})
    for d in t.decisions:
        rd = cite(dated[("rating_decision", d.decision_date)])
        out.append({"kind": "decision", "date": d.decision_date, "form": d.form, "filed": d.filed, "cite": rd,
                    "issues": [i.model_dump() for i in d.issues]})  # fmt: skip
        if d.notified:
            out.append({"kind": "notification_letter", "date": d.notified, "decision_date": d.decision_date,
                        "cite": cite(dated[("notification_letter", d.notified)])})  # fmt: skip
    if t.combined_rating is not None:
        newest = cite(of["rating_decision"][-1])
        out.append({"kind": "combined_rating", "pct": t.combined_rating, "cite": newest})
        out += [{"kind": "rated_condition", "condition": c.name, "pct": c.rating_pct, "cite": newest} for c in t.sc_conditions]
    reps = [*t.prior_reps, None]  # the firm's own 21-22a comes last
    for rep, doc in zip(reps, of["poa_form"], strict=True):
        name, kind, signed = (rep.name, rep.kind, rep.signed) if rep else (FIRM, "attorney", _today())
        out.append({"kind": "prior_representative", "name": name, "rep_type": kind, "signed": signed, "cite": cite(doc)})
    for pf in t.pending_filings:
        out.append({"kind": "pending_filing", "form": pf.form, "filed": pf.filed, "conditions": pf.conditions,
                    "cite": cite(dated[("claim_form", pf.filed)])})  # fmt: skip
    return out


def reads(persona: str) -> list:
    return [call("read_pages", doc=d.doc_id) for d in the_cfile(persona).docs if d.type != "other"]


def prep_steps(persona: str) -> list:
    """pull -> read -> record -> render -> verify -> prefill (a turn that passes)."""
    return [call("pull_cfile"), *reads(persona), call("record_facts", facts=truth_batch(persona)),
            call("render"), call("verify"), call("prefill", questions=list(QUESTIONS))]  # fmt: skip
