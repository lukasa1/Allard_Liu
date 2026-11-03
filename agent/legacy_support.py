"""LEGACY (until step 8): the regex support of the old CaseSession; the new agent is agent/support/.

Customer support subagent: answers the veteran when no other subagent is talking with them.

Routing (the session does it, following the architecture): while the intake subagent or the POA
step is working the case, it answers the veteran's questions itself, since it already has the
conversation. Once the case is parked (with the attorney, handed to staff, or closed), messages come
here. Support is READ-ONLY: it gets a snapshot of the case, never the case itself, so it can't move
a stage, file or sign anything. Whatever would change the case comes back as a flag, and the
session (the orchestrator's side) turns each flag into a staff task.

What it does with one message, all deterministic except the QA tool:
  flags     new condition, withdraw / end representation, contact change, complaint, wants a person
  status    "any news on my file?" -> plain words from the snapshot; never a promised VA date
  QA        other questions -> the same QA tool as intake (web search on official sites, or the
            offline FAQ); legal advice and case predictions go to a person
  otherwise "thanks, a person will read this" (and the session makes a task)

Crisis language never reaches this module: the session checks it first in every phase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent.case import CaseState
from agent.ingest import _WANTS_HUMAN, WITHDRAW
from agent.intake.controller import QAResult, QATool

FLAG_KINDS = ("new_condition", "withdraw", "contact_change", "complaint", "wants_human")
# Every flag needs an object: "add my wife as a dependent" is not a new condition, "cancel the C&P
# exam" is not a withdrawal, "I've moved on from that job" is not a new address.
_NOT_A_CONDITION = (
    r"(?!\s*(?:(?:my|a|an|the|our|his|her) )?(?:new )?(?:wife|husband|spouse|partner|fianc\w*|child|children|kids?|sons?|daughters?|dependents?"
    r"|mom|mother|dad|father|parents?|family|new (?:email|address|phone|number)|email|address|phone"
    r"|number|name|bank|account|direct deposit|contact|appointment|exam)\b)"
)
_FLAGS: dict[str, re.Pattern] = {
    "new_condition": re.compile(
        rf"\b(also (want|like|need|wanna) to (claim|file( for)?|add|include){_NOT_A_CONDITION}"
        r"|(add|include) (a |another |one more |my )?(new )?(condition|claim|issue)s?\b"
        r"|another (condition|claim|issue|disability)"
        r"|forgot to (mention|tell you|add)"
        rf"|can (i|we|you) (also )?(add|include|claim|file for)\b{_NOT_A_CONDITION}"
        rf"|(?:want|like|need) to (add|claim|file for){_NOT_A_CONDITION} (my |a )?\w+ (too|as well)"
        rf"|(claim|file) (for )?{_NOT_A_CONDITION}my \w+( \w+)? (too|as well)"
        # a new or worse condition since intake
        r"|(have|got|developed|there'?s|found out about) (a |another |some )?new (condition|diagnosis|problem"
        r"|health (issue|problem)|issue|injury|illness|disability)"
        r"|\b(i|i'?ve|i have|i was|i got|i'?ve been|i just got|i recently got|just|recently)( just| recently| been)?"
        r" (been |got |was |were )?diagnosed (with|as)"
        r"|\bmy (\w+ ){1,3}(has |have |is |are |'s )?(gotten|got|getting|become|grown|been getting) (\w+ )?worse"
        r"|\bmy (\w+ ){1,3}(has |have |is |'s )?worsen(ed|ing))",
        re.IGNORECASE,
    ),
    "withdraw": WITHDRAW,
    "contact_change": re.compile(
        r"\b(i('ve| have)? (just |recently )?moved(?! (on|up|forward|over|past|ahead|away from (it|that)|in with)\b)"
        r"|my new (address|phone|number|email|cell)|new (address|phone number|email address|cell number)"
        r"|changed? my (address|phone|number|email)|(update|change) my (address|phone|number|email|contact))\b",
        re.IGNORECASE,
    ),
    # About us or the service, not about a doctor, a divorce or a spouse.
    "complaint": re.compile(
        r"\b((file|make|lodge|submit|have) a complaint|i('m| am)? (want to |need to |wanna )?complain(ing)?\b"
        r"|complaint (about|against|regarding)"
        r"|(unhappy|not happy|frustrat\w*|angry|upset|disappointed|fed up|annoyed|mad|dissatisfied)"
        r"( \w+){0,2} (with|about|at|by|over) (you\b|your\b|the firm|this firm|the service|the process|how (you|this|things|my case|my claim)"
        r"|this\b|the wait|the delay|no one|nobody|the lack|the communication|my (lawyer|attorney|case|claim|file))"
        r"|(this|that|you|you guys|your (service|team|firm|staff|communication)|the (service|wait|delay|communication"
        r"|process|firm)) (is|are|was|were|'s|'re|has been|have been) ((so|really|just|absolutely|completely|totally"
        r"|pretty|very) )?(terrible|unacceptable|ridiculous|awful|horrible|a joke|useless)"
        r"|^\s*(this is )?(ridiculous|unacceptable|terrible|awful)\W*$"
        r"|(nobody|no one|no-one) (has )?(called|contacted|answered|gotten back)"
        r"|haven'?t heard (back )?from (anyone|anybody|you)|waste of (my )?time)",
        re.IGNORECASE,
    ),
}
# "What's going on with my case?": answered from the snapshot. Every alternative needs the case as
# its object, so "Where is the nearest VA hospital?" and "my progress note" are not status.
_CASE_NOUN = (
    r"(case|file|c-file|claims? file|claim|application|appeal|paperwork|forms?|records|documents?|21-22a"
    r"|poa|power of attorney|intent to file|itf)"
)
_STATUS = re.compile(
    r"\b(status|any updates?|updates? (on|about|regarding) (my|the|our) " + _CASE_NOUN + r"|(an|for an?) update\s*[?.!]*$"
    r"|any news|news (on|about)|any word|heard (back|anything)|(any|making|made) progress|progress (on|with)"
    r"|where (is|are|'s) (my|our|the) " + _CASE_NOUN + r"\b|where (do|does) (we|things|my \w+) stand|where are we\b"
    r"|what('?s| is| happens) next|next steps?|still (waiting|pending|open)"
    r"|how('?s| is) my (case|claim|file) (going|doing|coming)|what('?s| is) going on with my"
    r"|why (was|is|did) my (case|claim|file)"
    r"|when (will|do|would|should|can|might) (i|we) (hear|find out|know)\b)"
    r"|^\s*((and|so|also|ok(ay)?),? )?(did|has|have|had) (you|va|the va|the attorney|my attorney|our attorney"
    r"|the lawyer|my lawyer|anyone|someone|anybody|the firm|your team|the team)\b"
    r"(.*\b(my|the|our) " + _CASE_NOUN + r"\b|.*\byet\b)"
    r"|^\s*((and|so|also|ok(ay)?),? )?(is|was|has|have|did) (my|our|the) " + _CASE_NOUN + r"\b.*\b(yet|already)\b"
    r"|^\s*((and|so|also|ok(ay)?),? )?(is|was) (my|our) " + _CASE_NOUN + r" (approved|denied|done|filed|submitted"
    r"|accepted|granted|finished|ready|in|through)\b",
    re.IGNORECASE,
)
# A question about THIS case ("Have you requested my C-file?", "Is my power of attorney valid?"):
# a general FAQ answer would read like a case update, so a person answers it.
_ABOUT_THIS_CASE = re.compile(
    r"\b(my|yet|you|your)\b.*\b" + _CASE_NOUN + r"\b|\b" + _CASE_NOUN + r"\b.*\b(my|yet|you)\b"
    r"|\bmy (effective date|rating|decision|exam|c&p)\b",
    re.IGNORECASE,
)
_GENERAL = re.compile(r"^\s*(what|how) (is|are|does|do) (a|an|the)\b(?!.*\bmy\b)", re.IGNORECASE)
_QUESTION_START = re.compile(
    r"^(what|why|how|when|where|who|which|can|could|do|does|did|is|are|will|would|should|may)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[?.!])\s+|\n+")

ACK = {
    # What happens next is the orchestrator's call (reopen intake, or the attorney reviews it first),
    # and its action tells the veteran; this only acknowledges.
    "new_condition": "Thanks for telling me. I've noted that you'd like to add that to your claim.",
    "withdraw": "I've passed your request to our team. A person will contact you to confirm before anything about your representation changes.",
    "contact_change": "Thanks for letting us know. I've asked our team to update your contact details; they'll confirm the change with you. Please don't type ID numbers here.",
    "complaint": "I'm sorry about that. I've passed your message to a member of our team, who will contact you.",
    "wants_human": "Of course. I've asked a member of our team to contact you.",
}
FOR_A_PERSON = "Thanks for your message. I've passed it to our team, and someone will follow up with you."
NO_DATES = "I can't predict VA's timing, but we'll message you as soon as anything changes."
# A flagged message can also carry a question the flag doesn't answer ("I moved to Tulsa. Will I get
# 70%?"): the reply must say the question went to the team too, not only acknowledge the flag.
ALSO_ASKED = "I've also passed your question to our team, and someone will answer it."


@dataclass
class SupportResult:
    text: str
    flags: list[str] = field(default_factory=list)  # FLAG_KINDS found in the message
    answered: list[str] = field(default_factory=list)  # status | qa
    # True whenever a person must read the message: nothing answered it, or some question in it
    # went unanswered (flags or not), so a person always gets a task for an unanswered question.
    for_a_person: bool = False
    unanswered: list[str] = field(default_factory=list)  # the question sentences nobody answered


def snapshot(case: CaseState) -> dict[str, Any]:
    """What support may see: a copy of the facts that matter to the veteran, never the case object,
    the C-file, the face note or another subagent's transcript."""
    o = case.intake_outcome
    return {
        "phase": case.phase,
        "decision": o.decision if o else None,
        "first_name": case.intake.first_name if case.intake else None,
        "poa_signed": case.poa_signed,
        "poa_submitted": case.poa_submission is not None,
        "poa_status": (case.poa_submission or {}).get("status"),
        "itf_date": (case.itf or {}).get("date"),
        "face_note_ready": case.face_note is not None,
        "cfile_requested": bool(case.cfile_documents) or case.cfile_manual,
        "cfile_received": bool(case.cfile_documents),
        "poa_countersigned": bool(
            getattr(case, "poa_countersigned", False) or getattr(case, "poa_countersigned_at", None)
        ),
    }


def status_text(snap: dict[str, Any]) -> str:
    """The case's status in plain words (the 'case-status' skill), from the snapshot only."""
    phase = snap["phase"]
    if phase == "closed":
        if snap["decision"] == "rated_100":
            return ("Your case with us is closed: since you're already rated at 100%, there's no "
                    "increase for us to pursue right now. Someone will reach out if that changes.")  # fmt: skip
        return "Your case with us is closed. If something has changed, tell me and I'll pass it to our team."
    if phase == "human_handoff":
        return "A member of our team is handling your case personally and will contact you directly. " + NO_DATES
    done = []
    if snap["poa_signed"]:
        done.append("you signed VA Form 21-22a" + (" and we sent it to VA" if snap["poa_submitted"] else ""))
    if snap["itf_date"]:
        done.append(f"we filed an intent to file on {snap['itf_date']}, which protects your start date for benefits")
    so_far = ("So far, " + "; ".join(done) + ". ") if done else ""
    if phase == "attorney_review":
        return (f"{so_far}Your file is now with our attorney for review, and someone from our team "
                f"will contact you about next steps. {NO_DATES}")  # fmt: skip
    if phase == "attorney_signoff":
        if snap.get("poa_submitted"):
            nxt = "Our team is preparing your case."
        elif snap.get("poa_countersigned"):
            nxt = "Our attorney has countersigned the form, and our team will file it with VA next."
        else:
            nxt = ("Next, our attorney countersigns the form, and then our team files it with VA. "
                   "That lets us act for you on your claims.")  # fmt: skip
        return f"{so_far}{nxt} {NO_DATES}"
    if phase == "case_prep":
        if snap.get("cfile_received"):
            nxt = "We've received your VA claims file, and our team is reading it to prepare your case."
        elif snap.get("cfile_requested"):
            nxt = "We've asked VA for your claims file. When it arrives, our team will read it to prepare your case."
        else:
            nxt = "Our team is preparing your case and will ask VA for your claims file."
        return f"{so_far}{nxt} {NO_DATES}"
    return f"{so_far}Our team is working on your case. {NO_DATES}"


def find_flags(text: str) -> list[str]:
    found = [k for k, rx in _FLAGS.items() if rx.search(text)]
    if _WANTS_HUMAN.search(text):
        found.append("wants_human")
    return found


def _about_this_case(sentence: str) -> bool:
    """A question about this case's own documents or progress: the QA tool only knows general facts,
    so its answer would read like a case update ("Have you requested my C-file?")."""
    return bool(_ABOUT_THIS_CASE.search(sentence)) and not _GENERAL.match(sentence)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def _is_question(sentence: str) -> bool:
    return sentence.endswith("?") or bool(_QUESTION_START.match(sentence))


class SupportAgent:
    def __init__(self, qa: QATool | None = None) -> None:
        self.qa = qa

    def handle(self, snap: dict[str, Any], text: str) -> SupportResult:
        flags = find_flags(text)
        parts: list[str] = [ACK[f] for f in flags]
        answered: list[str] = []
        unanswered: list[str] = []
        status_given = False
        for sentence in _sentences(text):
            if _STATUS.search(sentence):
                if not status_given:
                    parts.append(status_text(snap))
                    answered.append("status")
                    status_given = True
                continue
            if not _is_question(sentence) or flags and self._is_flag_sentence(sentence):
                continue
            reply = None if _about_this_case(sentence) else self._qa(sentence)
            if reply is None:
                unanswered.append(sentence)
            else:
                parts.append(reply)
                answered.append("qa")
        # A person reads the message when any question in it went unanswered, flags or not (the
        # session makes a task from for_a_person; a flag's own task wouldn't mention the question),
        # and when nothing at all answered it (no flag, no status, no QA).
        for_a_person = bool(unanswered) or not (flags or answered)
        if for_a_person:
            parts.append(ALSO_ASKED if flags or answered else FOR_A_PERSON)
        name = snap.get("first_name")
        if name and parts and not flags and answered and not for_a_person:
            parts[0] = f"Hi {name}. {parts[0]}"
        return SupportResult(
            text=" ".join(parts), flags=flags, answered=answered, for_a_person=for_a_person, unanswered=unanswered
        )

    @staticmethod
    def _is_flag_sentence(sentence: str) -> bool:
        return bool(find_flags(sentence))

    def _qa(self, question: str) -> str | None:
        if self.qa is None:
            return None
        try:
            result: QAResult = self.qa(question)
        except Exception:  # QA is a convenience: a failure means a person answers
            return None
        if result.handoff or not result.text:
            return None
        source = f" (Source: {result.sources[0]})" if result.sources else ""
        return f"{result.text}{source}"
