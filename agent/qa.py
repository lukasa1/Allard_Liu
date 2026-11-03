"""kb_search's engine: answer a veteran's general question from official web sources.

  WebSearchQA  OpenRouter's web plugin, restricted to official domains (va.gov, ecfr.gov, ...).
               The model answers only from the search results and cites them. About $0.007 per
               search with the Exa engine (pinned), plus tokens.

It refuses some things and hands them to a person instead (`handoff=True`): legal advice,
predictions about this veteran's case, and money owed to VA; these never reach the model. An
answer with no official source is not given either. Tests use a fixed FAQ stand-in
(tests/fake_kb.py) with the same contract.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class QAResult:
    text: str
    sources: list[str] = field(default_factory=list)
    handoff: bool = False  # True: a person on the team should answer (legal advice, case-specific)
    usage: dict[str, Any] = field(default_factory=dict)  # tokens / cost of the call, if any (trace log)


QATool = Callable[[str], QAResult]  # question -> QAResult

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


QA_SYSTEM = """You answer a veteran's question during a law firm's intake chat, using ONLY the web \
search results you are given (official VA and federal sources). Rules:
- Two or three plain sentences. No legal jargon, no lists, no em dashes.
- General information only. Never predict this veteran's outcome, rating or eligibility, and never \
tell them what they should do. If the question asks for that, or about this firm's own policies, or \
the search results don't answer it, reply with exactly: HANDOFF
- Don't mention that you searched."""


class WebSearchQA:
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

