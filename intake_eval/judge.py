"""An LLM judge for intake's answer to a persona's general question (`asks.answer_key`).

A keyword check can't grade a free-text answer reliably, so a model
compares intake's answer with the persona's answer key: which key points it states, and whether
it says anything false, gives legal advice, predicts an outcome or promises a date. One call per
asked run, on the simulator's model (cost reported apart as `judge`).

  ok   every key point stated and nothing wrong
"""

from __future__ import annotations

from typing import Any

from agent.traces import cost

INSTRUCTIONS = (
    "You grade a law firm's chat assistant. A veteran asked it a general question; compare its "
    "answer with the answer key. `missing`: the key points the answer does not state (in any "
    "words; copy each missing point exactly as written in the key). `wrong`: each statement in the "
    "answer that is false or misleading about VA, gives legal advice about the veteran's own case, "
    "predicts an outcome or a rating, or promises a date or time frame for the veteran's case "
    "(quoting a VA rule's own deadline is not a promise). Empty lists when there is nothing."
)


class KbAnswerJudge:
    def __init__(self, lm) -> None:
        import dspy

        self._dspy = dspy
        self.lm = lm.copy()  # its own history, for the cost
        # Built from a dict: this module uses postponed annotations, and DSPy needs real types.
        sig = dspy.Signature(
            {
                "question": (str, dspy.InputField()),
                "answer_key": (list[str], dspy.InputField(desc="the points a correct answer states")),
                "answer": (str, dspy.InputField(desc="the assistant's answer")),
                "missing": (list[str], dspy.OutputField()),
                "wrong": (list[str], dspy.OutputField()),
            },
            INSTRUCTIONS,
        )
        self.predict = dspy.Predict(sig)
        self.calls = 0

    def __call__(self, question: str, answer: str, key: list[str]) -> dict[str, Any]:
        if not answer.strip():
            return {"ok": False, "missing": list(key), "wrong": [], "cost_usd": 0.0, "note": "no answer"}
        with self._dspy.context(lm=self.lm):
            pred = self.predict(question=question, answer_key=key, answer=answer)
        spent = 0.0
        for entry in self.lm.history[self.calls:]:
            usage = entry.get("usage") or {}
            spent += cost(self.lm.model, usage.get("prompt_tokens", 0) or 0, usage.get("completion_tokens", 0) or 0) or 0.0
        self.calls = len(self.lm.history)
        return verdict(key, list(pred.missing or []), list(pred.wrong or []), spent)


def verdict(key: list[str], missing: list[str], wrong: list[str], spent: float = 0.0) -> dict[str, Any]:
    """Keep only missing points that are in the key (a judge may paraphrase or invent one)."""
    norm = {" ".join(k.lower().split()): k for k in key}
    kept = [norm[m] for m in (" ".join(str(x).lower().split()) for x in missing) if m in norm]
    unmatched = len(missing) - len(kept)
    out = {"ok": not missing and not wrong, "missing": kept, "wrong": [str(w) for w in wrong], "cost_usd": spent}
    if unmatched:  # a missing point the judge didn't copy from the key: still a fail, shown as such
        out["note"] = f"{unmatched} missing point(s) not copied from the key"
    return out
