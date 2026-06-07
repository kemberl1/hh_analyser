"""LLM client abstraction layer — Phase 6.

Provides abstract LLMClient interface (NFR-28: provider-replaceable)
and concrete X5CopilotClient implementation via openai SDK.
"""

from app.services.llm.base import LLMClient, LLMError, LLMResponse
from app.services.llm.factory import get_llm_client
from app.services.llm.x5_copilot import X5CopilotClient

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "X5CopilotClient",
    "get_llm_client",
]
