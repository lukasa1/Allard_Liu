"""Shared scripts and case-file fixtures for tests that drive the real intake agent."""

from helpers import FILED, PREP_DONE

from agent.casefile import Answer, CaseFile, DocState
from agent.intake import checklist
from agent.scripted.lm import call

T = "2026-11-03T10:00:00+00:00"
CONSENTS = {"authorize_7332_records": True, "authorize_address_change": False}

# A veteran who passes screening: Army 2004-2010, honorable, never filed, no prior attorney.
SCREEN_STEPS = (
    call("record_answer", q="is_veteran", a="Yes, I served"),
    call("record_answer", q="service_periods", a="Army, active duty, 2004-06 to 2010-05, honorable"),
    call("record_answer", q="other_service_periods", a="No, that's it"),
    call("record_answer", q="filed_before", a="No"),
    call("record_answer", q="prior_claim_probe", a="No, never"),
    call("record_answer", q="prior_attorney", a="No"),
)


def screened(**kw) -> CaseFile:
    """A case at stage 2 whose screening answers came from SCREEN_STEPS."""
    case = CaseFile(case_id="c1", stage=2, owner="intake", goal="Pass 1", **kw)
    for step in SCREEN_STEPS:
        q, a = step.args["q"], step.args["a"]
        case.answers[q] = Answer(value=checklist.parse(q, a), source="veteran, chat", raw=a)
    checklist.refresh(case)
    return case


def prefill_pass2(case: CaseFile, leave: tuple[str, ...] = ()) -> None:
    """What claims prep's prefill (step 4) would write, as a fixture: the claimed condition from
    the C-file, and every other pass-2 field settled (unknown) except `leave`."""
    case.answers["claim_conditions"] = Answer(value=["tinnitus"], source="C-file p. 4")
    while todo := [i for i in checklist.missing(case, "pass2") if i.id not in leave and not i.id.startswith("confirm:")]:
        for item in todo:
            case.answers[item.id] = Answer(value=None, source="C-file p. 2", unknown=True)


def answered(rt, stage: int, leave: tuple[str, ...] = (), case_id: str = "c", **kw) -> str:
    """A filed case after claims prep at `stage`, every pass-2 field settled except `leave`."""
    case = CaseFile(case_id=case_id, stage=stage, prep=PREP_DONE, filings=FILED, checklist={"screen": [], "pass2": []},
                    **kw)  # fmt: skip
    prefill_pass2(case, leave)
    checklist.refresh(case)
    return rt.store.create_case(case).case_id


def sign_both(case: CaseFile) -> None:
    """Case-file shortcut for both documents signed (no PDFs)."""
    case.documents = {f: DocState(signed_at=T) for f in ("21-22a", "fee_agreement")}
