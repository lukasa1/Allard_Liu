"""DSPy version of the intake brain.

The three LLM calls the intake subagent makes (extract, phrase, summarize) are DSPy signatures in
one `IntakeProgram` module. The controller still decides what to ask and when to stop; DSPy only
fills the brain's role. Keeping the program as a module means DSPy optimizers (MIPROv2, GEPA) can
tune its prompts against the simulated-veteran eval, and a tuned program can be saved and loaded
with DSPY_PROGRAM.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

import dspy
from dspy.utils.exceptions import AdapterParseError
from pydantic import BaseModel, model_validator

from .brains import EXTRACT_SYSTEM, PHRASE_SYSTEM, SUMMARY_SYSTEM, Extraction, describe, recent
from .questions import Ask

PENDING_STATUSES = ("answered", "unclear", "declined", "not_addressed")


class AnswerItem(BaseModel):
    # Lenient on purpose: one out-of-shape item must not lose the whole extraction. The
    # controller's `coerce` validates each value against its question's type.
    question_id: str = ""
    value_json: Any = None

    @model_validator(mode="before")
    @classmethod
    def _loose(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {}
        data = dict(data)
        if "value_json" not in data and "value" in data:
            data["value_json"] = data.pop("value")
        if data.get("question_id") is not None:
            data["question_id"] = str(data["question_id"])
        return data


class ExtractAnswers(dspy.Signature):
    pending_question: str = dspy.InputField(desc="JSON: the question the veteran was just asked")
    other_open_questions: str = dspy.InputField(
        desc="JSON list: other questions still open, which the reply may also answer"
    )
    recent_conversation: str = dspy.InputField(desc="JSON list of the last few turns")
    veteran_reply: str = dspy.InputField()
    # Every output has a default, so a missing field doesn't fail the whole parse (DSPy fills
    # defaults for missing outputs).
    answers: list[AnswerItem] = dspy.OutputField(
        default_factory=list,
        desc="one item per question the reply answers; value_json is a JSON-encoded value",
    )
    pending_status: str = dspy.OutputField(
        default="unclear", desc="one of: answered, unclear, declined, not_addressed"
    )
    clarify_hint: str = dspy.OutputField(
        default="", desc="what to ask again if unclear, else empty"
    )
    escalate: bool = dspy.OutputField(default=False)
    escalate_reason: str = dspy.OutputField(default="", desc="empty unless escalate")
    wants_human: bool = dspy.OutputField(default=False)
    veteran_question: str = dspy.OutputField(
        default="", desc="a question the veteran asked the firm, copied, else empty"
    )


class PhraseNextMessage(dspy.Signature):
    recent_conversation: str = dspy.InputField(desc="JSON list of the last few turns")
    kind: Literal["question", "clarify"] = dspy.InputField()
    intent: str = dspy.InputField(desc="the question to ask, in plain words")
    condition: str = dspy.InputField(desc="the condition this question is about, or empty")
    note: str = dspy.InputField(
        desc="something to include first, or the clarify hint; may be empty"
    )
    message: str = dspy.OutputField(desc="the next message to the veteran")


class SummarizeNarrative(dspy.Signature):
    condition: str = dspy.InputField()
    answers: str = dspy.InputField(desc="JSON list of {question, answer}")
    summary: str = dspy.OutputField()


ExtractAnswers = ExtractAnswers.with_instructions(EXTRACT_SYSTEM)
PhraseNextMessage = PhraseNextMessage.with_instructions(PHRASE_SYSTEM)
SummarizeNarrative = SummarizeNarrative.with_instructions(SUMMARY_SYSTEM)


class IntakeProgram(dspy.Module):
    """The brain as one DSPy program: the unit an optimizer tunes, saves and loads."""

    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.Predict(ExtractAnswers)
        self.phrase = dspy.Predict(PhraseNextMessage)
        self.summarize = dspy.Predict(SummarizeNarrative)


class DSPyBrain:
    def __init__(self, lm: dspy.BaseLM, program: IntakeProgram | None = None) -> None:
        self.lm = lm
        self.program = program or IntakeProgram()
        path = os.environ.get("DSPY_PROGRAM")
        if program is None and path:
            self.program.load(path)

    def extract(
        self,
        *,
        pending: Ask,
        open_asks: list[Ask],
        transcript: list[dict[str, str]],
        user_text: str,
    ) -> Extraction:
        try:
            with dspy.context(lm=self.lm):
                pred = self.program.extract(
                    pending_question=json.dumps(describe(pending), ensure_ascii=False),
                    other_open_questions=json.dumps(
                        [describe(a) for a in open_asks], ensure_ascii=False
                    ),
                    recent_conversation=json.dumps(recent(transcript), ensure_ascii=False),
                    veteran_reply=user_text,
                )
        except AdapterParseError:
            # Unparseable output (including a declined request) reads as "didn't catch that";
            # the controller re-asks, then marks the question unknown.
            return Extraction(pending_status="unclear")
        values: dict[str, Any] = {}
        for item in pred.answers or []:
            if not item.question_id or item.value_json is None:
                continue
            values[item.question_id] = _decode(item.value_json)
        status = str(pred.pending_status or "").strip().strip("`'\"").lower()
        return Extraction(
            values=values,
            pending_status=status if status in PENDING_STATUSES else "unclear",
            clarify_hint=pred.clarify_hint or "",
            escalate=bool(pred.escalate),
            escalate_reason=pred.escalate_reason or "",
            wants_human=bool(pred.wants_human),
            veteran_question=pred.veteran_question or "",
        )

    def phrase(
        self, *, ask: Ask, kind: str, transcript: list[dict[str, str]], note: str = ""
    ) -> str:
        try:
            with dspy.context(lm=self.lm):
                pred = self.program.phrase(
                    recent_conversation=json.dumps(recent(transcript), ensure_ascii=False),
                    kind="clarify" if kind == "clarify" else "question",
                    intent=ask.text,
                    condition=ask.condition or "",
                    note=note,
                )
            return pred.message.strip()
        except AdapterParseError:
            # Fall back to the question bank's own wording: always safe to send.
            if kind == "clarify":
                return f"Sorry, I didn't quite catch that. {ask.text}"
            return f"{note} {ask.text}".strip()

    def summarize(self, *, condition: str, qa: list[tuple[str, str]]) -> str:
        answers = json.dumps([{"question": q, "answer": a} for q, a in qa], ensure_ascii=False)
        try:
            with dspy.context(lm=self.lm):
                return self.program.summarize(condition=condition, answers=answers).summary.strip()
        except AdapterParseError:
            return "(summary not generated; see the answers)"


def _decode(value: Any) -> Any:
    """value_json as a python object: a JSON string is decoded, anything else (a raw bool, list,
    number, or unparseable text) is passed on as-is for `coerce` to validate."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
