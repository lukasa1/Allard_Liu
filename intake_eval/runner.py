"""Drive one synthetic veteran through a whole case on the runtime (agent/runtime.py).

The simulated veteran answers the agents' chat messages; the runner uses the cards for it the way
the demo's page does, through the host actions of agent.intake.documents: it fills the secure form
from the persona's synthetic identity, draws a signature and clicks Sign. A simulated attorney
countersigns both documents once the case waits on the attorney (D6). Before reading the outbox or
the case, the runner waits until the runtime is idle (§3: no turn queued or running, claims prep's
background turn included).

The orchestrator scenario (a persona's `during_prep`): right after the countersign, once claims
prep owns the case, the veteran sends that message, so support answers it and flags it.

One run, one runtime: each case has its own store, traces and documents (`make_rt(data_dir)`).
"""

from __future__ import annotations

import base64
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Protocol

from PIL import Image, ImageDraw

from agent.casefile import CaseFile, EvalCondition
from agent.harness import CANNED_REPLY
from agent.intake import documents
from agent.personas import Persona
from agent.runtime import Runtime
from agent.store import Event
from poa_skill.service import WorkflowError

CONDITIONS: tuple[EvalCondition, ...] = EvalCondition.__args__  # ask_no_probes, ask, cfile
MAX_STEPS = 300  # veteran messages + card actions + countersign per case
FAILURES_TO_GIVE_UP = 3  # consecutive canned replies or simulator errors
IDLE_TIMEOUT_S = 900  # a live claims-prep turn reads the whole C-file
ATTORNEY = "simulated attorney"
ACTIONABLE = ("secure_form", "signature_pad", "sign_button")  # a newer card replaces an older one
VAULT_BRANCH = {
    "army": "army", "navy": "navy", "air force": "air_force", "marine corps": "marine_corps",
    "coast guard": "coast_guard", "space force": "space_force",
}  # fmt: skip


def signature_png() -> str:
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(40, 150), (200, 40), (360, 150), (560, 60)], fill=(19, 36, 70, 255), width=6)
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def secure_form_values(p: Persona, fields: list[str]) -> dict[str, str]:
    t = p.truth
    first = t.service_periods[0].branch if t.service_periods else None
    values = {
        "first_name": t.first_name or "", "middle_initial": p.identity.get("middle_initial", ""),
        "last_name": t.last_name or "", "ssn": p.identity["ssn"],
        "date_of_birth": p.identity.get("dob_typed") or p.identity["dob"],
        "branch": VAULT_BRANCH.get(first or "", ""), "address.line1": t.street or "",
        "address.city": t.city or "", "address.state": t.state or "", "address.zip": t.zip or "",
        "phone": t.cell_phone or "", "email": t.email or "", "va_file_number": "", "service_number": "",
    }  # fmt: skip
    return {f: values.get(f, "") for f in fields}


class Veteran(Protocol):
    """What the runner needs from a simulated veteran (intake_eval.simulator.DSPySimulator)."""

    calls: int
    cost: float

    def respond(self, agent_text: str) -> str: ...


@dataclass
class CaseRun:
    persona_id: str
    condition: str
    rt: Runtime
    case_id: str
    sim: Any = None
    transcript: list[dict[str, str]] = field(default_factory=list)  # role: agent | veteran | app
    veteran_actions: int = 0  # chat messages + card actions
    turns_to_signed_poa: int | None = None  # veteran actions until the 21-22a was signed
    steps: int = 0
    hit_step_limit: bool = False
    gave_up: bool = False  # stopped after repeated model failures
    stalled: str = ""  # nothing left to answer, but the case hadn't ended
    stopped_at_cost: bool = False  # --max-cost reached
    model_failures: int = 0  # canned "having trouble" replies + simulator errors
    error: str = ""  # traceback if the run crashed

    @property
    def case(self) -> CaseFile:
        return self.rt.store.get_case(self.case_id)

    @property
    def events(self) -> list[Event]:
        return self.rt.store.events(self.case_id)

    @property
    def traces(self) -> list[dict]:
        return self.rt.harness.traces.read(self.case_id)

    def cost(self) -> float:
        agents = sum(x.get("cost") or 0.0 for x in self.traces if x["kind"] == "lm")
        return agents + (getattr(self.sim, "cost", 0.0) or 0.0)

    @property
    def completed(self) -> bool:
        return not (self.error or self.hit_step_limit or self.gave_up or self.stalled or self.stopped_at_cost)


def finished(case: CaseFile) -> bool:
    """The case reached an end the eval scores: parked, or ready for attorney review."""
    return case.parked or (case.stage >= 5 and case.owner is None)


def run_case(persona: Persona, condition: EvalCondition, make_rt: Callable[[], Runtime], sim: Veteran,
             max_cost: float | None = None, spent: float = 0.0) -> CaseRun:  # fmt: skip
    """`max_cost`: stop when `spent` (earlier runs) plus this run's trace cost passes it."""
    rt = make_rt()
    case = rt.open_case(persona.id, eval_condition=condition)
    run = CaseRun(persona.id, condition, rt, case.case_id, sim=sim)
    try:
        _drive(run, persona, sim, lambda: max_cost is not None and spent + run.cost() > max_cost)
    except Exception as exc:  # noqa: BLE001 - keep the partial transcript; scored as a crash
        run.error = traceback.format_exc()
        run.transcript.append({"role": "app", "text": f"[run crashed: {type(exc).__name__}: {exc}]"})
    return run


def _drive(run: CaseRun, persona: Persona, sim: Veteran, over_budget: Callable[[], bool]) -> None:
    rt, cid = run.rt, run.case_id
    seen, cards, unread, failures = 0, [], [], 0
    while run.steps < MAX_STEPS:
        run.steps += 1
        rt.wait_until_idle(cid, timeout=IDLE_TIMEOUT_S)
        for item in rt.updates(cid, seen):
            seen = item.seq
            if item.kind == "message":
                text = item.payload["text"]
                run.transcript.append({"role": "agent", "text": f"[{item.agent}] {text}"})
                unread.append(text)
                failures = failures + 1 if text == CANNED_REPLY else 0
                run.model_failures += text == CANNED_REPLY
            elif item.payload.get("type") in ACTIONABLE:
                kind = item.payload["type"]
                cards = [c for c in cards if c["type"] != kind] + [item.payload]
        case = run.case
        if over_budget():
            run.stopped_at_cost = True
            return
        if failures >= FAILURES_TO_GIVE_UP:
            run.gave_up = True
            return
        if finished(case):
            return
        if cards:
            _use_card(run, persona, cards.pop(0))
        elif case.side_state == "waiting_on_attorney":
            documents.countersign(rt, cid, by=ATTORNEY)
            run.transcript.append({"role": "app", "text": f"[{ATTORNEY} countersigns both documents]"})
            if persona.during_prep:
                _send_during_prep(run, persona)
        elif not unread:
            run.stalled = f"stage {case.stage} ({case.side_state or case.owner or 'no owner'}): nothing to answer"
            return
        else:
            try:
                reply = sim.respond("\n\n".join(unread))
            except Exception as exc:  # noqa: BLE001 - a refusal, unparseable output, a 429 after retries
                run.model_failures += 1
                failures += 1
                run.transcript.append({"role": "app", "text": f"[simulator failed: {type(exc).__name__}]"})
                continue
            unread = []
            run.transcript.append({"role": "veteran", "text": reply})
            rt.message(cid, reply)
            _acted(run)
    run.hit_step_limit = True


def _acted(run: CaseRun) -> None:
    run.veteran_actions += 1
    doc = run.case.documents.get("21-22a")
    if run.turns_to_signed_poa is None and doc and doc.signed_at:
        run.turns_to_signed_poa = run.veteran_actions


def _use_card(run: CaseRun, persona: Persona, card: dict) -> None:
    """Do what a veteran does with one card, through the host actions (like the demo's page)."""
    rt, cid, kind = run.rt, run.case_id, card["type"]
    if run.case.parked:
        run.transcript.append({"role": "app", "text": f"[{kind} card ignored: the case is {run.case.side_state}]"})
        return
    try:
        if kind == "secure_form":
            values = secure_form_values(persona, [f["name"] for f in card["fields"]])
            errors = documents.submit_secure_form(rt, cid, card["request_id"], values)
            note = f"[veteran fills the secure form: {', '.join(sorted(values))}; errors: {errors or 'none'}]"
        elif kind == "signature_pad":
            documents.save_signature(rt, cid, signature_png())
            note = "[veteran draws and saves a signature]"
        else:
            live = documents.service(rt, cid).live(card["form"])
            if live is None or live.id != card["document_id"]:
                run.transcript.append({"role": "app", "text": f"[Sign card for an old {card['form']} draft ignored]"})
                return
            documents.sign(rt, cid, card["form"], consent_text=card["consent_text"], ip="127.0.0.1",
                           user_agent="eval simulator")  # fmt: skip
            note = f"[veteran clicks Sign on the {card['form']}]"
    except (ValueError, WorkflowError) as err:  # e.g. a secure form that was already submitted
        run.transcript.append({"role": "app", "text": f"[{kind} card no longer valid: {err}]"})
        return
    run.transcript.append({"role": "app", "text": note})
    _acted(run)


def _send_during_prep(run: CaseRun, persona: Persona, timeout_s: float = 120.0) -> None:
    """The orchestrator scenario: message the case while claims prep runs (support answers it)."""
    end = time.monotonic() + timeout_s
    while (case := run.case).owner != "claims_prep":
        if case.prep.done or case.parked or time.monotonic() > end:
            run.transcript.append({"role": "app", "text": "[claims prep never ran: scenario message not sent]"})
            return
        time.sleep(0.02)
    text = persona.during_prep["message"]
    run.transcript.append({"role": "veteran", "text": text})
    run.rt.message(run.case_id, text)
    _acted(run)
