"""Synthetic veterans: a hidden ground-truth record, how the person behaves, and what VA holds.

Every persona is made up; none is based on a real client. A persona file
(agent/data/personas/*.yaml) holds only what differs from the defaults below:

  truth     the true intake record (what a perfect intake would collect)
  stories   per condition, what the veteran would say to the narrative prompts
  behaviors scripted habits for the simulated veteran (omit_second_period, ...)
  says      how they name conditions in everyday words
  expected  decision / fee_pct (and flag_decision) a correct case should reach
  identity  synthetic DOB, SSN, middle initial (for the POA skill's secure form)
  cfile     the synthetic C-file: rating decisions, filings, prior 21-22a (see agent/cfile)
  poa       the veteran's answers to the 21-22a's Item 20 and Item 22
  during_prep  the orchestrator scenario (eval): a message the veteran sends while claims prep
            runs ({message, condition}); support should flag the new condition
  believes  truth fields the veteran remembers differently from the records (e.g. a discharge the
            DD-214 shows otherwise): what the simulated veteran plays, and the key when the C-file
            isn't read (the ask / ask_no_probes conditions)

The same personas are the test veterans you can pick in the demo.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent.intake.schema import IntakeRecord

PERSONAS_DIR = Path(__file__).resolve().parent / "data" / "personas"

DEFAULT_TRUTH: dict[str, Any] = {
    "is_veteran": True,
    "first_name": "Jordan",
    "last_name": "Reyes",
    "service_periods": [
        {
            "branch": "army",
            "component": "active",
            "start": "2004-06",
            "end": "2010-05",
            "discharge": "honorable",
        }
    ],
    "filed_before": False,
    "street": "412 Oak Street",
    "city": "Racine",
    "state": "WI",
    "zip": "53403",
    "cell_phone": "262-555-0142",
    "email": "jordan.reyes@example.com",
    "prior_attorney": False,
    "dic_claim": False,
    "earning_over_1600": True,
    "receives_ssa": False,
    "ssa_interest": False,
    "partner_share_consent": True,
    "mos": ["88M Motor Transport Operator"],
    "retired": False,
    "exposures": ["burn pits"],  # DEFAULT_STORY is set at Camp Taji, Iraq (a PACT Act location)
    "litigation_contact": False,
    "claim_conditions": ["tinnitus"],
    "other_conditions": [],
    "marital_status": "single",
    "children_under_18": False,
    "next_of_kin": "Maria Reyes, mother, 262-555-0177",
    "heard_about": "a friend",
}

DEFAULT_STORY: dict[str, str] = {
    "h02": "A constant high-pitched ringing in both ears.",
    "h03": "On bad days it's so loud I can't concentrate or fall asleep.",
    "h04": "It started during service, after a convoy hit an IED near Baghdad in 2007.",
    "h05": "Every day.",
    "h06": "It never went away after I got out, and it's gotten a little worse.",
    "h07": "Camp Taji, Iraq.",
    "h08": "In a vehicle, on convoys through a combat zone.",
    "h09": "Constant engine noise, gunfire and explosions, usually without good hearing protection.",
    "h10": "The IED blast in 2007, plus years of truck and weapons noise.",
    "h11": "No. Everyone had ringing ears and I didn't want to be pulled off missions.",
    "h12": "I drive a delivery truck now and it's hard to hear dispatch over the ringing.",
    "h13": "I've left early a few times when it gets really bad, maybe once a month.",
    "h14": "I avoid restaurants and parties, and I sleep with a fan on to drown it out.",
    "h15": "Before the Army I had no hearing problems at all.",
    "h16": "No, I think that covers it.",
}


@dataclass
class Persona:
    id: str
    summary: str
    truth: IntakeRecord
    stories: dict[str, dict[str, str]]  # condition -> prompt id -> what the veteran would say
    behaviors: list[str] = field(default_factory=list)
    says: dict[str, str] = field(default_factory=dict)  # canonical condition -> how they say it
    style: str = ""
    expected: dict[str, Any] = field(default_factory=dict)  # decision, fee_pct, flag_decision
    identity: dict[str, str] = field(default_factory=dict)  # dob, ssn, middle_initial
    typed: dict[str, str] = field(default_factory=dict)  # secure-form field -> the wrong value the veteran types
    asks: dict[str, Any] = field(default_factory=dict)  # at_reply (1-based) or after: itf_filed; text: sent instead of that reply; answer_key; expects: kb | person
    split: str = "dev"  # dev: the system was developed against it; heldout: not fixed against directly
    cfile: dict[str, Any] = field(default_factory=dict)
    poa: dict[str, bool] = field(default_factory=dict)
    during_prep: dict[str, str] = field(default_factory=dict)  # message, condition
    believes: dict[str, Any] = field(default_factory=dict)  # truth fields as the veteran remembers them

    @property
    def believed_truth(self) -> IntakeRecord:
        """The record as the veteran remembers it (the truth unless `believes` overrides a field)."""
        if not self.believes:
            return self.truth
        return IntakeRecord.model_validate({**self.truth.model_dump(), **self.believes})

    @property
    def expected_decision(self) -> str:
        return self.expected.get("decision", "eligible")

    @property
    def display_name(self) -> str:
        return f"{self.truth.first_name} {self.truth.last_name}"


def _default_identity(pid: str) -> dict[str, str]:
    h = int(hashlib.sha256(pid.encode()).hexdigest(), 16)
    # SSN area 100-665 and group/serial never zero: valid shape, and synthetic.
    ssn = f"{100 + h % 500:03d}-{10 + (h // 1000) % 89:02d}-{1000 + (h // 10**6) % 8999:04d}"
    year = 1960 + (h // 10**10) % 25
    month = 1 + (h // 10**12) % 12
    day = 1 + (h // 10**14) % 27
    return {"dob": f"{year:04d}-{month:02d}-{day:02d}", "ssn": ssn, "middle_initial": ""}


def load_persona(path: Path) -> Persona:
    data = yaml.safe_load(path.read_text())
    truth = copy.deepcopy(DEFAULT_TRUTH)
    if (data.get("truth") or {}).get("is_veteran") is False:  # never served: no default service facts
        truth.update(mos=[], exposures=[], litigation_contact=None, claim_conditions=[], other_conditions=[], retired=False)  # else the
    truth.update(data.get("truth", {}))  # default Army MOS and Iraq story would make the simulator say it served
    stories = data.get("stories") or {}
    for condition in truth.get("claim_conditions", []):
        stories.setdefault(condition, DEFAULT_STORY if condition == "tinnitus" else {})
    identity = _default_identity(data["id"])
    identity.update({k: str(v) for k, v in (data.get("identity") or {}).items()})
    return Persona(
        id=data["id"],
        summary=data.get("summary", ""),
        truth=IntakeRecord.model_validate(truth),
        stories=stories,
        behaviors=list(data.get("behaviors", [])),
        says=dict(data.get("says", {})),
        style=data.get("style", ""),
        expected=dict(data.get("expected", {})),
        identity=identity,
        typed={k: str(v) for k, v in (data.get("typed") or {}).items()},
        asks=dict(data.get("asks") or {}),
        split=str(data.get("split", "dev")),
        cfile=dict(data.get("cfile") or {}),
        poa={
            "authorize_7332_records": True,
            "authorize_address_change": True,
            **(data.get("poa") or {}),
        },
        during_prep=dict(data.get("during_prep") or {}),
        believes=dict(data.get("believes") or {}),
    )


def load_personas(selection: str = "all", directory: Path = PERSONAS_DIR) -> list[Persona]:
    paths = sorted(directory.glob("*.yaml"))
    personas = [load_persona(p) for p in paths]
    if selection == "all":
        return personas
    wanted = [s.strip() for s in selection.split(",") if s.strip()]
    by_id = {p.id: p for p in personas}
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise SystemExit(
            f"unknown persona(s): {', '.join(missing)}. Available: {', '.join(sorted(by_id))}"
        )
    return [by_id[w] for w in wanted]


def get_persona(pid: str) -> Persona:
    (persona,) = load_personas(pid)
    return persona
