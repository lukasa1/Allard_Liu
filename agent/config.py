"""Runtime settings, read from the environment (and the repo's .env, which is gitignored).

Everything has an offline default, so the demo and the tests run with no keys at all:

  INTAKE_PROVIDER   offline | dspy. Default: dspy when OPENROUTER_API_KEY is set, else offline.
  DSPY_MODEL        model for the agents (default openrouter/openai/gpt-6-luna)
  DSPY_SIM_MODEL    model for the simulated veteran in the eval (default: DSPY_MODEL)
  DSPY_CACHE        "0" disables DSPy's response cache (use for repeated trials / pass^k)
  LIGHTHOUSE_MODE   stub | recorded | sandbox (default stub; see agent/lighthouse)
  VA_TOKEN_ICN      sandbox only: ICN of the access tokens' user; other case ICNs are refused
  QA_MODEL          OpenRouter model for web-search QA (default openai/gpt-6-luna)
  QA_SEARCH_DOMAINS comma-separated domains web search is restricted to
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DSPY_MODEL = "openrouter/openai/gpt-6-luna"
PROVIDERS = ("offline", "dspy")


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


def make_lm(role: str = "agent"):
    import dspy

    model = None
    if role == "simulator":
        model = os.environ.get("DSPY_SIM_MODEL")
    model = model or os.environ.get("DSPY_MODEL") or DEFAULT_DSPY_MODEL
    cache = os.environ.get("DSPY_CACHE", "1") != "0"
    # temperature stays unset: current reasoning models on OpenRouter reject sampling parameters.
    return dspy.LM(model, max_tokens=16000, cache=cache)


def data_dir() -> Path:
    return Path(os.environ.get("POA_DATA_DIR", ".data"))
