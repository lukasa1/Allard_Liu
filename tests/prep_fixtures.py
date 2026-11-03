"""Shared fixtures for tests that drive the real claims-prep agent: a case at stage 3. Its
script (a correct reading of the C-file) is agent/scripted/prep.py."""

from agent.casefile import CaseFile, Filing
from agent.intake.documents import service

ITF = "2026-11-03"


def filed() -> dict[str, Filing]:
    return {"21-22a": Filing(confirmation="A"), "itf": Filing(confirmation="B", data={"itf_date": ITF}),
            "fee_agreement": Filing(confirmation="FAX-1")}  # fmt: skip


def fee_agreement(rt, cid: str, pct: int = 30) -> None:
    """The case's fee agreement with its terms (the face note's header reads the fee from it)."""
    service(rt, cid).prepare(form_key="fee_agreement", terms={"fee_pct": pct})


def case_at_stage_3(rt, persona: str, cid: str = "c1", **fields) -> str:
    cid = rt.store.create_case(
        CaseFile(case_id=cid, persona_id=persona, stage=3, filings=filed(), **fields)
    ).case_id
    fee_agreement(rt, cid)
    return cid
