"""The scripted demo (`uv run intake serve --scripted`): one whole case played with no model.

The real runtime, tools, guard, stage table, documents, claims prep's verify and the case panel
run as usual; only the model is replaced by agent/scripted/lm.py, which answers every model call
with the text the model gave in one real eval run (agent/scripted/demo_story.json, recorded by
agent/scripted/record.py from the midpoint run of recent_decision). The case runs on the clock
and IDs the eval pinned for that run, so its dates and confirmation codes are the run's too.

The presenter follows the story: the input box holds the veteran's next line from the run (Enter
sends it; nothing else can be sent), and the cards (secure form, signature, Sign) and the
attorney's Countersign are used as they appear.

The story: Hector Alvarez (persona recent_decision), Marine Corps 2002-2010, rated 40% (PTSD 30%,
tinnitus 10%), a 2026 decision that denied his left knee. Claims prep reads his synthetic C-file;
the face note puts the 2026 decision on a numbered line with its appeal deadline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from agent import clock
from agent.scripted.lm import Raw, ScriptedLM

STORY = Path(__file__).with_name("demo_story.json")
PERSONA = "recent_decision"
OFF_SCRIPT = "(Scripted demo: this step isn't in the recorded run, so no agent answers it. Start case plays the story again.)"
NOT_NEXT = "Scripted demo: send the line in the box (the veteran's next line in the recorded run)."


@dataclass
class Story:
    persona: str
    veteran: list[str]  # the veteran's lines, in order
    turns: list[tuple[str, list[str]]] = field(default_factory=list)  # (agent, raw model outputs), in order
    # An agent's reply -> the veteran's line that answers it. The input box holds the line for
    # the reply last shown, so a chat that left the script (a canned reply) gets none rather than
    # a wrong one.
    answers: dict[str, str] = field(default_factory=dict)
    chat: list[dict[str, str]] = field(default_factory=list)  # the run's chat: {from, text}
    condition: str = "cfile"  # the eval condition the run used

    @property
    def seed(self) -> str:
        """The seed the eval pinned the run with (intake_eval/runner.py: persona|condition)."""
        return f"{self.persona}|{self.condition}"

    def suggestion(self, last_reply: str | None) -> str:
        return self.answers.get(last_reply or "", "")

    def load(self, lm: ScriptedLM) -> None:
        """Script the LM and pin the clock: call right before the case opens."""
        lm.reset()
        for agent, outputs in self.turns:
            lm.turn(agent, *(Raw(text) for text in outputs))
        clock.pin(self.seed, again=True)


@cache
def story() -> Story:
    data = json.loads(STORY.read_text())
    answers: dict[str, str] = {}
    last = None
    for m in data["chat"]:
        if m["from"] == "veteran":
            answers.setdefault(last or "", m["text"])
        else:
            last = m["text"]
    veteran = [m["text"] for m in data["chat"] if m["from"] == "veteran"]
    turns = [(t["agent"], t["outputs"]) for t in data["turns"]]
    condition = data["source"].split("/")[0]  # "cfile/recent_decision"
    return Story(data["persona"], veteran, turns, answers, data["chat"], condition)
