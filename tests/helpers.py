"""Helpers the runtime tests share: waiting on a background turn, reading the outbox and the event
log, opening a case, and a few case-file constants."""

import io
import re
import time

import pypdf

from agent.casefile import Filing, PrepState
from agent.scripted.lm import call, final

FILED = {"21-22a": Filing(confirmation="A"), "itf": Filing(confirmation="B")}
PREP_DONE = PrepState(face_note="n", verified=True, prefill_done=True)


def until(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while not pred():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def messages(rt, cid):
    return [(o.agent, o.payload["text"]) for o in rt.updates(cid) if o.kind == "message"]


def events(rt, cid, *types):
    return [e for e in rt.store.events(cid) if e.type in types]


def refusals(rt, cid):
    return [e.data["reason"] for e in events(rt, cid, "refused")]


def incoming(prompt: str) -> str:
    return prompt.split("[[ ## incoming ## ]]")[1]


def outside(text: str) -> str:
    """The text with every untrusted block cut out."""
    return re.sub(r"<untrusted.*?</untrusted>", "", text, flags=re.DOTALL)


def opened(rt, lm, persona: str | None = None, first=()) -> str:
    """A new case the orchestrator handed to intake, after intake's first turn (`first`: its steps)."""
    lm.turn("orchestrator", call("run_intake", goal="Pass 1: screen, sign, file."), final(reply="Welcome!"))
    lm.turn("intake", *first, final(reply="Did you serve in the military?"))
    cid = rt.open_case(persona).case_id
    rt.wait_until_idle()
    return cid


def say(rt, cid, text):
    rt.message(cid, text)
    rt.wait_until_idle()


def pdf_text(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
