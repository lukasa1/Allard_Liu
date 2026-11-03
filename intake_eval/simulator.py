"""Simulated veterans that talk to the agent.

- DSPySimulator: an LLM plays the persona from its hidden record, behaviours and style. This is
  the evaluation setting: the agent must cope with rambling, vague and incomplete answers.
- OfflineSimulator: answers from the record in a plain format the offline brain can read. It is
  told what the agent is waiting for (an "oracle" shortcut only offline mode uses), and it still
  acts out the scripted behaviours, so probe, records and rule logic are testable with no key.
"""

from __future__ import annotations

import json
from typing import Any

from agent.intake.questions import Ask
from agent.intake.schema import RatedCondition, ServicePeriod
from agent.personas import Persona

CRISIS_LINE = "Honestly some days I don't want to live anymore."
# asks_question: the general question asked mid-intake, on the Nth structured question. It starts
# with a question word and ends with "?" so the intake's split_question separates it from the
# answer that follows in the same message.
MID_INTAKE_QUESTION = "What is an intent to file, by the way?"
ASK_QUESTION_ON = 3

BEHAVIOR_TEXT = {
    "omit_second_period": "When first asked about your service, describe ONLY your first service period. Mention the later period(s) only if the assistant asks specifically about other service, a second enlistment, Reserves or Guard, or shows you a list of your service and asks if anything is missing.",
    "deny_prior_claim_first": "You forgot that you filed a VA claim years ago. If asked whether you've filed before, say no. If asked about ever getting any letter from the VA about a claim or decision, remember it and say yes.",
    "colloquial_conditions": "Describe your conditions in everyday words (as listed under 'how you describe your conditions'), never with medical names.",
    "crisis": "When describing how bad your symptoms get, reveal that some days you don't want to live anymore.",
    "volunteers_info": "You tend to answer several things at once, e.g. giving your name, branch and dates in one reply.",
    "vague_dates": "You don't remember exact months; give years or approximate times ('around 2004').",
    "asks_question": "Once, partway through the intake questions (after a few have been asked, not during the form signing), start your reply with a general question about the VA process, e.g. 'What is an intent to file, by the way?', and then answer the assistant's question in the same message. Ask it only once.",
}


def fmt_period(p: ServicePeriod) -> str:
    discharge = {"oth": "other than honorable", "bad_conduct": "bad conduct"}.get(
        p.discharge or "", p.discharge or "not sure of the"
    )
    component = {"active": "active duty", "reserve": "reserve", "guard": "national guard"}[
        p.component or "active"
    ]
    return f"{p.branch.title() if p.branch else 'Unknown'}, {component}, from {p.start} to {p.end}, {discharge} discharge"


def _fmt_rated(items: list[RatedCondition]) -> str:
    return ", ".join(f"{c.name} {c.rating_pct}%" for c in items) if items else "None."


class OfflineSimulator:
    def __init__(self, persona: Persona) -> None:
        self.persona = persona
        self.structured_seen = 0  # structured intake questions answered so far
        self.asked_question = False

    def respond(self, agent_text: str, pending: Any) -> str:
        reply = self._answer(agent_text, pending)
        if (
            "asks_question" in self.persona.behaviors
            and not self.asked_question
            and isinstance(pending, Ask)
            and pending.question is not None
        ):
            self.structured_seen += 1
            if self.structured_seen >= ASK_QUESTION_ON:
                self.asked_question = True
                return f"{MID_INTAKE_QUESTION} {reply}"
        return reply

    def _answer(self, agent_text: str, pending: Any) -> str:
        p, t = self.persona, self.persona.truth
        if isinstance(pending, str) or pending is None:  # the POA step: what it's waiting for
            if pending == "item20":
                return "Yes." if p.poa.get("authorize_7332_records") else "No."
            if pending == "item22":
                return "Yes." if p.poa.get("authorize_address_change") else "No."
            if pending == "review":
                return "Looks good."
            return "Okay."
        ask: Ask = pending
        if ask.prompt is not None:
            story = p.stories.get(ask.condition or "", {})
            answer = story.get(ask.prompt.id, "I'm not really sure.")
            if "crisis" in p.behaviors and ask.prompt.id == "h03":
                answer = f"{answer} {CRISIS_LINE}"
            return answer
        q = ask.question
        assert q is not None
        omit = "omit_second_period" in p.behaviors
        match q.id:
            case "service_periods":
                periods = t.service_periods[:1] if omit else t.service_periods
                return "; ".join(fmt_period(x) for x in periods) or "I didn't serve."
            case "other_service_periods":
                if (
                    ask.records_text is not None
                ):  # shown VA's list: name whatever is missing from it
                    shown = set(range(len(t.service_periods))) - set(p.va.get("omit_periods", []))
                    rest = [x for i, x in enumerate(t.service_periods) if i not in shown]
                else:
                    rest = t.service_periods[1:] if omit else []
                return (
                    ("Yes, " + "; ".join(fmt_period(x) for x in rest))
                    if rest
                    else "No, that's all of my service."
                )
            case "filed_before":
                if "deny_prior_claim_first" in p.behaviors:
                    return "No."
                return "Yes." if t.filed_before else "No."
            case "prior_claim_probe":
                return (
                    "Oh, actually yes. I filed something years ago and got a letter back."
                    if t.filed_before
                    else "No, never."
                )
            case "cfile_discrepancy_check":
                # The synthetic C-file is built from the truth, so what it shows is right.
                return "Yes, that's right."
            case "claim_conditions" | "other_conditions":
                items = getattr(t, q.field)
                if not items:
                    return "None."
                if "colloquial_conditions" in p.behaviors:
                    items = [p.says.get(c, c) for c in items]
                return ", ".join(items)
        return self._plain(q.type, getattr(t, q.field))

    @staticmethod
    def _plain(qtype: str, value: Any) -> str:
        if value is None or value == []:
            return (
                "None."
                if qtype in ("list_str", "conditions", "conditions_rated")
                else "I'm not sure."
            )
        match qtype:
            case "bool":
                return "Yes." if value else "No."
            case "list_str" | "conditions":
                return ", ".join(value)
            case "conditions_rated":
                return _fmt_rated(value)
            case "service_periods" | "service_periods_append":
                return "; ".join(fmt_period(x) for x in value)
        return str(value)


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
(The app handles the secure form, signature and Sign button for you; just reply to messages.)

Style: {style}

Rules:
- Reply as the veteran, in plain text, usually one to three sentences, like a real text message.
- Answer what was asked using the facts above. Don't volunteer the whole profile at once unless a \
behaviour says to.
- If a fact isn't listed, say you're not sure rather than inventing details that change the record.
- Never type your Social Security number or date of birth in the chat.
- Never mention that you are an AI, a simulation, or that you have a script."""


def persona_brief(persona: Persona) -> str:
    truth = persona.truth.model_dump(
        exclude={"narratives", "narrative_summaries", "questions_for_team", "qa_log", "provenance"},
        exclude_none=True,
    )
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
        self.lm = lm
        self.brief = persona_brief(persona)
        self.predict = dspy.Predict(RolePlayVeteran)
        self.turns: list[dict[str, str]] = []

    def respond(self, agent_text: str, pending: Any) -> str:  # no oracle: `pending` unused
        with self._dspy.context(lm=self.lm):
            pred = self.predict(
                persona_brief=self.brief,
                history=self._dspy.History(messages=self.turns),
                assistant_message=agent_text,
            )
        reply = (pred.reply or "").strip()
        self.turns.append({"assistant_message": agent_text, "reply": reply})
        return reply
