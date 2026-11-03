"""Shared scripts and case-file fixtures for tests that drive the real intake agent."""

from fake_lm import call

from agent.casefile import Answer, CaseFile, DocState
from agent.intake import checklist

T = "2026-11-03T10:00:00+00:00"

# A veteran who passes screening: Army 2004-2010, honorable, never filed, no prior attorney.
SCREEN_STEPS = (
    call("record_answer", q="is_veteran", a="Yes, I served"),
    call("record_answer", q="service_periods", a="Army, active duty, 2004-06 to 2010-05, honorable"),
    call("record_answer", q="other_service_periods", a="No, that's it"),
    call("record_answer", q="filed_before", a="No"),
    call("record_answer", q="prior_claim_probe", a="No, never"),
    call("record_answer", q="prior_attorney", a="No"),
)


def prefill_pass2(case: CaseFile, leave: tuple[str, ...] = ()) -> None:
    """What claims prep's prefill (step 4) would write, as a fixture: the claimed condition from
    the C-file, and every other pass-2 field settled (unknown) except `leave`."""
    case.answers["claim_conditions"] = Answer(value=["tinnitus"], source="C-file p. 4")
    while todo := [i for i in checklist.missing(case, "pass2") if i.id not in leave and not i.id.startswith("confirm:")]:
        for item in todo:
            case.answers[item.id] = Answer(value=None, source="C-file p. 2", unknown=True)


def sign_both(case: CaseFile) -> None:
    """Case-file shortcut for both documents signed (no PDFs: the orchestrator tests)."""
    case.documents = {f: DocState(signed_at=T) for f in ("21-22a", "fee_agreement")}


def countersign_both(case: CaseFile) -> None:
    for d in case.documents.values():
        d.countersigned_at, d.countersigned_by = T, "Attorney 1"
