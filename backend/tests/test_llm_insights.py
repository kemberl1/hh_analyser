"""Tests for Phase 6 — LLM market insights.

All LLM calls are MOCKED (no real X5 CoPilot API calls in tests).
Tests cover:
  1. LLMClient abstraction & X5CopilotClient
  2. Market insights service (context building, prompt, caching)
  3. NFR-16: only aggregates in context, no PII
  4. Insights endpoint (envelope structure, disabled mode, error handling)
  5. Factory behaviour (enabled/disabled)
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.insights import InsightBasedOn, InsightData, InsightMeta, MarketInsightResponse
from app.services.llm.base import LLMClient, LLMError, LLMMessage, LLMResponse
from app.services.llm.factory import get_llm_client, reset_llm_client
from app.services.market_insights import (
    _extract_highlights,
    build_market_context,
    build_prompt,
    clear_cache,
    generate_market_insight,
    get_cached_insight,
    set_cached_insight,
)


# ---------------------------------------------------------------------------
# Helpers — mock LLM client
# ---------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """In-memory mock LLM client for testing."""

    def __init__(self, response_text: str = "Тест-ответ.", usage: dict | None = None):
        self._response_text = response_text
        self._usage = usage or {"prompt_tokens": 100,
                                "completion_tokens": 50, "total_tokens": 150}
        self.chat_calls: list[dict] = []
        self.embeddings_calls: list[dict] = []

    async def chat(self, messages, *, model=None, temperature=None, max_tokens=None, **kwargs):
        self.chat_calls.append({
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return LLMResponse(
            content=self._response_text,
            model=model or "test-model",
            usage=self._usage,
        )

    async def embeddings(self, texts, *, model=None, **kwargs):
        self.embeddings_calls.append({"texts": texts, "model": model})
        return [[0.1, 0.2, 0.3] for _ in texts]


class FailingLLMClient(LLMClient):
    """LLM client that always raises LLMError."""

    async def chat(self, messages, **kwargs):
        raise LLMError("Provider unavailable", status_code=503, retryable=True)

    async def embeddings(self, texts, **kwargs):
        raise LLMError("Provider unavailable", status_code=503, retryable=True)


# ---------------------------------------------------------------------------
# 1. LLMClient abstraction tests
# ---------------------------------------------------------------------------

class TestLLMClientAbstraction:
    """Test the abstract LLMClient interface works with mock."""

    @pytest.mark.asyncio
    async def test_mock_chat_returns_response(self):
        client = MockLLMClient(response_text="Hello world")
        messages = [LLMMessage(role="user", content="Say hello")]
        response = await client.chat(messages)
        assert isinstance(response, LLMResponse)
        assert response.content == "Hello world"
        assert response.model == "test-model"
        assert response.usage["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_mock_chat_records_calls(self):
        client = MockLLMClient()
        msgs = [LLMMessage(role="system", content="sys"),
                LLMMessage(role="user", content="hi")]
        await client.chat(msgs, model="my-model", temperature=0.5)
        assert len(client.chat_calls) == 1
        assert client.chat_calls[0]["model"] == "my-model"
        assert client.chat_calls[0]["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_mock_embeddings(self):
        client = MockLLMClient()
        result = await client.embeddings(["text1", "text2"])
        assert len(result) == 2
        assert len(result[0]) == 3

    @pytest.mark.asyncio
    async def test_failing_client_raises_llm_error(self):
        client = FailingLLMClient()
        with pytest.raises(LLMError) as exc_info:
            await client.chat([LLMMessage(role="user", content="test")])
        assert exc_info.value.status_code == 503
        assert exc_info.value.retryable is True


# ---------------------------------------------------------------------------
# 2. LLMError tests
# ---------------------------------------------------------------------------

class TestLLMError:
    def test_error_attributes(self):
        err = LLMError("test", status_code=429, retryable=True)
        assert str(err) == "test"
        assert err.status_code == 429
        assert err.retryable is True

    def test_error_defaults(self):
        err = LLMError("default")
        assert err.status_code is None
        assert err.retryable is False


# ---------------------------------------------------------------------------
# 3. Market context builder — NFR-16 (no PII, only aggregates)
# ---------------------------------------------------------------------------

class TestMarketContext:
    """Verify that build_market_context returns only anonymised aggregates."""

    @pytest.mark.asyncio
    async def test_context_contains_only_aggregates(self):
        """Context must have only aggregate keys — no raw vacancy data, no PII."""
        # Mock database session with aggregate returns
        session = AsyncMock()

        with patch("app.services.market_insights.compute_salary_metrics") as m_sal, \
                patch("app.services.market_insights.compute_skills_metrics") as m_sk, \
                patch("app.services.market_insights.compute_employers_metrics") as m_emp, \
                patch("app.services.market_insights.compute_demand_metrics") as m_dem, \
                patch("app.services.market_insights.compute_distribution") as m_dist:

            m_sal.return_value = {
                "count": 100, "total_count": 150,
                "median": 200000, "mean": 210000,
                "min": 80000, "max": 500000,
                "percentiles": {"p10": 100000, "p25": 150000, "p50": 200000, "p75": 260000, "p90": 350000},
                "salary_disclosure_rate": 0.67,
            }
            m_sk.return_value = {
                "skills": [
                    {"skill": "React", "canonical": "react",
                        "count": 80, "share": 0.8},
                    {"skill": "TypeScript", "canonical": "typescript",
                        "count": 70, "share": 0.7},
                ],
            }
            m_emp.return_value = {
                "employers": [
                    {"employer_id": 1, "name": "Yandex",
                        "count": 20, "share": 0.13},
                ],
            }
            m_dem.return_value = {
                "points": [
                    {"period_start": "2026-05-01", "count": 100, "growth": 0.05},
                ],
            }
            m_dist.return_value = {
                "distribution": [
                    {"key": "junior", "label": "Junior", "count": 30, "share": 0.2},
                    {"key": "middle", "label": "Middle",
                        "count": 70, "share": 0.47},
                    {"key": "senior", "label": "Senior",
                        "count": 50, "share": 0.33},
                ],
            }

            context = await build_market_context(session, grade_label="all")

        # Verify ONLY expected aggregate keys
        allowed_keys = {
            "grade_filter", "date_range", "salary", "top_skills",
            "top_employers", "demand_trend", "grade_distribution",
            "format_distribution",
        }
        assert set(context.keys()) == allowed_keys

        # Verify NO PII-like fields
        ctx_str = str(context)
        # No email, phone, personal names in context
        assert "email" not in ctx_str.lower()
        assert "phone" not in ctx_str.lower()
        assert "hh_vacancy_id" not in ctx_str.lower()
        assert "raw_html" not in ctx_str.lower()
        assert "raw_payload" not in ctx_str.lower()

        # Context contains aggregated values
        assert context["salary"]["median"] == 200000
        assert context["salary"]["sample_size"] == 100
        assert len(context["top_skills"]) == 2
        assert context["top_skills"][0]["name"] == "React"

    @pytest.mark.asyncio
    async def test_context_employer_has_no_id(self):
        """Employer entries in context must NOT contain employer_id (PII-adjacent)."""
        session = AsyncMock()

        with patch("app.services.market_insights.compute_salary_metrics") as m_sal, \
                patch("app.services.market_insights.compute_skills_metrics") as m_sk, \
                patch("app.services.market_insights.compute_employers_metrics") as m_emp, \
                patch("app.services.market_insights.compute_demand_metrics") as m_dem, \
                patch("app.services.market_insights.compute_distribution") as m_dist:

            m_sal.return_value = {"count": 0, "total_count": 0, "median": None, "mean": None,
                                  "min": None, "max": None, "percentiles": {}, "salary_disclosure_rate": None}
            m_sk.return_value = {"skills": []}
            m_emp.return_value = {"employers": [
                {"employer_id": 999, "name": "Test", "count": 5, "share": 0.1}]}
            m_dem.return_value = {"points": []}
            m_dist.return_value = {"distribution": []}

            context = await build_market_context(session)

        # Employer entries should have name, count, share — NOT employer_id
        for emp in context["top_employers"]:
            assert "employer_id" not in emp
            assert "name" in emp
            assert "count" in emp
            assert "share" in emp


# ---------------------------------------------------------------------------
# 4. Prompt builder tests
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_build_prompt_returns_messages(self):
        context = {
            "grade_filter": "all",
            "salary": {"median": 200000},
            "top_skills": [{"name": "React", "share": 0.8}],
        }
        messages = build_prompt(context)
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert "200000" in messages[1].content  # salary data is in the prompt
        assert "React" in messages[1].content

    def test_prompt_system_message_is_russian(self):
        messages = build_prompt({"grade_filter": "all"})
        # System prompt should mention Frontend market analysis in Russian
        assert "Frontend" in messages[0].content or "фронтенд" in messages[0].content.lower(
        )
        assert "навыки" in messages[0].content.lower(
        ) or "навык" in messages[0].content.lower()


# ---------------------------------------------------------------------------
# 5. Highlights extraction
# ---------------------------------------------------------------------------

class TestHighlights:
    def test_extract_bullet_points(self):
        text = """Обзор:
- React остаётся лидером
- TypeScript обязателен
• Рост удалёнки
* Зарплаты растут
1. Изучайте Next.js
2) Добавьте тесты
"""
        highlights = _extract_highlights(text)
        assert len(highlights) >= 4
        assert "React остаётся лидером" in highlights

    def test_extract_empty(self):
        assert _extract_highlights("Просто текст без пунктов") == []

    def test_extract_capped_at_10(self):
        lines = "\n".join(f"- пункт {i}" for i in range(20))
        highlights = _extract_highlights(lines)
        assert len(highlights) <= 10


# ---------------------------------------------------------------------------
# 6. Cache tests
# ---------------------------------------------------------------------------

class TestInsightCache:
    def setup_method(self):
        clear_cache()

    def test_cache_miss_returns_none(self):
        assert get_cached_insight("month", "all", None, None) is None

    def test_cache_hit(self):
        data = {"summary": "test", "highlights": []}
        set_cached_insight("month", "all", None, None, data)
        cached = get_cached_insight("month", "all", None, None)
        assert cached is not None
        assert cached["summary"] == "test"

    def test_cache_different_params_miss(self):
        data = {"summary": "test"}
        set_cached_insight("month", "all", None, None, data)
        assert get_cached_insight("week", "all", None, None) is None
        assert get_cached_insight("month", "senior", None, None) is None

    def test_cache_expiry(self):
        data = {"summary": "test"}
        set_cached_insight("month", "all", None, None, data)
        # Manually expire the entry
        from app.services.market_insights import _cache, _cache_key
        key = _cache_key("month", "all", None, None)
        _cache[key]["_expires"] = time.time() - 1  # expired
        assert get_cached_insight("month", "all", None, None) is None

    def test_clear_cache(self):
        set_cached_insight("month", "all", None, None, {"summary": "x"})
        clear_cache()
        assert get_cached_insight("month", "all", None, None) is None


# ---------------------------------------------------------------------------
# 7. generate_market_insight integration (with mocked LLM + aggregation)
# ---------------------------------------------------------------------------

class TestGenerateInsight:
    def setup_method(self):
        clear_cache()

    @pytest.mark.asyncio
    async def test_generates_insight(self):
        session = AsyncMock()
        llm = MockLLMClient(
            response_text="- React лидирует\n- TypeScript обязателен")

        with patch("app.services.market_insights.build_market_context") as m_ctx:
            m_ctx.return_value = {
                "grade_filter": "all",
                "date_range": {"from": None, "to": None},
                "salary": {"median": 200000, "total_vacancies": 100, "sample_size": 80},
                "top_skills": [],
                "top_employers": [],
                "demand_trend": [],
                "grade_distribution": [],
                "format_distribution": [],
            }
            result = await generate_market_insight(session, llm, period="month")

        assert "summary" in result
        assert "React лидирует" in result["summary"]
        assert "highlights" in result
        assert len(result["highlights"]) >= 1
        assert result["model"] == "test-model"
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self):
        session = AsyncMock()
        llm = MockLLMClient(response_text="Cached result")

        with patch("app.services.market_insights.build_market_context") as m_ctx:
            m_ctx.return_value = {
                "grade_filter": "all",
                "date_range": {"from": None, "to": None},
                "salary": {"total_vacancies": 50, "sample_size": 40},
                "top_skills": [], "top_employers": [],
                "demand_trend": [], "grade_distribution": [], "format_distribution": [],
            }
            # First call — hits LLM
            result1 = await generate_market_insight(session, llm)
            # Second call — should use cache
            result2 = await generate_market_insight(session, llm)

        assert len(llm.chat_calls) == 1  # Only one LLM call (cached second)
        assert result2["summary"] == result1["summary"]

    @pytest.mark.asyncio
    async def test_llm_error_propagates(self):
        session = AsyncMock()
        llm = FailingLLMClient()

        with patch("app.services.market_insights.build_market_context") as m_ctx:
            m_ctx.return_value = {
                "grade_filter": "all", "date_range": {"from": None, "to": None},
                "salary": {"total_vacancies": 0, "sample_size": 0},
                "top_skills": [], "top_employers": [],
                "demand_trend": [], "grade_distribution": [], "format_distribution": [],
            }
            with pytest.raises(LLMError):
                await generate_market_insight(session, llm)


# ---------------------------------------------------------------------------
# 8. Factory tests
# ---------------------------------------------------------------------------

class TestLLMFactory:
    def setup_method(self):
        reset_llm_client()

    def teardown_method(self):
        reset_llm_client()

    def test_disabled_returns_none(self):
        with patch("app.services.llm.factory.settings") as m_settings:
            m_settings.LLM_ENABLED = False
            m_settings.API_KEY = "some-key"
            result = get_llm_client()
        assert result is None

    def test_no_key_returns_none(self):
        with patch("app.services.llm.factory.settings") as m_settings:
            m_settings.LLM_ENABLED = True
            m_settings.API_KEY = ""
            result = get_llm_client()
        assert result is None

    def test_placeholder_key_returns_none(self):
        with patch("app.services.llm.factory.settings") as m_settings:
            m_settings.LLM_ENABLED = True
            m_settings.API_KEY = "your-api-key-here"
            result = get_llm_client()
        assert result is None


# ---------------------------------------------------------------------------
# 9. Endpoint tests (HTTP-level)
# ---------------------------------------------------------------------------

class TestInsightsEndpoint:
    """Test GET /api/v1/insights/market endpoint."""

    @pytest.mark.asyncio
    async def test_disabled_returns_200_with_message(self, client):
        """When LLM is disabled, endpoint returns 200 with disabled message."""
        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=None):
            resp = await client.get("/api/v1/insights/market")

        assert resp.status_code == 200
        body = resp.json()

        # Check envelope structure
        assert "meta" in body
        assert "data" in body

        # Meta
        assert body["meta"]["llm_enabled"] is False
        assert body["meta"]["period"] == "month"
        assert body["meta"]["grade"] == "all"

        # Data
        assert "summary" in body["data"]
        assert "недоступен" in body["data"]["summary"].lower(
        ) or "отключен" in body["data"]["summary"].lower()
        assert body["data"]["highlights"] == []
        assert body["data"]["based_on"]["sample_size"] == 0

    @pytest.mark.asyncio
    async def test_success_returns_200_with_insight(self, client):
        """When LLM works, return full insight."""
        mock_result = {
            "summary": "React и TypeScript лидируют",
            "highlights": ["React #1", "TS обязателен"],
            "based_on": {"sample_size": 500},
            "model": "x5-airun-medium",
            "generated_at": "2026-06-06T04:00:00Z",
        }

        mock_llm = MockLLMClient()

        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=mock_llm), \
                patch("app.api.v1.endpoints.insights.generate_market_insight", return_value=mock_result):
            resp = await client.get("/api/v1/insights/market?period=month&grade=all")

        assert resp.status_code == 200
        body = resp.json()

        assert body["meta"]["llm_enabled"] is True
        assert body["meta"]["model"] == "x5-airun-medium"
        assert body["data"]["summary"] == "React и TypeScript лидируют"
        assert len(body["data"]["highlights"]) == 2
        assert body["data"]["based_on"]["sample_size"] == 500

    @pytest.mark.asyncio
    async def test_llm_error_returns_200_with_fallback(self, client):
        """When LLM throws error, return 200 with error message (no crash)."""
        mock_llm = MockLLMClient()

        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=mock_llm), \
            patch("app.api.v1.endpoints.insights.generate_market_insight",
                  side_effect=LLMError("timeout", retryable=True)):
            resp = await client.get("/api/v1/insights/market")

        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["llm_enabled"] is True
        assert "не удалось" in body["data"]["summary"].lower(
        ) or "ошибка" in body["data"]["summary"].lower()

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_200(self, client):
        """Any unexpected exception returns 200 with error, not 500."""
        mock_llm = MockLLMClient()

        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=mock_llm), \
            patch("app.api.v1.endpoints.insights.generate_market_insight",
                  side_effect=RuntimeError("something broke")):
            resp = await client.get("/api/v1/insights/market")

        assert resp.status_code == 200
        body = resp.json()
        assert "ошибка" in body["data"]["summary"].lower()

    @pytest.mark.asyncio
    async def test_grade_filter_passed(self, client):
        """Grade filter is forwarded in meta."""
        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=None):
            resp = await client.get("/api/v1/insights/market?grade=senior")
        body = resp.json()
        assert body["meta"]["grade"] == "senior"

    @pytest.mark.asyncio
    async def test_period_filter_passed(self, client):
        """Period filter is forwarded in meta."""
        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=None):
            resp = await client.get("/api/v1/insights/market?period=week")
        body = resp.json()
        assert body["meta"]["period"] == "week"

    @pytest.mark.asyncio
    async def test_invalid_period_returns_422(self, client):
        """Invalid period value returns 422."""
        with patch("app.api.v1.endpoints.insights.get_llm_client", return_value=None):
            resp = await client.get("/api/v1/insights/market?period=invalid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10. Schema tests
# ---------------------------------------------------------------------------

class TestInsightSchemas:
    def test_market_insight_response_structure(self):
        resp = MarketInsightResponse(
            meta=InsightMeta(period="month", grade="all", llm_enabled=True),
            data=InsightData(
                summary="Test",
                highlights=["a", "b"],
                based_on=InsightBasedOn(sample_size=100),
            ),
        )
        d = resp.model_dump()
        assert d["meta"]["period"] == "month"
        assert d["data"]["summary"] == "Test"
        assert d["data"]["based_on"]["sample_size"] == 100

    def test_default_values(self):
        resp = MarketInsightResponse(
            meta=InsightMeta(),
            data=InsightData(),
        )
        d = resp.model_dump()
        assert d["meta"]["period"] == "month"
        assert d["meta"]["llm_enabled"] is True
        assert d["data"]["summary"] == ""
        assert d["data"]["highlights"] == []
