"""X5 CoPilot API client — concrete LLMClient implementation.

Uses the ``openai`` Python SDK pointed at the X5 CoPilot API 2.0
(OpenAI-compatible) via ``base_url`` + ``api_key`` from settings.

Retry logic via tenacity:
  • 429 (rate-limit) — exponential back-off with jitter
  • 5xx            — exponential back-off with jitter
  • Timeout        — retry up to max_retries

Auth errors (401/403) are NOT retried — raised immediately.
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx
import structlog
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import settings
from app.services.llm.base import LLMClient, LLMError, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Decide whether to retry the call."""
    if isinstance(exc, LLMError):
        return exc.retryable
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return True
    return False


class X5CopilotClient(LLMClient):
    """X5 CoPilot API 2.0 client (OpenAI-compatible).

    Parameters are read from ``app.core.config.settings`` by default but
    can be overridden for testing.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._base_url = base_url or settings.LLM_BASE_URL
        self._api_key = api_key or settings.API_KEY
        self._default_model = default_model or settings.LLM_MODEL
        self._timeout = timeout if timeout is not None else settings.LLM_TIMEOUT
        self._max_retries = max_retries if max_retries is not None else settings.LLM_MAX_RETRIES
        self._temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self._max_tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS

        # Optional custom CA bundle: X5 CoPilot is fronted by an internal X5
        # corporate CA (sre-vault.x5.ru) not present in the public certifi
        # bundle. When LLM_CA_BUNDLE is set we build an httpx client that
        # verifies against it — TLS verification stays ON (NFR-compliant).
        ca_bundle = settings.LLM_CA_BUNDLE
        http_client: httpx.AsyncClient | None = None
        if ca_bundle:
            ssl_ctx = ssl.create_default_context(cafile=ca_bundle)
            http_client = httpx.AsyncClient(
                verify=ssl_ctx,
                timeout=float(self._timeout),
            )

        # openai SDK client — no built-in retries (we handle via tenacity)
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=float(self._timeout),
            max_retries=0,  # let tenacity handle retries
            http_client=http_client,
        )

        logger.info(
            "x5_copilot_client_init",
            base_url=self._base_url,
            model=self._default_model,
            timeout=self._timeout,
            max_retries=self._max_retries,
            custom_ca_bundle=bool(ca_bundle),
            # NEVER log api_key (NFR-17)
        )

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat-completion request to X5 CoPilot."""
        used_model = model or self._default_model
        used_temp = temperature if temperature is not None else self._temperature
        used_max_tokens = max_tokens if max_tokens is not None else self._max_tokens

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential_jitter(initial=1, max=30, jitter=2),
            reraise=True,
        )
        async def _do_chat() -> LLMResponse:
            return await self._raw_chat(
                messages, used_model, used_temp, used_max_tokens, **kwargs
            )

        return await _do_chat()

    async def _raw_chat(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a single chat request (no retry wrapping)."""
        openai_messages = [
            {"role": m.role, "content": m.content} for m in messages
        ]

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=openai_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except AuthenticationError as exc:
            logger.error("llm_auth_error", status=exc.status_code)
            raise LLMError(
                "LLM authentication failed (check API_KEY)",
                status_code=exc.status_code,
                retryable=False,
            ) from exc
        except RateLimitError as exc:
            logger.warning("llm_rate_limit", status=exc.status_code)
            raise LLMError(
                "LLM rate limit exceeded",
                status_code=exc.status_code,
                retryable=True,
            ) from exc
        except APITimeoutError as exc:
            logger.warning("llm_timeout")
            raise LLMError(
                "LLM request timed out",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            logger.warning("llm_connection_error", detail=str(exc))
            raise LLMError(
                "LLM connection failed",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            logger.error("llm_api_error", status=exc.status_code)
            raise LLMError(
                f"LLM provider error ({exc.status_code})",
                status_code=exc.status_code,
                retryable=exc.status_code >= 500,
            ) from exc

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        logger.info(
            "llm_chat_ok",
            model=response.model,
            tokens=usage.get("total_tokens"),
            finish_reason=choice.finish_reason,
        )

        return LLMResponse(
            content=content,
            model=response.model or model,
            usage=usage,
            raw={},  # don't store raw provider response to minimize surface
        )

    # ------------------------------------------------------------------
    # embeddings (Phase 7 stub — interface satisfied)
    # ------------------------------------------------------------------

    async def embeddings(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        """Compute embeddings via X5 CoPilot (Phase 7).

        Default embedding model: x5-airun-embed-4b.
        """
        emb_model = model or "x5-airun-embed-4b"

        try:
            response = await self._client.embeddings.create(
                model=emb_model,
                input=texts,
                **kwargs,
            )
        except AuthenticationError as exc:
            raise LLMError(
                "LLM authentication failed",
                status_code=exc.status_code,
                retryable=False,
            ) from exc
        except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
            raise LLMError(
                f"LLM embeddings error: {exc}",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            raise LLMError(
                f"LLM embeddings provider error ({exc.status_code})",
                status_code=exc.status_code,
                retryable=exc.status_code >= 500,
            ) from exc

        return [item.embedding for item in response.data]
