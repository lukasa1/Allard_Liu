"""The simulated veteran: an LLM (Haiku, config.make_lm("simulator")) plays the persona from its
hidden record, behaviours and style, so the agents must cope with rambling, vague and incomplete
answers. It only ever sees the agents' chat messages; the eval runner uses the cards for it.

`respond(agent_text) -> reply` is the whole interface (tests pass a scripted stand-in). The
simulator's own model calls are counted (`calls`, `cost`) so the eval can report and cap them.
"""

from __future__ import annotations

import json

from agent.personas import Persona
from agent.traces import cost

BEHAVIOR_TEXT = {
    "omit_second_period": "When first asked about your service, describe ONLY your first service period. Mention the later period(s) only if the assistant asks specifically about other service, a second enlistment, Reserves or Guard, or shows you a list of your service and asks if anything is missing.",
    "deny_prior_claim_first": "You forgot that you filed a VA claim years ago. If asked whether you've filed before, say no. If asked about ever getting any letter from the VA about a claim or decision, remember it and say yes.",
    "colloquial_conditions": "Describe your conditions in everyday words (as listed under 'how you describe your conditions'), never with medical names.",
    "crisis": "When describing how bad your symptoms get, reveal that some days you don't want to live anymore.",
    "volunteers_info": "You tend to answer several things at once, e.g. giving your name, branch and dates in one reply.",
    "vague_dates": "You don't remember exact months; give years or approximate times ('around 2004').",
    "asks_question": "Once, partway through the intake questions (after a few have been asked, not during the form signing), start your reply with a general question about the VA process, e.g. 'What is an intent to file, by the way?', and then answer the assistant's question in the same message. Ask it only once.",
    "new_condition_during_prep": "Your last listed claim condition was diagnosed only last week. Leave it out until your forms are filed: the app tells the firm about it for you while they read your VA file. If the assistant asks about it after that, confirm it and describe it.",
}


SIM_BRIEF = """You are role-playing a U.S. military veteran who is texting with a law firm's intake \
assistant about a VA disability claim. Stay in character the whole time.

Who you are (the facts are hidden from the assistant; reveal them only when asked or when it's natural):
{truth}

How you describe each condition and what you'd say about it:
{stories}

How you describe your conditions in everyday words: {says}

Behaviours to act out:
{behaviors}

When the assistant asks you to sign the form that lets its attorney represent you:
- may the attorney see VA records about drug or alcohol treatment, HIV or sickle cell anemia: {item20}
- may the attorney update your mailing address with VA: {item22}
- when it shows you the form and asks if it looks right, say it looks right.
- when it shows you the fee agreement and asks whether you agree, say yes.
(The app fills the secure form, draws your signature and clicks Sign for you; just reply to messages.)

Style: {style}

Rules:
- Reply as the veteran, in plain text, usually one to three sentences, like a real text message.
- Answer what was asked using the facts above. Don't volunteer the whole profile at once unless a \
behaviour says to.
- If a fact isn't listed, say you're not sure rather than inventing details that change the record.
- Never type your Social Security number or date of birth in the chat.
- Never mention that you are an AI, a simulation, or that you have a script."""


def persona_brief(persona: Persona) -> str:
    truth = persona.truth.model_dump(exclude_none=True)
    return SIM_BRIEF.format(
        truth=json.dumps(truth, indent=2),
        stories=json.dumps(persona.stories, indent=2),
        says=json.dumps(persona.says) if persona.says else "(use the names above)",
        behaviors="\n".join(f"- {BEHAVIOR_TEXT.get(b, b)}" for b in persona.behaviors)
        or "- (none)",
        item20="yes" if persona.poa.get("authorize_7332_records") else "no",
        item22="yes" if persona.poa.get("authorize_address_change") else "no",
        style=persona.style or "Cooperative, a bit informal.",
    )


class DSPySimulator:
    def __init__(self, persona: Persona, lm) -> None:
        import dspy

        # Built from a dict: this module uses postponed annotations, and DSPy needs real types.
        RolePlayVeteran = dspy.Signature(
            {
                "persona_brief": (str, dspy.InputField()),
                "history": (dspy.History, dspy.InputField()),
                "assistant_message": (
                    str,
                    dspy.InputField(desc="the intake assistant's latest message(s)"),
                ),
                "reply": (str, dspy.OutputField()),
            },
            "Reply as the veteran described in the brief, following its rules. Output only the reply text.",
        )

        self._dspy = dspy
        self.persona = persona
        self.lm = lm.copy()  # its own history: the cost below reads this simulator's calls only
        self.brief = persona_brief(persona)
        self.predict = dspy.Predict(RolePlayVeteran)
        self.turns: list[dict[str, str]] = []
        self.calls, self.cost = 0, 0.0

    def respond(self, agent_text: str) -> str:
        with self._dspy.context(lm=self.lm):
            pred = self.predict(
                persona_brief=self.brief,
                history=self._dspy.History(messages=self.turns),
                assistant_message=agent_text,
            )
        for entry in self.lm.history[self.calls:]:
            usage = entry.get("usage") or {}
            self.cost += cost(self.lm.model, usage.get("prompt_tokens", 0) or 0, usage.get("completion_tokens", 0) or 0) or 0.0
        self.calls = len(self.lm.history)
        reply = (pred.reply or "").strip()
        self.turns.append({"assistant_message": agent_text, "reply": reply})
        return reply


def load_chat(sim: DSPySimulator, messages: list[dict]) -> str:
    """Load a chat so far (message events: from, text) into `sim`'s history, for the demo's
    autoplay. Returns the agents' messages since the veteran last spoke."""
    agent: list[str] = []
    for m in messages:
        if m["from"] == "veteran":
            sim.turns.append({"assistant_message": "\n\n".join(agent), "reply": m["text"]})
            agent = []
        elif m.get("to") == "veteran":
            agent.append(m["text"])
    return "\n\n".join(agent)
