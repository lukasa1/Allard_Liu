"""Input guards: every message the veteran types passes through here before any model sees it.

One home for the deterministic checks that run whatever a subagent or model would say:

  redact_chat   hide ID numbers (poa_skill.redact) and a date of birth typed next to a birth word
  detect_crisis crisis language (the session and the intake controller hand off on it)
  wants_human   a request to talk to a person (not a mention of one)
  ingest        all three at once, on the redacted text

Crisis detection favours recall: when unsure, it flags. It still has to leave ordinary injury and
PTSD narratives alone ("I hurt myself lifting a crate", "the suicide of my friend"), because the
intake controller ends the intake on a crisis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from poa_skill import redact

HIDDEN = "[number hidden for your privacy]"  # poa_skill.guard's placeholder

# ----------------------------------------------------------------------------- date of birth
# A date of birth typed in chat (chat never asks for one; the secure form does). Only next to a
# birth word, so service dates stay readable ("from 2004-06 to 2010-05"):
#   "born 03/14/1985", "DOB: 1985-03-14", "born on 1985/03/14", "born March 14th, 1985",
#   "my birthday is the 14th of March 1985"
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_CHAT_DOB = re.compile(
    r"\b(born|birth ?(?:day|date)|date of birth|d\.?o\.?b\b\.?)\W{0,3}"
    r"(?:(?:in|on|was|is|of)\s+)?(?:the\s+)?"
    r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"  # 03/14/1985, 3-14-85
    r"|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}"  # 1985-03-14, 1985/03/14, 1985.03.14
    rf"|{_MONTH}\s+{_DAY},?\s+\d{{4}}"  # March 14th, 1985
    rf"|{_DAY}\s+(?:of\s+)?{_MONTH},?\s+\d{{4}})",  # 14th of March 1985, 14 March 1985
    re.IGNORECASE,
)


def redact_chat(text: str) -> tuple[str, bool]:
    """Hide ID numbers and a typed date of birth. Returns (clean text, whether anything was hidden)."""
    clean, redacted = redact(text)
    clean, n_dob = _CHAT_DOB.subn(lambda m: f"{m.group(1)} {HIDDEN}", clean)
    return clean, redacted or n_dob > 0


# ----------------------------------------------------------------------------- crisis
# Verbs that turn "end it" / "hurt myself" from a narrative into intent or ideation.
_INTENT = (
    r"(?:want(?:ed)?|wanna|going|gonna|plan(?:ning|ned)?(?: on)?|ready|decided|about|trying|tried|try"
    r"|might|may|could|will|would|'ll|urge|thoughts?|thinking|think|thought|feel like|considering"
    r"|considered|keep thinking)"
)
_CRISIS = re.compile(
    r"\b("
    # killing / ending one's life
    r"kill(?:ing)? myself|end(?:ing)? my (?:own )?life|tak(?:e|ing) my (?:own )?life|end(?:ing)? it all"
    rf"|{_INTENT}(?: about| of| on| to)? (?:end|ending) (?:it|things|everything|my life)\b"
    # suicide: first-person ideation or attempts, not "his suicide" or "suicide prevention"
    r"|suicidal\w*|self[- ]?harm\w*"
    r"|(?:attempt(?:ed|ing)?|tried|try(?:ing)?|thought|thinking|think|considered|considering"
    r"|contemplat\w+|want(?:ed)?|wanna|going|gonna|plan(?:ning|ned)?)"
    r"(?: about| of| to)? (?:commit(?:ting)? )?suicide"
    r"|my (?:own )?suicide|(?<!his )(?<!her )(?<!their )(?<!'s )suicide (?:attempt|note|plan)s?"
    # wanting to die (not "want to die laughing")
    r"|(?:want|wanna|wanted|ready) (?:to )?die\b(?!\s+(?:laughing|of (?:laughter|embarrassment|shame)))"
    r"|(?:don'?t|do not|no longer) want to (?:live|be here|be alive|wake up|exist|go on)"
    r"|wish i (?:was|were|could be) dead|better off dead|better off without me"
    r"|(?:no|any|the|a) (?:reason|point) (?:in |to |of )?(?:living|live|being alive|going on)"
    r"|nothing (?:left )?to live for"
    r"|(?:shoot|hang|cutting|burning|starving) myself"
    # hurting oneself: intent, not an injury ("I hurt myself lifting a crate", "cut myself shaving")
    r"|hurting myself|harm(?:ing)? myself|(?:hurt|cut|burn(?:ed)?) myself (?:on purpose|again|deliberately)"
    rf"|{_INTENT}(?: of| about| to)? (?:hurt|cut|burn|harm) myself"
    r"|overdos\w*|(?:tried|try|trying|want|wanna|going|gonna)(?: to)? od\b"
    r"|took (?:too many|a bunch of|all (?:of )?my) (?:pills|meds|medications?)"
    r"|(?:could|should|might|will|gonna|going to) just end it\b"
    r"|(?:want|wish|need) (?:it|this|everything)(?: all)? (?:to )?(?:be )?over\b"
    r"|(?:want|wish) (?:it all|everything) to (?:end|stop)"
    r")",
    re.IGNORECASE,
)
# "my buddy died of an overdose" is a narrative; an overdose of one's own is not. Kept simple:
# any first-person "overdose" phrase counts, but a third-person one needs a person to judge.
_THIRD_PERSON_OD = re.compile(
    r"\b(he|she|they|his|her|their|friend|buddy|brother|sister|son|daughter|wife|husband)\b[^.!?]{0,40}"
    r"\boverdos\w*",
    re.IGNORECASE,
)


def detect_crisis(text: str) -> bool:
    for m in _CRISIS.finditer(text):
        phrase = m.group(1).lower()
        if phrase.startswith("overdos") and _THIRD_PERSON_OD.search(text) and not re.search(
            r"\bi\b[^.!?]{0,30}overdos", text, re.IGNORECASE
        ):
            continue
        return True
    return False


# ----------------------------------------------------------------------------- wants a person
# A request to talk to a person, not any mention of one: "I never could talk to someone about it"
# (a narrative) and "Does a human read this?" or "Do I need to talk to someone at VA?" (questions
# about the process) must not end the intake.
_WHO = (
    r"(someone|somebody|a person|a real person|a human|a real human|an? (attorney|lawyer)"
    r"|(my|the|our|your) (attorney|lawyer)|a staff member|your team|your staff)"
)
_WANTS_HUMAN = re.compile(
    rf"\b((can|could|may) i (please )?(talk|speak) (to|with) {_WHO}"
    # not "Do I need to talk to someone at VA?" (a question about the process)
    rf"|(?<!do )(?<!did )(?<!should )(?<!will )(?<!would )i('d| would)? (like|want|need) to (talk|speak) (to|with) {_WHO}"
    rf"|let me (talk|speak) (to|with) {_WHO}"
    rf"|(get|put|connect|transfer) me (through )?(to|with) {_WHO}"
    rf"|(have|can|could) {_WHO} (please )?(call|contact|phone) me"
    r"|(a )?(real person|human),? please|(talk|speak) to a (real )?(person|human)( please| now)?\s*[.!]*$)"
    # "Call me", "Please call me at 555-0100", "Can you call me back?": only as a request, at the
    # start of a sentence, so "they never call me" stays a narrative
    r"|(?:^|(?<=[.!?,;])\s*)(?:ok(?:ay)?,? |so,? |also,? )?(?:please,? |pls,? )?"
    r"(?:(?:can|could|would|will) (?:you|someone|somebody) (?:please )?)?(?:call|phone|ring) me\b",
    re.IGNORECASE,
)


def wants_human(text: str) -> bool:
    return bool(_WANTS_HUMAN.search(text))


# ----------------------------------------------------------------------------- all at once
@dataclass
class Ingested:
    clean: str  # the redacted text: the only version any model, log or subagent may see
    redacted: bool  # something was hidden (tell the veteran)
    crisis: bool
    wants_human: bool


def ingest(text: str) -> Ingested:
    clean, redacted = redact_chat(text)
    return Ingested(clean=clean, redacted=redacted, crisis=detect_crisis(clean), wants_human=wants_human(clean))
