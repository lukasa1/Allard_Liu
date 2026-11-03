"""Answer the veteran's questions during intake.

Two engines, the same contract (question -> QAResult(text, sources, handoff)):

  WebSearchQA  OpenRouter's web plugin, restricted to official domains (va.gov, ecfr.gov, ...).
               The model answers only from the search results and cites them. About $0.007 per
               search with the Exa engine (pinned), plus tokens.
  OfflineQA    a small hand-checked FAQ with official sources. Used with no API key.

Both refuse the same things and hand them to a person instead (`handoff=True`): legal advice,
predictions about this veteran's case, and anything about the firm's own policies beyond the
basics. The intake controller then tells the veteran the team will answer.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from agent.intake.controller import QAResult

DEFAULT_DOMAINS = (
    "va.gov",
    "benefits.va.gov",
    "ecfr.gov",
    "law.cornell.edu",
    "veteranscrisisline.net",
)
DEFAULT_QA_MODEL = "anthropic/claude-haiku-5.5"

# Case-specific or legal-advice questions: always a person.
_NEEDS_PERSON = re.compile(
    r"\b(will i (get|win|be approved)|what (rating|percent(age)?) will|my chances|should i|"
    r"do i qualify|am i eligible|how much will i get|is my case|can you guarantee|"
    r"what should i (do|say)|sue|lawsuit|"
    # money owed to VA (an overpayment, a debt) is case-specific: never the firm's fee answer
    r"owes? (to )?(the )?va|va (debt|overpayment)|overpa(id|yment)s?|debts?|collections?)\b",
    re.IGNORECASE,
)


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


class OfflineQA:
    engine = "offline_faq"

    def __call__(self, question: str) -> QAResult:
        if _NEEDS_PERSON.search(question):
            return QAResult(text="", handoff=True)
        low = question.lower()
        for entry in FAQ:
            if any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low) for k in entry.keywords):
                return QAResult(text=entry.answer, sources=[entry.source])
        return QAResult(text="", handoff=True)


QA_SYSTEM = """You answer a veteran's question during a law firm's intake chat, using ONLY the web \
search results you are given (official VA and federal sources). Rules:
- Two or three plain sentences. No legal jargon, no lists, no em dashes.
- General information only. Never predict this veteran's outcome, rating or eligibility, and never \
tell them what they should do. If the question asks for that, or about this firm's own policies, or \
the search results don't answer it, reply with exactly: HANDOFF
- Don't mention that you searched."""


class WebSearchQA:
    engine = "openrouter_web"

    def __init__(
        self, client=None, model: str | None = None, domains: tuple[str, ...] | None = None
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=os.environ.get("POA_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
                api_key=os.environ["OPENROUTER_API_KEY"],
                timeout=30,
                max_retries=1,
            )
        self.client = client
        self.model = model or os.environ.get("QA_MODEL", DEFAULT_QA_MODEL)
        env_domains = os.environ.get("QA_SEARCH_DOMAINS", "")
        self.domains = (
            domains
            or tuple(d.strip() for d in env_domains.split(",") if d.strip())
            or DEFAULT_DOMAINS
        )

    def __call__(self, question: str) -> QAResult:
        if _NEEDS_PERSON.search(question):
            return QAResult(text="", handoff=True)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": QA_SYSTEM},
                {"role": "user", "content": question},
            ],
            max_tokens=2000,
            # engine pinned to Exa: unset, OpenRouter uses OpenAI's native search for openai/*
            # models (different price, domain filtering not guaranteed).
            extra_body={
                "plugins": [
                    {
                        "id": "web",
                        "engine": "exa",
                        "max_results": 5,
                        "include_domains": list(self.domains),
                    }
                ]
            },
        )
        usage = _usage(resp)
        msg = resp.choices[0].message
        text = (msg.content or "").strip()
        if not text or "HANDOFF" in text:
            return QAResult(text="", handoff=True, usage=usage)
        sources = []
        for ann in getattr(msg, "annotations", None) or []:
            url = _annotation_url(ann)
            if url and url not in sources and _allowed(url, self.domains):
                sources.append(url)
        if not sources:  # an answer we can't attribute to an official page isn't given
            return QAResult(text="", handoff=True, usage=usage)
        return QAResult(text=text, sources=sources[:2], usage=usage)


def _usage(resp) -> dict:
    """Tokens and (if OpenRouter returns it) cost of one call, for the trace log."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    out = {"prompt_tokens": getattr(u, "prompt_tokens", None), "completion_tokens": getattr(u, "completion_tokens", None)}
    cost = getattr(u, "cost", None)
    if cost is not None:
        out["cost"] = cost
    return {k: v for k, v in out.items() if v is not None}


def _annotation_url(ann) -> str | None:
    if isinstance(ann, dict):
        return (ann.get("url_citation") or {}).get("url") or ann.get("url")
    citation = getattr(ann, "url_citation", None)
    if citation is not None:
        return getattr(citation, "url", None) or (
            citation.get("url") if isinstance(citation, dict) else None
        )
    return getattr(ann, "url", None)


def _allowed(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def make_qa(provider: str):
    if provider == "offline" or not os.environ.get("OPENROUTER_API_KEY"):
        return OfflineQA()
    return WebSearchQA()
