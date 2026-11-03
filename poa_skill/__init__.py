"""POA skill: complete and click-to-sign VA Form 21-22a.

A skill, not an agent. Any host agent mounts it by adding the instructions to its context and
the tools to its tool list, then routing those tool calls to `run_tool`:

    from poa_skill import load_skill, PoaService

    skill = load_skill()
    system_prompt = host_prompt + "\\n\\n" + skill.instructions   # or load on demand
    tools = host_tools + skill.tools_openai      # or skill.tools (Anthropic format)
    ...
    if call.name in skill.tool_names:
        out = skill.run_tool(PoaService(session_id), call.name, args)
        # out.result -> tool_result for the model; out.cards -> UI for the host to render

The host must also: render the cards (secure form, signature pad, preview, Sign button), post
secure-form and signature submissions to PoaService, call PoaService.sign() only from the
user's click, and run user chat through guard.redact().
"""

from dataclasses import dataclass
from pathlib import Path

from poa_skill.guard import redact
from poa_skill.service import ESIGN_CONSENT, FEE_ESIGN_CONSENT, FORMS, PoaService, WorkflowError
from poa_skill.tools import TOOLS, ToolOutcome, openai_tools, run_tool

SKILL_DIR = Path(__file__).parent / "skills" / "poa_21_22a"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str  # SKILL.md body (frontmatter stripped)
    tools: list[dict]  # Anthropic tool-use format
    run_tool: object

    @property
    def tools_openai(self) -> list[dict]:
        """OpenAI function-calling format, for OpenRouter and other OpenAI-compatible hosts."""
        return openai_tools(self.tools)

    @property
    def tool_names(self) -> set[str]:
        return {t["name"] for t in self.tools}


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    head, body = text[3:].split("\n---", 1)
    meta = dict(line.split(":", 1) for line in head.strip().splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in meta.items()}, body.lstrip()


def load_skill() -> Skill:
    meta, body = _frontmatter((SKILL_DIR / "SKILL.md").read_text())
    return Skill(meta["name"], meta["description"], body, TOOLS, run_tool)


__all__ = [
    "ESIGN_CONSENT",
    "FEE_ESIGN_CONSENT",
    "FORMS",
    "PoaService",
    "Skill",
    "ToolOutcome",
    "WorkflowError",
    "load_skill",
    "redact",
]
