"""A minimal intake subagent that runs the 21-22a skill with Claude tool use.

The host app (demo/server.py) owns one IntakeAgent per session. Two inputs reach the model:
  send(text)     a chat message from the user, with SSN-like numbers redacted first
  notify(event)  an app event ("secure form submitted", "signed"), so the agent can continue
LLM backend: POA_LLM_BACKEND=anthropic (default, ANTHROPIC_API_KEY) or bedrock (AWS creds).
Use synthetic data only unless the backend runs under a BAA.
"""

import json
import os
import re
from pathlib import Path

from poa_agent.service import PoaService
from poa_agent.tools import TOOLS, run_tool

SKILL = (Path(__file__).parent / "skills" / "poa_21_22a" / "SKILL.md").read_text()
MAX_TOOL_ROUNDS = 8

SYSTEM = f"""You are the intake assistant for {{firm}}, helping a veteran get their VA disability
claim started. You're warm, plain-spoken and brief: one question at a time, short messages.
You hand off to the firm's staff whenever you're unsure.

You have one skill loaded. Follow it exactly.

{SKILL}"""

# SSNs (123-45-6789, 123 45 6789, 123456789) and 8-digit VA file numbers. The separator must
# repeat, so ZIP+4 (53202-1234) and phone numbers pass through.
_ID_NUMBER = re.compile(r"(?<!\d)(?:\d{3}([- .])\d{2}\1\d{4}|\d{8,9})(?!\d)")


def redact(text: str) -> tuple[str, bool]:
    clean, n = _ID_NUMBER.subn("[number hidden for your privacy]", text)
    return clean, n > 0


def _client():
    if os.environ.get("POA_LLM_BACKEND", "anthropic") == "bedrock":
        from anthropic import AnthropicBedrock

        return AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-east-2"))
    from anthropic import Anthropic

    return Anthropic()


def default_model() -> str:
    if os.environ.get("POA_AGENT_MODEL"):
        return os.environ["POA_AGENT_MODEL"]
    if os.environ.get("POA_LLM_BACKEND") == "bedrock":
        return "us.anthropic.claude-opus-4-6-v1"
    return "claude-opus-5-5"


class IntakeAgent:
    def __init__(self, svc: PoaService, client=None, model: str | None = None):
        self.svc = svc
        self.client = client or _client()
        self.model = model or default_model()
        self.system = SYSTEM.replace("{firm}", svc.rep.get("firm_name", "the firm"))
        self.messages: list[dict] = []

    def send(self, text: str) -> dict:
        clean, redacted = redact(text)
        if redacted:
            self.svc.docs.audit("chat_pii_redacted")
            clean += "\n[app note: the user typed an ID number in chat; it was hidden from you]"
        return self._turn(clean, echo=clean if redacted else None)

    def notify(self, event: str) -> dict:
        return self._turn(f"[app event] {event}")

    def _turn(self, content: str, echo: str | None = None) -> dict:
        self.messages.append({"role": "user", "content": content})
        cards: list[dict] = []
        reply = ""
        for _ in range(MAX_TOOL_ROUNDS):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=self.system,
                tools=TOOLS,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": resp.content})
            reply = "".join(b.text for b in resp.content if b.type == "text")
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                break
            results = []
            for u in uses:
                out = run_tool(self.svc, u.name, u.input)
                cards.extend(out.cards)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": u.id,
                        "content": json.dumps(out.result),
                        "is_error": out.is_error,
                    }
                )
            self.messages.append({"role": "user", "content": results})
        else:
            reply = reply or "Let me get someone from the firm to help with this."
        return {"reply": reply, "cards": cards, "redacted_echo": echo}
