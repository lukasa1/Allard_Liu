"""The scripted demo (`uv run intake serve --scripted`, D26): one whole case played with no model.

The real runtime, tools, guard, stage table, documents, claims prep's verify and the case panel
run as usual; only the model is replaced by agent/scripted/lm.py, loaded with this story when a
case starts. Each agent takes its scripted turns in order, so the presenter follows the story:
press Tab to take the veteran's line the input box suggests, press Enter, and use the cards (secure
form, signature, Sign) and the attorney's Countersign as they appear. Typing something else
still runs the real code, but the agents' answers stay on the script.

The story: Hector Alvarez (persona recent_decision), Marine Corps 2002-2010, rated 40% (PTSD 30%,
tinnitus 10%), a 2026 decision that denied his left knee. Claims prep reads his synthetic C-file;
the face note puts the 2026 decision on a numbered line with its appeal deadline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.scripted.lm import ScriptedLM, call, final
from agent.scripted.prep import prep_steps
from intake_eval.runner import SECURE_FIELDS

PERSONA = "recent_decision"
MARINES = [{"branch": "marine corps", "component": "active", "start": "2002-06", "end": "2010-06",
            "discharge": "honorable"}]  # fmt: skip
OFF_SCRIPT = "(Scripted demo: that message isn't in the script, so no agent answers it. The story is over here: Start case plays it again.)"
PASS1 = {"finished": "pass 1: 21-22a and ITF filed, fee agreement faxed"}


@dataclass
class Story:
    persona: str
    veteran: list[str]  # the veteran's lines, in order
    turns: list[tuple[str, tuple]] = field(default_factory=list)  # (agent, steps), in order
    # An agent's reply -> the veteran's line that answers it. The input box suggests the line for
    # the reply last shown, so a chat that left the script (an off-script message, a canned reply)
    # gets no suggestion rather than a wrong one.
    answers: dict[str, str] = field(default_factory=dict)

    def suggestion(self, last_reply: str | None) -> str:
        return self.answers.get(last_reply or "", "")

    def load(self, lm: ScriptedLM) -> None:
        lm.reset()
        for agent, steps in self.turns:
            lm.turn(agent, *steps)


def _r(q: str, a: str, value=None, **kw):
    return call("record_answer", q=q, a=a, **({"value": value} if value is not None else {}), **kw)


def story() -> Story:
    t: list[tuple[str, tuple]] = []
    answers: dict[str, str] = {}

    def turn(agent: str, *steps, then: str | None = None) -> None:
        """`then`: the veteran's line that answers this turn's reply."""
        t.append((agent, steps))
        if then:
            answers[steps[-1].reply] = then

    # Case opened: the orchestrator hands pass 1 to intake, which greets the veteran.
    turn("orchestrator", call("run_intake", goal="Pass 1: screen, open the account, file."),
         final(reply="Welcome to the firm. Our intake assistant will take it from here."))  # fmt: skip
    turn(
        "intake",
        final(reply="Hi! I'll help you get started. Have you served in the U.S. military?"),
        then='Yes, I served in the Marine Corps.',
    )
    # Screening.
    turn("intake", _r("is_veteran", "Yes, I served in the Marine Corps.", True),
         final(reply="Thank you for your service. What were your dates of service, and how was your discharge characterized?"), then='Active duty, June 2002 to June 2010, honorable discharge. That was my only enlistment.')  # fmt: skip
    turn("intake", _r("service_periods", "Active duty, June 2002 to June 2010, honorable discharge", MARINES),
         _r("other_service_periods", "That was my only enlistment.", []),
         final(reply="Got it. Have you ever filed a claim with the VA? And are you receiving VA disability pay now?"), then='Yes, I filed with the VA before. I get disability pay now, 40 percent.')  # fmt: skip
    turn("intake", _r("filed_before", "Yes, I filed with the VA before."),
         _r("receiving_va_pay", "I get disability pay now", True), _r("rating_pct", "40 percent", 40),
         final(reply="Thanks. Have you ever had an attorney or agent represent you on a VA claim?"), then="No, I've never had a lawyer or anyone else represent me.")  # fmt: skip
    # Account opening: the secure form, the 21-22a, the fee agreement.
    turn("intake", _r("prior_attorney", "No, I've never had a lawyer or anyone else represent me.", False),
         call("request_secure_info", fields=list(SECURE_FIELDS), purpose="For your VA Form 21-22a (appointing our attorney)."),
         final(reply="You qualify for us to help. Please fill in the secure form: only our team sees those numbers."))  # fmt: skip
    turn("intake", call("fill_pdf", form="21-22a", fields={"authorize_7332_records": True,
                                                          "authorize_address_change": False}),
         final(reply="Here is your 21-22a, which appoints our attorney. Does everything look right?"), then='Yes, that all looks right.')  # fmt: skip
    turn(
        "intake",
        call("get_signature", form="21-22a"),
        final(reply="Please draw your signature below."),
    )
    turn(
        "intake",
        call("get_signature", form="21-22a"),
        final(reply="Your signature is saved. Click Sign when you're ready."),
    )
    turn("intake", call("fill_pdf", form="fee_agreement", fields={}),
         final(reply="Next is the fee agreement: 30% of past-due benefits, and only if you win. Do you agree?"), then='Yes, I agree to the fee agreement.')  # fmt: skip
    turn(
        "intake",
        call("get_signature", form="fee_agreement"),
        final(reply="Click Sign to sign the fee agreement."),
    )
    turn("intake", final(reply="Thank you! Our attorney is reviewing both documents now."))
    # The attorney countersigns: intake files, the orchestrator starts claims prep in the background.
    turn("intake", call("submit_va", form="21-22a"), call("submit_va", form="itf"),
         call("efax_ogc", doc="fee_agreement"),
         final(reply="We filed your 21-22a and an intent to file with the VA, and faxed the fee agreement.", result=PASS1))  # fmt: skip
    turn("orchestrator", call("run_prep", goal="Pull and read the C-file, prefill intake, write the face note."),
         final(reply="We've asked the VA for your claim file. I'll be back with a few questions once we've read it."))  # fmt: skip
    turn("claims_prep", *prep_steps(PERSONA), final(result={"finished": "face note verified"}))
    turn(
        "orchestrator",
        call("run_intake", goal="Pass 2: ask only what the C-file left open."),
        final(),
    )
    for (_, steps), (line, _) in zip(PASS2, [*PASS2[1:], ("", ())], strict=True):
        turn("intake", *steps, then=line or None)
    turn("orchestrator", final())
    return Story(PERSONA, [*answers.values()], t, answers)


K = "left knee condition"


def _h(prompt: str, a: str):
    return _r(f"narrative:{K}:{prompt}", a)


# Pass 2: the C-file settled service, rating, conditions and MOS, so intake asks only the rest
# (several questions per message), then the story prompts for the claimed condition.
PASS2: list[tuple[str, tuple]] = [
    (
        "",
        (
            final(
                reply="We've read your VA file, so I only have a few questions left. Are you receiving TDIU "
                "(Individual Unemployability)? Is this claim for you, or for death benefits for a family member? "
                "Are you earning more than $1,600 a month from work? And do you receive Social Security?"
            ),
        ),
    ),
    (
        "No TDIU. The claim is for me. I work part time, about $1,200 a month. No Social Security.",
        (
            _r("tdiu", "No TDIU.", False),
            _r("dic_claim", "The claim is for me.", False),
            _r("earning_over_1600", "I work part time, about $1,200 a month.", False),
            _r("receives_ssa", "No Social Security.", False),
            final(
                reply="Thanks. Would you like us to look into Social Security disability for you too? And may we "
                "share your contact details with a partner firm if one of our attorneys can't help?"
            ),
        ),
    ),
    (
        "No thanks on Social Security. Yes, you can share my details with a partner firm.",
        (
            _r("ssa_interest", "No thanks on Social Security.", False),
            _r("partner_share_consent", "Yes, you can share my details with a partner firm.", True),
            final(
                reply="Did you retire from the military? And were you exposed to anything like Agent Orange, burn "
                "pits, Camp Lejeune water or radiation?"
            ),
        ),
    ),
    (
        "I didn't retire, I got out after eight years. I was around burn pits.",
        (
            _r("retired", "I didn't retire, I got out after eight years.", False),
            _r("exposures", "I was around burn pits.", ["burn pits"]),
            final(
                reply="Has a law firm contacted you about a lawsuit over that exposure? Also, your file shows the "
                "VA denied your left knee in March 2026. Which conditions do you want our attorneys to help with?"
            ),
        ),
    ),
    (
        "No lawyer has contacted me about that. The left knee: they denied it and I think they got it wrong.",
        (
            _r("litigation_contact", "No lawyer has contacted me about that.", False),
            _r("claim_conditions", "The left knee", [K]),
            final(
                reply="Any other medical conditions you're dealing with? And for your left knee: what are the "
                "symptoms, and how bad does it get on a bad day?"
            ),
        ),
    ),
    (
        "No other conditions. My left knee aches, swells and sometimes gives out on stairs. On bad days I need a cane.",
        (
            _r("other_conditions", "No other conditions.", []),
            _h("h02", "My left knee aches, swells and sometimes gives out on stairs."),
            _h("h03", "On bad days I need a cane."),
            final(
                reply="When did it start, how often do you have symptoms, and has it gotten better or worse since service?"
            ),
        ),
    ),
    (
        (
            "It started in service after a hard parachute landing in 2005 that twisted my knee. It hurts every day and "
            "it's gotten worse since I got out."
        ),
        (
            _h("h04", "It started in service after a hard parachute landing in 2005."),
            _h("h05", "It hurts every day."),
            _h("h06", "It's gotten worse since I got out."),
            _h("h10", "A hard parachute landing that twisted my knee."),
            final(
                reply="Where were you stationed, and what were the conditions around you? Did you get treatment then?"
            ),
        ),
    ),
    (
        (
            "Camp Lejeune, North Carolina. We were in the field on a jump, with heavy packs on rough terrain. I went to "
            "medical and got a brace."
        ),
        (
            _h("h07", "Camp Lejeune, North Carolina."),
            _h("h08", "We were in the field on a jump."),
            _h("h09", "Heavy packs on rough terrain."),
            _h("h11", "I went to medical and got a brace."),
            final(
                reply="How does your knee affect your work and your daily life? How were things before service? "
                "Anything else you want the VA to know?"
            ),
        ),
    ),
    (
        (
            "I can't do the standing jobs I used to, and I miss about two days a month. I can't play with my kids or hike "
            "anymore. I had no knee problems before the Marines. The VA got it wrong, that's all."
        ),
        (
            _h("h12", "I can't do the standing jobs I used to."),
            _h("h13", "I miss about two days a month."),
            _h("h14", "I can't play with my kids or hike anymore."),
            _h("h15", "I had no knee problems before the Marines."),
            _h("h16", "The VA got it wrong."),
            final(
                reply="Thank you, that helps a lot. Last few: your marital status, any children under 18, your next "
                "of kin (name, relationship, phone), and how you heard about us?"
            ),
        ),
    ),
    (
        (
            "Married, my wife is Maria. Two kids under 18. Next of kin is Maria Alvarez, my wife, 414-555-0143. A friend "
            "told me about you."
        ),
        (
            _r("marital_status", "Married", "married"),
            _r("spouse_name", "my wife is Maria", "Maria"),
            _r("children_under_18", "Two kids under 18.", True),
            _r("next_of_kin", "Maria Alvarez, my wife, 414-555-0143"),
            _r("heard_about", "A friend told me about you."),
            final(
                reply="That's everything. Your case is now with our attorney for review, and we'll be in touch.",
                result={"finished": "pass 2: gaps closed"},
            ),
        ),
    ),
]
PASS2_LINES = [line for line, _ in PASS2 if line]
