"""kb_search (L31): the knowledge base as a registry tool, shared by intake and support.

The engine is the web-search QA of agent/qa.py (official domains only, answers cite their
sources, model Haiku 5.5). The runtime holds the engine (`rt.kb`), so tests inject an offline
stand-in and never touch the network. Each search is logged as a `kb_search` event, which is how
support later sees the questions already answered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from agent.ingest import redact_chat
from agent.tools.registry import ToolSpec

if TYPE_CHECKING:
    from agent.harness import Turn

NO_ANSWER = ("The knowledge base has no answer for this (or it asks for legal advice or a prediction "
             "about this case). Don't answer it yourself: tell the veteran a person on the team will "
             "follow up.")  # fmt: skip


class KbArgs(BaseModel):
    question: str = Field(min_length=3, description="the veteran's question, in plain words")


def kb_search(turn: Turn, args: KbArgs) -> dict:
    question, _ = redact_chat(args.question)
    result = turn.rt.kb(question)
    answered = bool(result.text) and not result.handoff
    turn.rt.store.append_event(turn.case_id, "kb_search", {"question": question, "answered": answered,
                               "sources": result.sources}, actor=turn.agent)  # fmt: skip
    if not answered:
        return {"answer": None, "note": NO_ANSWER}
    return {"answer": result.text, "sources": result.sources}


def kb_tool(turn: Turn) -> ToolSpec:
    return ToolSpec(
        "kb_search", "Search the knowledge base (official VA and federal sources) to answer a general "
        "question about VA process, forms or fees. Returns an answer with its sources, or no answer.",
        KbArgs, lambda a: kb_search(turn, a),
    )  # fmt: skip
