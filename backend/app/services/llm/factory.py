"""LLM client factory — returns the configured LLMClient singleton.

If LLM_ENABLED is False or API_KEY is empty, returns None.
Business logic must handle None gracefully (graceful degradation).
"""

from __future__ import annotations

import structlog

from app.core.config import settings
from app.services.llm.base import LLMClient

logger = structlog.get_logger(__name__)

_instance: LLMClient | None = None
_initialised: bool = False


def get_llm_client() -> LLMClient | None:
    """Return the configured LLMClient or None (LLM disabled / no key).

    Lazy singleton: created on first call, reused afterwards.
    Thread-safe enough for async single-worker FastAPI.
    """
    global _instance, _initialised

    if _initialised:
        return _instance

    _initialised = True

    if not settings.LLM_ENABLED:
        logger.info("llm_disabled", reason="LLM_ENABLED=false")
        return None

    if not settings.API_KEY or settings.API_KEY == "your-api-key-here":
        logger.warning("llm_disabled", reason="API_KEY not configured")
        return None

    # Import here to avoid hard dependency on openai when LLM is disabled
    from app.services.llm.x5_copilot import X5CopilotClient

    _instance = X5CopilotClient()
    return _instance


def reset_llm_client() -> None:
    """Reset singleton (useful in tests)."""
    global _instance, _initialised
    _instance = None
    _initialised = False
