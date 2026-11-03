"""Runtime settings, read from the environment (and the repo's .env, which is gitignored).

  DSPY_MODEL        model for every agent (default openrouter/anthropic/claude-haiku-5.5)
  DSPY_SIM_MODEL    model for the simulated veteran in the eval (default: DSPY_MODEL)
  REASONING_EFFORT  low | medium | high | none (default low; L9). Passed to LiteLLM as
                    `reasoning_effort`; whether OpenRouter honours it for this slug is checked in
                    the first live smoke test.
  DSPY_CACHE        "0" disables DSPy's response cache (use for repeated trials / pass^k)
  QA_MODEL          OpenRouter model for kb_search (default anthropic/claude-haiku-5.5)
  QA_SEARCH_DOMAINS comma-separated domains web search is restricted to

Legacy (the pre-rebuild session, until later build steps replace it):
  INTAKE_PROVIDER   offline | dspy. Default: dspy when OPENROUTER_API_KEY is set, else offline.
  LIGHTHOUSE_MODE   stub | recorded | sandbox (default stub; see agent/lighthouse)
  VA_TOKEN_ICN      sandbox only: ICN of the access tokens' user; other case ICNs are refused
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DSPY_MODEL = "openrouter/anthropic/claude-haiku-5.5"
PROVIDERS = ("offline", "dspy")

# USD per million tokens (input, output). LiteLLM may not price new slugs, so cost is computed here.
PRICES: dict[str, tuple[float, float]] = {
    "openrouter/anthropic/claude-haiku-5.5": (0.10, 0.50),
    "anthropic/claude-haiku-5.5": (0.10, 0.50),
}


def load_env() -> None:
    """Load REPO_ROOT/.env without overriding variables already set in the shell."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a dependency
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def default_provider() -> str:
    explicit = os.environ.get("INTAKE_PROVIDER", "").strip().lower()
    if explicit:
        if explicit not in PROVIDERS:
            raise SystemExit(f"INTAKE_PROVIDER must be one of {PROVIDERS}, got {explicit!r}")
        return explicit
    return "dspy" if os.environ.get("OPENROUTER_API_KEY") else "offline"


def reasoning_effort() -> str | None:
    effort = os.environ.get("REASONING_EFFORT", "low").strip().lower()
    return None if effort in ("", "none") else effort


def make_lm(role: str = "agent"):
    import dspy

    model = None
    if role == "simulator":
        model = os.environ.get("DSPY_SIM_MODEL")
    model = model or os.environ.get("DSPY_MODEL") or DEFAULT_DSPY_MODEL
    cache = os.environ.get("DSPY_CACHE", "1") != "0"
    kwargs = {}
    if effort := reasoning_effort():
        kwargs["reasoning_effort"] = effort
    # temperature stays unset: reasoning models on OpenRouter reject sampling parameters.
    return dspy.LM(model, max_tokens=16000, cache=cache, **kwargs)


def data_dir() -> Path:
    return Path(os.environ.get("POA_DATA_DIR", ".data"))
