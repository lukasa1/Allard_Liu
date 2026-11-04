"""The tool calls a correct reading of a persona's synthetic C-file makes, built from its ground
truth: claims prep's script in the tests and in the scripted demo."""

from __future__ import annotations

from agent import clock
from agent.cfile import vbms
from agent.cfile.facts import truth_facts
from agent.claims_prep.prefill import QUESTIONS
from agent.personas import get_persona
from agent.scripted.lm import call
from poa_skill.service import load_representative


def firm() -> str:
    rep = load_representative()
    return f"{rep['first_name']} {rep['last_name']}, {rep['firm_name']}"


def the_cfile(persona: str) -> vbms.CFile:
    """The C-file claims prep will pull: the firm's own 21-22a is filed today."""
    return vbms.pull(persona, (firm(), clock.today().isoformat()))


def cite(doc: vbms.Document, last: bool = False) -> dict:
    return {"doc_id": doc.doc_id, "page": doc.page_numbers[-1] if last else doc.first_page}


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
        if t.mos:  # every DD-214 shows a specialty (synth reuses the last MOS)
            out.append({"kind": "mos", "mos": t.mos[min(i, len(t.mos) - 1)], "cite": c})
    for d in t.decisions:
        rd = cite(dated[("rating_decision", d.decision_date)])
        out.append({"kind": "decision", "date": d.decision_date, "form": d.form, "filed": d.filed, "cite": rd,
                    "issues": [i.model_dump() for i in d.issues]})  # fmt: skip
        if d.notified:
            out.append({"kind": "notification_letter", "date": d.notified, "decision_date": d.decision_date,
                        "cite": cite(dated[("notification_letter", d.notified)])})  # fmt: skip
    if t.combined_rating is not None:
        newest = cite(
            of["rating_decision"][-1], last=True
        )  # the code sheet is the decision's last page
        out.append({"kind": "combined_rating", "pct": t.combined_rating, "cite": newest})
        out += [
            {"kind": "rated_condition", "condition": c.name, "pct": c.rating_pct, "cite": newest}
            for c in t.sc_conditions
        ]
    reps = [*t.prior_reps, None]  # the firm's own 21-22a comes last
    for rep, doc in zip(reps, of["poa_form"], strict=True):
        name, kind, signed = (
            (rep.name, rep.kind, rep.signed)
            if rep
            else (firm(), "attorney", clock.today().isoformat())
        )
        out.append(
            {
                "kind": "prior_representative",
                "name": name,
                "rep_type": kind,
                "signed": signed,
                "cite": cite(doc),
            }
        )
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
