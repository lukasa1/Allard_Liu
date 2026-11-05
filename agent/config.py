"""Runtime settings, read from the environment (and the repo's .env, which is gitignored).

  DSPY_MODEL        model for every agent (default openrouter/anthropic/claude-haiku-5.5)
  DSPY_SIM_MODEL    model for the simulated veteran in the eval (default: DSPY_MODEL)
  REASONING_EFFORT  low | medium | high | none (default low). Passed to LiteLLM as
                    `reasoning_effort` (OpenRouter may ignore it for some slugs).
  DSPY_CACHE        "0" disables DSPy's response cache (use for repeated trials / pass^k)
  QA_MODEL          OpenRouter model for kb_search (default anthropic/claude-haiku-5.5)
  QA_SEARCH_DOMAINS comma-separated domains web search is restricted to
  POA_DATA_DIR      where cases, traces, the vault and PDFs are kept (default .data)
  LM_TIMEOUT_S      per model call, in seconds (default 120): a hung call can't hold a turn
                    past its limit for long (the turn's own limit is checked at each tool call)
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DSPY_MODEL = "openrouter/anthropic/claude-haiku-5.5"

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
    timeout = float(os.environ.get("LM_TIMEOUT_S", "120"))
    # A ReAct step is a few hundred tokens; the cap stops a runaway output (one call can
    # otherwise run to 16,000 tokens and close to a minute).
    return dspy.LM(model, max_tokens=4000, cache=cache, timeout=timeout, **kwargs)


def data_dir() -> Path:
    return Path(os.environ.get("POA_DATA_DIR", ".data"))
