"""Record a scripted-demo story from one eval run: every model output, word for word.

    uv run python -m agent.scripted.record results/midpoint/runs/cfile/recent_decision \
        > agent/scripted/demo_story.json

A run directory (written by `intake eval`) holds the case's traces (traces.jsonl: one `lm` line
per model call, with the case, agent and turn) and its events (cases.sqlite). The story keeps,
per agent and in order, the raw text of each model call of each turn (retries and the adapter's
fallback calls included), so the scripted LM (agent/scripted/lm.py) answers the real harness,
parsers and tools exactly as the model did; and the chat as it happened, so the demo can suggest
the veteran's next line and a test can check that a replay says the same thing.

The traces hide ID numbers and typed dates of birth in the model's prose (agent/traces.py); the
tool arguments the face note needs are not touched by that, so a replay records the same facts.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _text(output: Any) -> str:
    """A model call's output as the adapter saw it: DSPy logs a string, or a dict with `text`."""
    first = output[0] if isinstance(output, list) else output
    return first["text"] if isinstance(first, dict) else first


def story_from_run(run_dir: Path, persona: str) -> dict[str, Any]:
    traces = [json.loads(line) for line in (run_dir / "traces.jsonl").read_text().splitlines() if line.strip()]
    case_ids = {t["case_id"] for t in traces if t.get("case_id")}
    if len(case_ids) != 1:
        raise ValueError(f"{run_dir}: expected one case, found {sorted(case_ids)}")
    turns: list[dict[str, Any]] = []
    for t in traces:
        if t["kind"] != "lm":
            continue
        if t.get("error"):  # a call that raised has no output to replay
            raise ValueError(f"{run_dir}: {t['agent']} turn {t['turn']}: a model call failed ({t['error']})")
        if not turns or (turns[-1]["agent"], turns[-1]["turn"]) != (t["agent"], t["turn"]):
            turns.append({"agent": t["agent"], "turn": t["turn"], "outputs": []})
        turns[-1]["outputs"].append(_text(t["output"]))
    agents = {a: [x["turn"] for x in turns if x["agent"] == a] for a in {x["agent"] for x in turns}}
    for agent, numbers in agents.items():  # one block per turn: interleaving would split a turn
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"{agent}: a turn's model calls are interleaved with another turn's")
    db = sqlite3.connect(run_dir / "cases.sqlite")
    try:
        rows = db.execute("select data from events where type = 'message' order by seq").fetchall()
    finally:
        db.close()
    chat = [{"from": d["from"], "text": d["text"]} for d in (json.loads(r[0]) for r in rows)]
    return {
        "persona": persona,
        "source": f"{run_dir.parent.name}/{run_dir.name}",
        "turns": [{"agent": x["agent"], "outputs": x["outputs"]} for x in turns],
        "chat": chat,
    }


def main(argv: list[str]) -> None:
    run_dir = Path(argv[0])
    json.dump(story_from_run(run_dir, argv[1] if len(argv) > 1 else run_dir.name), sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
