"""Settings. Keys come from .env: first this repo's folder, then the folder above it."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Order matters: load_dotenv(override=False) keeps the first value it sees.
for _candidate in (ROOT / ".env", ROOT.parent / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Settings:
    # ---- keys (the only two names the course .env uses) ----
    portkey_api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

    # ---- model routing. Course key -> Portkey + gpt-5.6-luna. ----
    # If your class notebook calls Portkey differently (virtual key, config id,
    # provider slug), set the optional PORTKEY_* variables below. All HTTP details
    # live in app/llm.py so there is exactly one place to change.
    model = os.getenv("LLM_MODEL", "gpt-5.6-luna").strip()
    portkey_base_url = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")
    portkey_provider = os.getenv("PORTKEY_PROVIDER", "").strip()
    portkey_virtual_key = os.getenv("PORTKEY_VIRTUAL_KEY", "").strip()
    portkey_config = os.getenv("PORTKEY_CONFIG", "").strip()
    openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    mock = os.getenv("MOCK_LLM", "").strip() == "1"   # offline demo/test mode, clearly labelled in the UI
    mode = os.getenv("AGENT_MODE", "agentic").strip()  # "agentic" or "lean"

    # ---- safety limits (overspending, loops, abuse) ----
    max_input_chars = _int("MAX_INPUT_CHARS", 2000)
    max_tokens_per_run = _int("BUDGET_RUN_TOKENS", 30_000)
    max_tokens_per_session_day = _int("BUDGET_SESSION_DAY_TOKENS", 200_000)
    max_tokens_global_day = _int("BUDGET_GLOBAL_DAY_TOKENS", 2_000_000)
    max_runs_per_minute = _int("BUDGET_RUNS_PER_MINUTE", 6)
    max_llm_calls_per_run = _int("MAX_LLM_CALLS_PER_RUN", 12)
    max_agent_steps = _int("MAX_AGENT_STEPS", 6)       # analyst tool-loop rounds
    max_tool_calls = _int("MAX_TOOL_CALLS", 8)
    run_timeout_s = _int("RUN_TIMEOUT_S", 90)
    request_timeout_s = _int("REQUEST_TIMEOUT_S", 45)

    port = _int("PORT", 8000)

    @classmethod
    def provider(cls) -> str:
        if cls.mock:
            return "mock"
        if cls.portkey_api_key:
            return "portkey"
        if cls.openai_api_key:
            return "openai"
        return "none"


settings = Settings()
