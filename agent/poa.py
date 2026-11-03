"""The intake subagent's POA step: mounts poa_skill (VA Form 21-22a) the way its README says.

The skill is instructions (SKILL.md) + six tools + a service; the model never sees raw PII and
has no signing tool. Two drivers, same contract:

  DSPyPoaStep     a DSPy ReAct agent: SKILL.md is its instructions, the skill's tools are its
                  tools (routed through skill.run_tool), one ReAct episode per veteran message or
                  app event. This is "an agent mounting a skill".
  OfflinePoaStep  a scripted policy that calls the same tools in the order SKILL.md describes,
                  so the demo and tests run with no API key.

Both return PoaTurn(text, cards). Cards are UI for the host (secure form, signature pad, PDF
preview, Sign button); the host posts the user's actions straight to PoaService, never through
the model, then tells the step with `event(...)`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agent.intake.parsing import _LEAD_NO, _LEAD_OK, _LEAD_YES, _UNSURE
from poa_skill import PoaService, load_skill
from poa_skill.form_21_22a import REQUIRED_VETERAN_FIELDS

LABEL_TO_FIELD = {label: key for key, label in REQUIRED_VETERAN_FIELDS.items()}
OPTIONAL_FIELDS = ["middle_initial", "va_file_number", "phone", "email"]
ITEM20_Q = (
    "One choice on the form is yours to make. Can our attorney see any VA records about treatment "
    "for drug or alcohol use, HIV, or sickle cell anemia, if your file has any? Without this, VA "
    "keeps those records from them. Yes or no is fine."
)
ITEM22_Q = "And can our attorney update your mailing address with VA for you if you move?"
EVENTS = ("secure_form_submitted", "signature_saved", "draft_edited", "signed")
HISTORY_TURNS = 12  # DSPy step: earlier turns kept verbatim in the prompt
_LOOKS_GOOD = re.compile(
    r"\b(looks? (good|right|fine|correct)|all good|correct|that'?s right|yes|yep|ok(ay)?)\b",
    re.IGNORECASE,
)


_APPROVE = re.compile(  # approvals that contain a "no"/"not"
    r"\b(no changes?( needed)?|nothing (to change|to fix|wrong)|not a thing wrong|all (good|correct|right))\b",
    re.IGNORECASE,
)
_NOT_OK = re.compile(r"\b(no|not|wrong|incorrect|isn'?t|change|fix|mistake|typo)\b", re.IGNORECASE)


@dataclass
class PoaTurn:
    text: str
    cards: list[dict] = field(default_factory=list)
    failed: bool = False  # the model call failed; any cards from tools that already ran are kept


def is_signed(svc: PoaService) -> bool:
    return any(d["status"] == "signed" for d in svc.status()["documents"])


def signed_document_id(svc: PoaService) -> str | None:
    return next(
        (d["document_id"] for d in svc.status()["documents"] if d["status"] == "signed"), None
    )


def _live_draft(svc: PoaService) -> dict | None:
    return next((d for d in svc.status()["documents"] if d["status"] == "draft"), None)


# ------------------------------------------------------------------------------- offline


class OfflinePoaStep:
    """Scripted: calls the skill's tools in SKILL.md's order, decided from get_intake_status."""

    def __init__(self, svc: PoaService) -> None:
        self.svc = svc
        self.skill = load_skill()
        self.consents: dict[str, bool | None] = {
            "authorize_7332_records": None,
            "authorize_address_change": None,
        }
        self.waiting_for: str | None = (
            None  # secure_form | item20 | item22 | review | signature | sign | done
        )
        self.reviewed = False

    def _tool(self, name: str, args: dict | None = None):
        return self.skill.run_tool(self.svc, name, args or {})

    # Memory: the vault, drafts and signature live in PoaService on disk; this is the step's position.
    def to_state(self) -> dict[str, Any]:
        return {"kind": "offline", "consents": dict(self.consents), "waiting_for": self.waiting_for,
                "reviewed": self.reviewed}  # fmt: skip

    def load_state(self, state: dict[str, Any]) -> None:
        if state.get("kind") != "offline":
            raise ValueError("saved POA step was not the offline one")
        self.consents = dict(state["consents"])
        self.waiting_for = state["waiting_for"]
        self.reviewed = state["reviewed"]

    def start(self) -> PoaTurn:
        intro = (
            "Next is the form that lets our attorney represent you with VA and see your VA file. "
            "I'll fill it in; you just check it and sign."
        )
        turn = self._advance()
        return PoaTurn(f"{intro} {turn.text}".strip(), turn.cards)

    def message(self, text: str) -> PoaTurn:
        if self.waiting_for in ("item20", "item22"):
            # A release of sensitive records needs a clear yes or no, not "I'm worried about that".
            if _UNSURE.search(text):
                answer = None
            elif _LEAD_YES.match(text) or _LEAD_OK.match(text):
                answer = True
            elif _LEAD_NO.match(text):
                answer = False
            else:
                answer = None
            if answer is None:
                return PoaTurn(
                    "Sorry, I didn't catch that. "
                    + (ITEM20_Q if self.waiting_for == "item20" else ITEM22_Q)
                )
            key = (
                "authorize_7332_records"
                if self.waiting_for == "item20"
                else "authorize_address_change"
            )
            self.consents[key] = answer
            return self._advance()
        if self.waiting_for == "review":
            if _APPROVE.search(text) or (_LOOKS_GOOD.search(text) and not _NOT_OK.search(text)):
                self.reviewed = True
                return self._advance()
            return PoaTurn(
                'You can change your name, address, branch, phone or email with "Edit before signing" '
                "above the preview. When it looks right, just tell me."
            )
        if self.waiting_for == "secure_form":
            return PoaTurn(
                "Whenever you're ready, fill in the secure form above. Your details go straight into encrypted storage."
            )
        if self.waiting_for == "signature":
            return PoaTurn("Please draw your signature in the box above and click Save.")
        if self.waiting_for == "sign":
            return PoaTurn(
                "When you're ready, click Sign on the form above. Only your click signs it."
            )
        return self._advance()

    def event(self, kind: str) -> PoaTurn:
        if kind == "draft_edited":
            # An edit always needs a fresh look before signing.
            self.reviewed = False
            if self.waiting_for in ("review", "signature", "sign"):
                self.waiting_for = "review"
                return PoaTurn("Thanks, I've updated the preview. Does everything look right now?")
            return self._advance()
        if kind == "secure_form_submitted" and self.waiting_for == "secure_form":
            self.waiting_for = None
        if kind == "signature_saved" and self.waiting_for == "signature":
            self.waiting_for = None
        return self._advance()

    def _advance(self) -> PoaTurn:
        status = self._tool("get_intake_status").result
        if is_signed(self.svc):
            self.waiting_for = "done"
            return PoaTurn(
                "Signed. Thank you. The firm adds the attorney's signature and files the form with VA, "
                "and we'll let you know once VA records the appointment."
            )
        if status["pending_secure_forms"]:
            self.waiting_for = "secure_form"
            return PoaTurn("Please fill in the secure form above.")
        missing = [LABEL_TO_FIELD[m] for m in status["missing_for_21_22a"] if m in LABEL_TO_FIELD]
        if missing:
            captured = set(status["captured"])
            fields = missing + [f for f in OPTIONAL_FIELDS if f not in captured]
            out = self._tool("request_secure_info", {
                "fields": fields,
                "purpose": "These go on the form that lets our attorney represent you with VA.",
            })  # fmt: skip
            self.waiting_for = "secure_form"
            return PoaTurn(
                "I've opened a secure form for your details. Please don't type your Social Security "
                "number in the chat; the form keeps it encrypted, and I only ever see the last four digits.",
                out.cards,
            )
        if self.consents["authorize_7332_records"] is None:
            self.waiting_for = "item20"
            return PoaTurn(ITEM20_Q)
        if self.consents["authorize_address_change"] is None:
            self.waiting_for = "item22"
            return PoaTurn(ITEM22_Q)
        draft = _live_draft(self.svc)
        if draft is None:
            out = self._tool("prepare_poa_21_22a", dict(self.consents))
            self.waiting_for = "review"
            return PoaTurn(
                "Here's your form. Please check your name, address and branch. Tell me if it looks "
                'right, or fix anything with "Edit before signing".',
                out.cards,
            )
        if not self.reviewed:
            self.waiting_for = "review"
            return PoaTurn("Does the form look right?")
        if not status["signature_on_file"]:
            out = self._tool("request_signature_capture")
            self.waiting_for = "signature"
            return PoaTurn(
                "Great. Please draw your signature once; it's saved and placed only when you click Sign.",
                out.cards,
            )
        out = self._tool("present_for_signature", {"document_id": draft["document_id"]})
        if not out.result.get("ready"):
            self.waiting_for = "review"
            return PoaTurn(
                f"Something still needs fixing before you can sign: {out.result.get('reason')}."
            )
        self.waiting_for = "sign"
        return PoaTurn(
            "Everything's ready. Click Sign when you're ready; only your click signs it.", out.cards
        )


# ------------------------------------------------------------------------------- DSPy ReAct

HOST_INSTRUCTIONS = """You are the intake assistant for a law firm that represents veterans before VA. \
You are in the step where the veteran signs VA Form 21-22a. Follow the skill below exactly. Messages \
starting with [app event] come from the app (the veteran submitted a secure form, saved a signature, \
edited the draft, or clicked Sign), not from the veteran. After each tool that shows something to the \
veteran (secure form, preview, signature pad, Sign button), finish and wait for them. Be warm and brief: \
one question per message.

## Skill: {name}
{description}

{instructions}"""


def make_dspy_poa_step(svc: PoaService, lm):
    import dspy

    skill = load_skill()

    # Built from a dict, not a class body: this module uses postponed annotations, and DSPy needs
    # real types on the fields. The conversation is plain text, not dspy.History: ReAct formats a
    # History against each inner step's own output fields (next_thought, next_tool_name, ...), so
    # the step choosing a tool would see every earlier reply as None.
    PoaAgentTurn = dspy.Signature(
        {
            "conversation": (
                str,
                dspy.InputField(desc="earlier turns of this step, oldest first (empty at the start)"),
            ),
            "incoming": (str, dspy.InputField(desc="the veteran's message, or an [app event]")),
            "reply": (str, dspy.OutputField(desc="your message to the veteran")),
        },
        HOST_INSTRUCTIONS.format(
            name=skill.name, description=skill.description, instructions=skill.instructions
        ),
    )

    class DSPyPoaStep:
        def __init__(self) -> None:
            self.svc = svc
            self.history: list[dict[str, str]] = []
            self._cards: list[dict] = []
            self.waiting_for: str | None = None

        def _tool(self, name: str):
            def run(**kwargs: Any) -> str:
                out = skill.run_tool(self.svc, name, kwargs)
                self._cards.extend(out.cards)
                return json.dumps(out.result)

            spec = next(t for t in skill.tools if t["name"] == name)
            return dspy.Tool(
                run,
                name=name,
                desc=spec["description"],
                args=spec["input_schema"].get("properties", {}),
            )

        def _turn(self, incoming: str) -> PoaTurn:
            self._cards = []
            react = dspy.ReAct(
                PoaAgentTurn, tools=[self._tool(t["name"]) for t in skill.tools], max_iters=6
            )
            # A fixed window (the context manager): the skill's state lives in PoaService and
            # get_intake_status, so older turns add tokens, not facts.
            conversation = "\n".join(
                f"Incoming: {h['incoming']}\nYou replied: {h['reply']}" for h in self.history[-HISTORY_TURNS:]
            )
            try:
                with dspy.context(lm=lm):
                    pred = react(conversation=conversation, incoming=incoming)
            except Exception:
                # Tools may already have run (a secure form opened, a draft prepared): keep their
                # cards so the veteran sees them, and tell the next turn what happened.
                done = ", ".join(c.get("type", "card") for c in self._cards) or "nothing"
                self.history.append({
                    "incoming": incoming,
                    "reply": f"(no reply: the model call failed; cards already shown: {done})",
                })  # fmt: skip
                self.waiting_for = "done" if is_signed(self.svc) else None
                return PoaTurn("", list(self._cards), failed=True)
            reply = (pred.reply or "").strip()
            self.history.append({"incoming": incoming, "reply": reply})
            self.waiting_for = "done" if is_signed(self.svc) else None
            return PoaTurn(reply, list(self._cards))

        def to_state(self) -> dict[str, Any]:
            return {"kind": "dspy", "history": list(self.history), "waiting_for": self.waiting_for}

        def load_state(self, state: dict[str, Any]) -> None:
            if state.get("kind") != "dspy":
                raise ValueError("saved POA step was not the DSPy one")
            self.history = list(state["history"])
            self.waiting_for = state["waiting_for"]

        def start(self) -> PoaTurn:
            return self._turn(
                "[app event] The screening questions are done. Start the 21-22a step now."
            )

        def message(self, text: str) -> PoaTurn:
            return self._turn(text)

        def event(self, kind: str) -> PoaTurn:
            text = {
                "secure_form_submitted": "The user submitted the secure form.",
                "signature_saved": "The user drew and saved their signature.",
                "draft_edited": "The user edited the draft themselves in the edit panel.",
                "signed": "The user clicked Sign. The 21-22a is signed.",
            }.get(kind, kind)
            return self._turn(f"[app event] {text}")

    return DSPyPoaStep()
