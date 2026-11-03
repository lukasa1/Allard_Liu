"""Load the question bank and evaluate each question's `show_if` rule against the record."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import yaml

from .schema import IntakeRecord

FieldType = str  # see data/questions.yaml for the list
STAGES = ("screen", "post_poa", "reopen")
SOURCES = ("chat", "va_records", "secure_form")  # a `cfile: true` question may also come from the C-file


@dataclass(frozen=True)
class Question:
    id: str
    field: str
    type: FieldType
    ask: str
    section: str = ""
    stage: str = "post_poa"
    source: str = "chat"
    show_if: str | None = None
    options: tuple[str, ...] = ()
    probe: bool = False
    confirms: str | None = None  # probes: the field this question double-checks
    ask_with_records: str | None = None  # probes: wording when VA's records were fetched
    cfile: bool = False  # claims prep can settle it from the C-file (before pass 2)
    form_q: Any = None  # question number(s) on the firm's intake form


@dataclass(frozen=True)
class NarrativePrompt:
    id: str
    ask: str
    auto: bool = False


@dataclass(frozen=True)
class Ask:
    """One concrete thing to ask: a structured question, or a narrative prompt for one condition.

    `records_text` is set when the question is worded around VA's records ("VA's records list
    this service: ..."); the controller fills it in, the simulator reads it.
    """

    question: Question | None = None
    prompt: NarrativePrompt | None = None
    condition: str | None = None
    records_text: str | None = None

    @property
    def key(self) -> str:
        if self.question is not None:
            return self.question.id
        assert self.prompt is not None and self.condition is not None
        return f"narrative:{self.condition}:{self.prompt.id}"

    @property
    def type(self) -> FieldType:
        return self.question.type if self.question is not None else "narrative"

    @property
    def text(self) -> str:
        if self.question is not None:
            if self.records_text is not None and self.question.ask_with_records:
                return self.question.ask_with_records.format(va_service=self.records_text)
            return self.question.ask
        assert self.prompt is not None
        return self.prompt.ask.format(condition=self.condition)


@dataclass
class QuestionBank:
    structured: list[Question]
    narrative: list[NarrativePrompt]
    by_id: dict[str, Question] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {q.id: q for q in self.structured}
        if len(self.by_id) != len(self.structured):
            raise ValueError("duplicate question id in question bank")
        for q in self.structured:
            if q.show_if:
                parse_show_if(q.show_if)  # fail fast on a malformed rule
            if q.stage not in STAGES:
                raise ValueError(f"{q.id}: unknown stage {q.stage!r}")
            if q.source not in SOURCES:
                raise ValueError(f"{q.id}: unknown source {q.source!r}")

    @classmethod
    def load(cls) -> QuestionBank:
        text = resources.files("agent.intake").joinpath("data/questions.yaml").read_text()
        data = yaml.safe_load(text)
        structured = [
            Question(
                id=q["id"],
                field=q["field"],
                type=q["type"],
                ask=q["ask"],
                section=q.get("section", ""),
                stage=q.get("stage", "post_poa"),
                source=q.get("source", "chat"),
                show_if=q.get("show_if"),
                options=tuple(q.get("options", ())),
                probe=bool(q.get("probe", False)),
                confirms=q.get("confirms"),
                ask_with_records=q.get("ask_with_records"),
                cfile=bool(q.get("cfile", False)),
                form_q=q.get("form_q"),
            )
            for q in data["structured"]
        ]
        narrative = [
            NarrativePrompt(id=p["id"], ask=p["ask"], auto=bool(p.get("auto", False)))
            for p in data["narrative"]
        ]
        return cls(structured=structured, narrative=narrative)


_CLAUSE = re.compile(r"^\s*(\w+)\s+(==|!=|contains)\s+(.+?)\s*$")
_UNARY = re.compile(r"^\s*(\w+)\s+(truthy|falsy)\s*$")


def parse_show_if(rule: str) -> list[tuple[str, str, Any]]:
    clauses = []
    for part in rule.split(" and "):
        if m := _UNARY.match(part):
            clauses.append((m.group(1), m.group(2), None))
        elif m := _CLAUSE.match(part):
            raw = m.group(3)
            value: Any = {"true": True, "false": False, "null": None}.get(raw, raw)
            clauses.append((m.group(1), m.group(2), value))
        else:
            raise ValueError(f"bad show_if clause: {part!r}")
    return clauses


def is_visible(question: Question, record: IntakeRecord) -> bool:
    if not question.show_if:
        return True
    for field_name, op, value in parse_show_if(question.show_if):
        actual = getattr(record, field_name)
        if op == "truthy" and not actual:
            return False
        if op == "falsy" and actual:
            return False
        if op == "==" and actual != value:
            return False
        if op == "!=" and actual == value:
            return False
        if op == "contains" and (
            not isinstance(actual, str) or str(value).lower() not in actual.lower()
        ):
            return False
    return True
