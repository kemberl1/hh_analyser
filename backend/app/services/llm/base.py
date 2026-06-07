"""Abstract LLM client interface — NFR-28 (provider-replaceable).

Business logic depends ONLY on LLMClient; concrete provider implementations
are injected via factory.  Phase 7 (resume analyser) will reuse this same
interface.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMMessage:
    """Single message in the chat conversation."""
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """Normalised response from any LLM provider."""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMError(Exception):
    """Base exception for LLM layer errors.

    Attributes:
        status_code: HTTP status from the provider if applicable.
        retryable: whether the caller should consider retrying.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class LLMClient(abc.ABC):
    """Abstract LLM client (NFR-28).

    Concrete implementations:
      • X5CopilotClient (Phase 6) — openai SDK → X5 CoPilot API
      • Future providers: swap implementation without touching business logic.

    Methods
    -------
    chat(messages, **kwargs) -> LLMResponse
        Send a chat-completion request.
    embeddings(texts, **kwargs) -> list[list[float]]
        (Phase 7) Compute text embeddings.
    """

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a chat completion.

        Parameters
        ----------
        messages : ordered conversation history.
        model : override default model for this request.
        temperature : sampling temperature.
        max_tokens : max tokens in response.

        Returns
        -------
        LLMResponse with generated text.

        Raises
        ------
        LLMError on provider failures (timeouts, 4xx/5xx, auth).
        """

    @abc.abstractmethod
    async def embeddings(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        """Compute embeddings for a list of texts (Phase 7).

        Returns
        -------
        List of embedding vectors (one per input text).

        Raises
        ------
        LLMError on provider failures.
        """
