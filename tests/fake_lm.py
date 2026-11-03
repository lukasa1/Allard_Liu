"""A rule-driven stand-in for an LLM, so the whole DSPy path can run in tests with no network.

It reads which DSPy signature is being called (from the output-field list in the system prompt),
parses the inputs from the last user message, and answers the way a careful model would, using
the offline rules. This checks the DSPy *wiring* end to end (adapters, field types, ReAct tool
calls, history); how well a real model does is what the live eval measures.
"""

from __future__ import annotations

import json
import re
from typing import Any

from dspy.clients.engines.dummy_engine import AsyncDummyEngine, DummyEngine
from dspy.utils.dummies import DummyLM

from agent.intake.brains import split_question
from agent.intake.parsing import parse_bool, parse_text
from poa_skill.form_21_22a import REQUIRED_VETERAN_FIELDS

_FIELD = re.compile(
    r"\[\[ ## (\w+) ## \]\]\n(.*?)(?=\n\n\[\[ ## \w+ ## \]\]|\n\nRespond with|\Z)", re.DOTALL
)
LABEL_TO_FIELD = {label: key for key, label in REQUIRED_VETERAN_FIELDS.items()}


def _inputs(content: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in _FIELD.finditer(content)}


def _jsonable(v: Any) -> Any:
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


class _Engine(DummyEngine):
    def _complete_messages(self, messages):
        owner: RuleLM = self.owner
        answer = owner.respond(messages[0]["content"], messages[-1]["content"])
        owner.calls.append(answer)
        return self._fmt(answer)

    def _fmt(self, answer: dict):
        from dspy.lm15 import Message, Response, TextPart, Usage

        text = self.owner._format_answer_fields(answer)
        return Response(id=None, model="rule", message=Message.assistant([TextPart(text)]), finish_reason="stop",
                        usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0))  # fmt: skip


class RuleLM(DummyLM):
    def __init__(self) -> None:
        super().__init__([])
        self._engine_spec = _Engine(self)
        self._async_engine_spec = AsyncDummyEngine(self._engine_spec)
        self.calls: list[dict] = []
        self.signatures: list[str] = []
        # POA agent memory (a real model keeps this in the conversation history)
        self.asked: str | None = None
        self.consents: dict[str, bool | None] = {
            "authorize_7332_records": None,
            "authorize_address_change": None,
        }
        self.reviewed = False
        self.reply = ""

    # ------------------------------------------------------------------ dispatch

    def respond(self, system: str, user: str) -> dict[str, Any]:
        out_block = system.split("Your output fields are:")[1].split("All interactions")[0]
        outputs = re.findall(r"`(\w+)`", out_block)
        x = _inputs(user)
        if "next_tool_name" in outputs and "allowed_actions" in x:
            # The orchestrator's ReAct loop: read the stage playbook once per decision, then finish.
            self.signatures.append("orchestrator_react")
            if "read_skill" not in re.findall(r"\[\[ ## tool_name_\d+ ## \]\]\n(\w+)", user):
                return {"next_thought": "check the playbook", "next_tool_name": "read_skill",
                        "next_tool_args": {"name": "stage-playbook"}}  # fmt: skip
            return {"next_thought": "decide", "next_tool_name": "finish", "next_tool_args": {}}
        if "next_tool_name" in outputs:
            self.signatures.append("react")
            return self._react(x, user)
        if outputs[:1] == ["reasoning"] and "reply" in outputs:
            self.signatures.append("react_extract")
            return {"reasoning": "done", "reply": self.reply}
        if "pending_status" in outputs:
            self.signatures.append("extract")
            return self._extract(x)
        if outputs == ["message"]:
            self.signatures.append("phrase")
            note = x.get("note", "")
            return {
                "message": f"{note} {x['intent']}".strip()
                if x.get("kind") == "question"
                else f"Sorry, could you say that again? {x['intent']}"
            }
        if outputs == ["summary"]:
            self.signatures.append("summarize")
            return {"summary": f"Summary for {x.get('condition')}."}
        if outputs in (["action", "reason"], ["reasoning", "action", "reason"]):
            self.signatures.append("orchestrator")
            allowed = [a["name"] for a in json.loads(x["allowed_actions"])]
            case = json.loads(x["case"])
            blocked = [
                a for a in case.get("attention", []) if a.startswith(("escalated", "intake ended"))
            ]
            extra = {"reasoning": "per the playbook"} if outputs[0] == "reasoning" else {}
            if "hand_off_to_staff" in allowed and blocked:
                return {**extra, "action": "hand_off_to_staff", "reason": "a person must take over"}
            pick = next((a for a in allowed if a not in ("hand_off_to_staff", "wait")), "wait")
            return {**extra, "action": pick, "reason": "next step"}
        if outputs == ["facts"]:
            self.signatures.append("cfile")
            return {"facts": {"doc_type": x.get("doc_type_hint", "other")}}
        raise AssertionError(f"unexpected signature with outputs {outputs}")

    # ------------------------------------------------------------------ intake brain

    def _extract(self, x: dict[str, str]) -> dict[str, Any]:
        pending = json.loads(x["pending_question"])
        reply = x["veteran_reply"]
        answer, asked = split_question(reply)
        value = (
            parse_text(pending["type"], answer, tuple(pending.get("options", ())))
            if answer
            else None
        )
        answers = (
            []
            if value is None
            else [
                {"question_id": pending["question_id"], "value_json": json.dumps(_jsonable(value))}
            ]
        )
        status = "answered" if answers else ("not_addressed" if asked else "unclear")
        return {"answers": answers, "pending_status": status, "clarify_hint": "", "escalate": False,
                "escalate_reason": "", "wants_human": False, "veteran_question": asked}  # fmt: skip

    # ------------------------------------------------------------------ POA ReAct agent

    def _react(self, x: dict[str, str], user: str) -> dict[str, Any]:
        incoming = x.get("incoming", "")
        tools = re.findall(r"\[\[ ## tool_name_\d+ ## \]\]\n(\w+)", user)
        observations = re.findall(
            r"\[\[ ## observation_\d+ ## \]\]\n(.*?)(?=\n\n\[\[ ## |\Z)", user, re.DOTALL
        )
        if not tools:
            if not incoming.startswith("[app event]"):
                if self.asked in ("item20", "item22"):
                    key = (
                        "authorize_7332_records"
                        if self.asked == "item20"
                        else "authorize_address_change"
                    )
                    self.consents[key] = parse_bool(incoming)
                elif self.asked == "review" and re.search(
                    r"looks good|correct|yes", incoming, re.IGNORECASE
                ):
                    self.reviewed = True
            return self._call("get_intake_status", {})
        obs: dict = {}
        if observations and observations[-1].lstrip().startswith("{"):
            obs, _ = json.JSONDecoder().raw_decode(observations[-1].lstrip())
        last = tools[-1]
        if last == "get_intake_status":
            if any(d["status"] == "signed" for d in obs["documents"]):
                return self._finish("Signed. The firm files the form with VA next.")
            if obs["pending_secure_forms"]:
                return self._finish("Please fill in the secure form.")
            missing = [LABEL_TO_FIELD[m] for m in obs["missing_for_21_22a"] if m in LABEL_TO_FIELD]
            if missing:
                return self._call(
                    "request_secure_info",
                    {"fields": missing + ["phone", "email"], "purpose": "For the form."},
                )
            for key, ask, q in (("authorize_7332_records", "item20", "Can our attorney see drug or alcohol, HIV or sickle cell records?"),
                                ("authorize_address_change", "item22", "Can our attorney update your address with VA?")):  # fmt: skip
                if self.consents[key] is None:
                    self.asked = ask
                    return self._finish(q)
            drafts = [d for d in obs["documents"] if d["status"] == "draft"]
            if not drafts:
                return self._call("prepare_poa_21_22a", dict(self.consents))
            if not self.reviewed:
                self.asked = "review"
                return self._finish("Does the form look right?")
            if not obs["signature_on_file"]:
                return self._call("request_signature_capture", {})
            return self._call("present_for_signature", {"document_id": drafts[0]["document_id"]})
        if last == "prepare_poa_21_22a":
            self.asked = "review"
            return self._finish("Here's your form. Does it look right?")
        return self._finish({"request_secure_info": "I've opened a secure form.", "request_signature_capture": "Please draw your signature.",
                             "present_for_signature": "Click Sign when you're ready."}.get(last, "Okay."))  # fmt: skip

    def _call(self, name: str, args: dict) -> dict[str, Any]:
        return {"next_thought": f"call {name}", "next_tool_name": name, "next_tool_args": args}

    def _finish(self, reply: str) -> dict[str, Any]:
        self.reply = reply
        return {
            "next_thought": "wait for the veteran",
            "next_tool_name": "finish",
            "next_tool_args": {},
        }
