"""The intake subagent's "brain": reads replies into typed answers and phrases questions.

The controller (controller.py) never changes; the brain is swappable:
- DSPyBrain (dspy_brain.py): a DSPy program on any LiteLLM model (default OpenRouter gpt-6-luna).
- OfflineBrain (here): rule-based. Reads only plain, direct answers and asks questions verbatim.
  It exists so the whole system runs, tests and demos with no API key. It is not a measure of
  quality.

The instruction texts below are the DSPy signatures' instructions (kept here so they are easy to
review in one place).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

# The deterministic backstops that run whatever the brain says live in agent/ingest.py (the single
# home of the input guards); re-exported here so existing imports keep working.
from agent.ingest import _CRISIS, _WANTS_HUMAN, _WHO, detect_crisis

from .parsing import _UNSURE, parse_text
from .questions import Ask

_QUESTION_START = re.compile(
    r"^\s*(how|what|when|why|who|where|which|can|could|do|does|will|would|is|are|should)\b",
    re.IGNORECASE,
)


def split_question(text: str) -> tuple[str, str]:
    """Split a reply into (answer part, question the veteran asked). Either may be empty."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    asked = [s for s in sentences if s.endswith("?") and _QUESTION_START.match(s)]
    rest = [s for s in sentences if s not in asked]
    return " ".join(rest).strip(), " ".join(asked).strip()


@dataclass
class Extraction:
    values: dict[str, Any] = field(default_factory=dict)  # ask key -> value (python object)
    pending_status: str = "answered"  # answered | unclear | declined | not_addressed
    clarify_hint: str = ""
    escalate: bool = False
    escalate_reason: str = ""
    wants_human: bool = False
    veteran_question: str = ""


class Brain(Protocol):
    def extract(
        self,
        *,
        pending: Ask,
        open_asks: list[Ask],
        transcript: list[dict[str, str]],
        user_text: str,
    ) -> Extraction: ...

    def phrase(
        self, *, ask: Ask, kind: str, transcript: list[dict[str, str]], note: str = ""
    ) -> str: ...

    def summarize(self, *, condition: str, qa: list[tuple[str, str]]) -> str: ...


# --------------------------------------------------------------------------------------------
# Offline (rule-based)
# --------------------------------------------------------------------------------------------


# Shown when the offline brain can't read an answer, so a person testing the demo knows what works.
_EXAMPLES = {
    "bool": '"Yes" or "No"',
    "int": 'a number like "30"',
    "service_periods": '"Army, active duty, from 2004-06 to 2010-05, honorable discharge" (separate periods with ";")',
    "service_periods_append": '"No", or "Navy, reserve, from 2014 to 2016, honorable"',
    "conditions_rated": '"tinnitus 10%, lumbar strain 20%", or "None"',
    "list_str": '"88M Motor Transport Operator", or "None"',
    "conditions": '"tinnitus, lower back pain", or "None"',
}


class OfflineBrain:
    def extract(
        self,
        *,
        pending: Ask,
        open_asks: list[Ask],
        transcript: list[dict[str, str]],
        user_text: str,
    ) -> Extraction:
        ext = Extraction()
        if _WANTS_HUMAN.search(user_text):
            ext.wants_human = True
            return ext
        answer, asked = split_question(user_text)
        ext.veteran_question = asked
        options = pending.question.options if pending.question else ()
        value = parse_text(pending.type, answer, options) if answer else None
        if value is None:
            if answer and _UNSURE.search(answer):
                ext.pending_status = "declined"  # "I don't know" is an answer: move on
            else:
                ext.pending_status = "not_addressed" if asked else "unclear"
        else:
            ext.values[pending.key] = value
        return ext

    def phrase(
        self, *, ask: Ask, kind: str, transcript: list[dict[str, str]], note: str = ""
    ) -> str:
        prefix = f"{note} " if note else ""
        if kind == "clarify":
            example = _EXAMPLES.get(ask.type, "")
            if ask.type == "enum" and ask.question is not None:
                example = "one of: " + ", ".join(ask.question.options)
            hint = f" (Offline mode reads plain answers, e.g. {example}.)" if example else ""
            return f"{prefix}Sorry, I didn't quite catch that. {ask.text}{hint}"
        return f"{prefix}{ask.text}"

    def summarize(self, *, condition: str, qa: list[tuple[str, str]]) -> str:
        lines = [f"Condition: {condition}."]
        lines += [f"{q} {a}" for q, a in qa]
        return " ".join(lines)


# --------------------------------------------------------------------------------------------
# Instructions for the LLM brain (DSPy signatures)
# --------------------------------------------------------------------------------------------

EXTRACT_SYSTEM = """You read one reply from a veteran during an intake conversation for a law firm that \
represents veterans in VA disability claims, and you turn it into structured answers.

You get the question the veteran was just asked (`pending_question`), other questions that are still \
open, the last few turns, and the reply. Rules:
- Record an answer only when the reply actually states it. Never guess or fill in typical values.
- Veterans often answer several questions at once or volunteer facts early. Record every open question \
the reply answers, not only the pending one.
- `value_json` is a JSON-encoded value of the question's type:
  bool -> true/false; int -> a number; str -> a JSON string; enum -> one of the listed options as a string;
  list_str / conditions -> a JSON array of strings (use [] if they say none);
  service_periods / service_periods_append -> a JSON array of objects with keys branch (army, navy, \
air force, marine corps, coast guard, space force), component (active, reserve, guard), start and end \
("YYYY-MM"; if only a year is given use "YYYY-01" for start and "YYYY-12" for end), discharge \
(honorable, general, oth, bad_conduct, dishonorable, uncharacterized; null if not stated). For \
service_periods_append, list ONLY periods that are not already listed in the question;
  conditions_rated -> a JSON array of {"name": ..., "rating_pct": ...};
  narrative -> a JSON string that keeps the veteran's own words and facts.
- For conditions, use the plain medical name the VA would use ("ringing in my ears" -> "tinnitus", \
"bad back" -> "lumbar strain"), but keep laterality (left/right) when the veteran gives it.
- `pending_status`: answered (the pending question is answered), unclear (they tried but the answer is \
vague, contradictory or doesn't fit the type), declined (they don't know or won't say), or not_addressed.
- When unclear, put a short note in `clarify_hint` about what to ask (e.g. "needs the end year").
- `escalate`: true if the veteran shows signs of crisis or risk of self-harm, or the reply suggests \
danger to anyone. Give a short `escalate_reason`.
- `wants_human`: true if they ask to speak with a real person.
- `veteran_question`: if they ask the firm a question (about VA, the process, fees, timing), copy it \
here; otherwise "". Do not answer it yourself; a separate tool answers it."""

PHRASE_SYSTEM = """You are the intake assistant for a law firm that helps veterans with VA disability \
claims. You are texting with a veteran. Write your next message.

- Ask exactly one thing: the question described in `intent`. Keep its meaning; say it plainly and warmly.
- If `intent` quotes VA's records, keep those facts exactly as written.
- If the veteran just shared something, acknowledge it in a few words first. Don't repeat their answer back in full.
- If `kind` is "clarify", gently ask again using the hint in `note`; don't make them feel wrong.
- Otherwise, if `note` is set, include it first, keeping its facts and any source link exactly (it may \
be the answer to a question the veteran asked).
- Keep it short: one to three sentences plus the note. No lists, no form numbers, no legal jargon.
- Never give legal advice, predict outcomes, or promise a rating or a result.
- No em dashes.
- Output only the message text."""

SUMMARY_SYSTEM = """Write a "VA narrative summary" for one condition from a veteran's intake answers, for \
the firm's attorneys. Use only facts the veteran stated; do not add, infer or embellish. Write in the \
third person, in plain prose of one or two short paragraphs, covering, where the veteran gave them: \
current symptoms and severity; onset and continuity since service; the in-service event, location and \
conditions; whether it was reported or treated in service; and the effect on work and daily life. If an \
element is missing, say so in one short closing sentence (e.g. "They did not say whether it was reported \
in service.")."""


def recent(transcript: list[dict[str, str]], n: int = 6) -> list[dict[str, str]]:
    return [{"speaker": t["role"], "text": t["text"]} for t in transcript[-n:]]


def describe(ask: Ask) -> dict[str, Any]:
    d: dict[str, Any] = {"question_id": ask.key, "question": ask.text, "type": ask.type}
    if ask.question is not None and ask.question.options:
        d["options"] = list(ask.question.options)
    if ask.condition:
        d["condition"] = ask.condition
    return d
