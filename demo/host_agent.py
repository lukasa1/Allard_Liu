"""Example host agent for the demo: a generic assistant that MOUNTS the POA skill.

This is not part of the skill. It shows the integration contract from poa_skill/__init__.py:
skill instructions appended to the host's prompt, skill tools added to the host's tool list,
skill tool calls routed to skill.run_tool, user chat passed through poa_skill.redact first.
A real intake agent mounts this skill alongside its other skills the same way.

LLM: any OpenAI-compatible endpoint. Defaults to OpenRouter (OPENROUTER_API_KEY), model from
POA_AGENT_MODEL (default anthropic/claude-sonnet-5.5). OpenRouter is not covered by a BAA: the
skill keeps SSN/DOB out of the model by design, but use synthetic data only.
"""

import json
import os

from poa_skill import PoaService, load_skill, redact
from poa_skill.guard import REDACTION_NOTE

MAX_TOOL_ROUNDS = 8
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"

HOST_PROMPT = """You are an intake assistant for a law firm that represents veterans before VA.
Be warm and brief: one question at a time. Use a skill when its description fits the task."""


def _client():
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("POA_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


class HostAgent:
    def __init__(self, svc: PoaService, client=None, model: str | None = None):
        self.svc = svc
        self.skill = load_skill()
        self.client = client or _client()
        self.model = model or os.environ.get("POA_AGENT_MODEL", DEFAULT_MODEL)
        system = (
            f"{HOST_PROMPT}\n\n## Skill: {self.skill.name}\n{self.skill.description}\n\n"
            f"{self.skill.instructions}"
        )
        self.tools = list(self.skill.tools_openai)  # a real host adds its own tools here
        self.messages: list[dict] = [{"role": "system", "content": system}]

    def send(self, text: str) -> dict:
        clean, redacted = redact(text)
        if redacted:
            self.svc.docs.audit("chat_pii_redacted")
            clean += "\n" + REDACTION_NOTE
        return self._turn(clean, echo=clean if redacted else None)

    def notify(self, event: str) -> dict:
        return self._turn(f"[app event] {event}")

    def _turn(self, content: str, echo: str | None = None) -> dict:
        self.messages.append({"role": "user", "content": content})
        cards: list[dict] = []
        reply = ""
        for _ in range(MAX_TOOL_ROUNDS):
            resp = self.client.chat.completions.create(
                model=self.model, messages=self.messages, tools=self.tools, max_tokens=1500
            )
            msg = resp.choices[0].message
            reply = msg.content or ""
            calls = msg.tool_calls or []
            self.messages.append(
                {
                    "role": "assistant",
                    "content": reply,
                    **(
                        {
                            "tool_calls": [
                                {
                                    "id": c.id,
                                    "type": "function",
                                    "function": {
                                        "name": c.function.name,
                                        "arguments": c.function.arguments,
                                    },
                                }
                                for c in calls
                            ]
                        }
                        if calls
                        else {}
                    ),
                }
            )
            if not calls:
                break
            for c in calls:
                if c.function.name in self.skill.tool_names:
                    try:
                        args = json.loads(c.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    out = self.skill.run_tool(self.svc, c.function.name, args)
                    cards.extend(out.cards)
                    result = out.result
                else:
                    result = {"error": f"unknown tool {c.function.name}"}
                self.messages.append(
                    {"role": "tool", "tool_call_id": c.id, "content": json.dumps(result)}
                )
        else:
            reply = reply or "Let me get someone from the firm to help with this."
        return {"reply": reply, "cards": cards, "redacted_echo": echo}
