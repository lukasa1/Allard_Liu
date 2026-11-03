"""Skills per agent, in the architecture's layout: one folder per skill with a SKILL.md (a name, a
one-line description, then the directions).

Only the index (name + description) sits in an agent's prompt; `read_skill` loads one skill's
directions when the model decides it needs them (progressive disclosure). The harness
(agent/harness.py) gives every agent the index in its prompt and a `read_skill` tool for its own
folder. Where code enforces a rule (routing, the stage guard), the skill describes it for the
model, and tests keep the two in sync.

  orchestrator/  stage-playbook, routing, flags
  intake/        screen-veteran, poa-and-fees, intent-to-file, close-gaps
  claims_prep/   face-note-format, cfile-vs-intake
  support/       case-status, answer-questions, hand-to-a-person
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent
AGENTS = ("orchestrator", "intake", "claims_prep", "support")


@dataclass(frozen=True)
class SkillDoc:
    agent: str
    name: str
    description: str
    body: str


def _parse(path: Path, agent: str) -> SkillDoc:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing frontmatter")
    head, body = text[4:].split("\n---\n", 1)
    meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
    return SkillDoc(agent, meta["name"], meta["description"], body.strip())


def load_skills(agent: str) -> dict[str, SkillDoc]:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}")
    return {s.name: s for s in (_parse(p, agent) for p in sorted((ROOT / agent).glob("*/SKILL.md")))}


def skill_index(agent: str) -> str:
    """The lines that go in the agent's prompt: one per skill."""
    return "\n".join(f"- {s.name}: {s.description}" for s in load_skills(agent).values())


def read_skill(agent: str, name: str) -> str:
    skills = load_skills(agent)
    if name not in skills:
        return f"No skill named {name!r}. Available: {', '.join(skills)}"
    return skills[name].body
