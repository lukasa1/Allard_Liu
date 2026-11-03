"""A fixed-FAQ stand-in for kb_search's web-search engine (agent/qa.py), so no test touches the
network. Same contract (question -> QAResult) and the same hand-to-a-person rule."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.qa import _NEEDS_PERSON, QAResult


@dataclass(frozen=True)
class FaqEntry:
    keywords: tuple[str, ...]
    answer: str
    source: str


FAQ: tuple[FaqEntry, ...] = (
    FaqEntry(
        (
            "fee", "cost", "charge", "pay you", "how much do you", "percent do you", "free",
            # owing money only to the firm: "How much do I owe VA?" goes to a person (_NEEDS_PERSON)
            "owe you", "owe the firm", "owe your firm", "pay the firm", "pay your firm",
        ),
        "Accredited attorneys can only charge for work done after VA's first decision on a claim, "
        "and the fee usually comes out of past-due benefits if you win, so there's nothing to pay "
        "up front. Our team will go over the fee agreement with you before anything is signed.",
        "https://www.va.gov/ogc/accreditation.asp",
    ),
    FaqEntry(
        ("how long", "timeline", "take", "wait"),
        "VA publishes its current average processing times for disability claims, and they change "
        "over time. Our team can tell you what to expect for your situation.",
        "https://www.va.gov/disability/after-you-file-claim/",
    ),
    FaqEntry(
        ("c-file", "c file", "claims file", "my file", "records"),
        "Your claims file (C-file) is VA's full record of your claims. Once you sign the form "
        "appointing our attorney, the firm can request it so we can review your history.",
        "https://www.va.gov/records/",
    ),
    FaqEntry(
        ("21-22a", "power of attorney", "poa", "representative", "what am i signing"),
        "VA Form 21-22a appoints an individual attorney or agent to represent you with VA. It lets "
        "them see your VA records and act for you on your claims. You can revoke it at any time.",
        "https://www.va.gov/find-forms/about-form-21-22a/",
    ),
    FaqEntry(
        ("intent to file", "effective date", "0966"),
        "An intent to file holds your potential start date for benefits for up to a year while you "
        "gather evidence, so you don't lose back pay.",
        "https://www.va.gov/resources/your-intent-to-file-a-va-claim/",
    ),
    FaqEntry(
        ("appeal", "higher-level review", "supplemental", "board", "denied"),
        "If you disagree with a VA decision you generally have one year from the decision letter to "
        "choose a review: a Supplemental Claim, a Higher-Level Review, or a Board appeal.",
        "https://www.va.gov/decision-reviews/",
    ),
    FaqEntry(
        ("crisis", "988", "suicide", "hotline"),
        "The Veterans Crisis Line is free and confidential, 24/7: dial 988 and press 1, or text "
        "838255.",
        "https://www.veteranscrisisline.net/",
    ),
)


class FaqKB:

    def __call__(self, question: str) -> QAResult:
        if _NEEDS_PERSON.search(question):
            return QAResult(text="", handoff=True)
        low = question.lower()
        for entry in FAQ:
            if any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low) for k in entry.keywords):
                return QAResult(text=entry.answer, sources=[entry.source])
        return QAResult(text="", handoff=True)


