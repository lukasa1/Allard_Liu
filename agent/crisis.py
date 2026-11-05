"""crisis_to_person and to_person: the model's backstops for what code's checks missed.

to_person (intake only; support has `escalate`): a request for a person or to end the representation
that code's wants_human / wants_withdraw checks missed, handed over by the rule's own code too.

Code checks every message for crisis language before any model sees it (agent/ingest.py). A
miss (a wording or a character the check doesn't know) reaches intake or support, which then call
this tool. It does what the rule does, by the same code: the Veterans Crisis Line text from code
(not the model's words), an urgent staff task, needs_human (a closed case stays closed), and the
orchestrator woken; the turn's
own reply is held back, so no further question reaches the veteran.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from agent.tools.registry import ToolSpec

if TYPE_CHECKING:
    from agent.harness import Turn


class PersonArgs(BaseModel):
    kind: Literal["wants_human", "withdraw"] = Field(description="wants_human: they ask for a person; "
                                                     "withdraw: they want to end the firm's representation")
    reason: str = Field(min_length=3, description="what the veteran said, in one line")


def to_person_tool(turn: Turn) -> ToolSpec:
    done: list[str] = []  # once per turn

    def run(args: PersonArgs) -> str:
        if not done:
            done.append(args.kind)
            turn.rt.to_person_from_agent(turn.case_id, turn.agent, args.kind, args.reason)
        return "handed to a person: code sent the veteran the hand-off message; finish now and say nothing more"

    return ToolSpec(
        "to_person", "The veteran asks to talk to a person, or wants to stop working with the firm (end the "
        "representation, cancel, revoke the forms), in any words: hand the case to a person now. Not for a "
        "question about how that works (\"can I revoke it later?\"): answer that from kb_search.",
        PersonArgs, run,
    )  # fmt: skip


class CrisisArgs(BaseModel):
    reason: str = Field(min_length=3, description="what the veteran said that shows it, in one line")


def crisis_tool(turn: Turn) -> ToolSpec:
    done: list[str] = []  # once per turn (a retried attempt repeats its tool calls)

    def run(args: CrisisArgs) -> str:
        if not done:
            done.append(args.reason)
            turn.rt.crisis_from_agent(turn.case_id, turn.agent, args.reason)
        return "handed to a person: the Veterans Crisis Line was sent by code; finish now and say nothing more"

    return ToolSpec(
        "crisis_to_person", "The veteran shows thoughts of suicide or of hurting themselves (in any words, "
        "said about themselves): send the Veterans Crisis Line and hand the case to a person now. Use it "
        "at once, before anything else. When unsure, use it. Not for someone else's (a friend's suicide) "
        "or an injury story (\"I hurt myself lifting a crate\").",
        CrisisArgs, run,
    )  # fmt: skip
