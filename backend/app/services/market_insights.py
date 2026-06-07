"""Market insights service — Phase 6.

Gathers ANONYMISED aggregate metrics (NFR-16: no PII, no raw vacancies)
from the existing aggregation layer and sends them to the LLM for
a Russian-language analytical summary of the Frontend job market.

Caching: the last generated insight is cached in memory with a TTL
(LLM_CACHE_TTL, default 1 hour) to avoid redundant LLM calls.
"""

from __future__ import annotations

import hashlib
import time
from datetime import date, datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.aggregation import (
    compute_demand_metrics,
    compute_distribution,
    compute_employers_metrics,
    compute_salary_metrics,
    compute_skills_metrics,
)
from app.services.llm.base import LLMClient, LLMError, LLMMessage

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# In-memory cache (simple TTL-based)
# ---------------------------------------------------------------------------

_cache: dict[str, dict[str, Any]] = {}


def _cache_key(period: str, grade: str, date_from: date | None, date_to: date | None) -> str:
    """Build a deterministic cache key from query params."""
    raw = f"{period}:{grade}:{date_from}:{date_to}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached_insight(
    period: str, grade: str, date_from: date | None, date_to: date | None
) -> dict[str, Any] | None:
    """Return cached insight if still valid, else None."""
    key = _cache_key(period, grade, date_from, date_to)
    entry = _cache.get(key)
    if entry is None:
        return None
    expires = entry.get("_expires", 0)
    if time.time() > expires:
        _cache.pop(key, None)
        return None
    return entry


def set_cached_insight(
    period: str,
    grade: str,
    date_from: date | None,
    date_to: date | None,
    data: dict[str, Any],
) -> None:
    """Store insight in cache with TTL."""
    key = _cache_key(period, grade, date_from, date_to)
    _cache[key] = {**data, "_expires": time.time() + settings.LLM_CACHE_TTL}


def clear_cache() -> None:
    """Purge the entire insight cache (useful in tests)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Context builder — ONLY anonymous aggregates (NFR-16)
# ---------------------------------------------------------------------------

async def build_market_context(
    session: AsyncSession,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
    grade_label: str = "all",
) -> dict[str, Any]:
    """Collect anonymised aggregate data for the LLM prompt.

    Returns a dict with summary numbers only — NO raw vacancy texts,
    NO employer IDs, NO personal information.  This satisfies NFR-16.
    """
    salary = await compute_salary_metrics(session, date_from, date_to, grade_id)
    skills = await compute_skills_metrics(session, date_from, date_to, grade_id, limit=15)
    employers = await compute_employers_metrics(session, date_from, date_to, grade_id, limit=10)
    demand = await compute_demand_metrics(session, "month", date_from, date_to, grade_id)
    grade_dist = await compute_distribution(session, "grade", date_from, date_to, None)
    format_dist = await compute_distribution(session, "format", date_from, date_to, grade_id)

    context = {
        "grade_filter": grade_label,
        "date_range": {
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
        },
        "salary": {
            "sample_size": salary.get("count", 0),
            "total_vacancies": salary.get("total_count", 0),
            "median": salary.get("median"),
            "mean": salary.get("mean"),
            "min": salary.get("min"),
            "max": salary.get("max"),
            "percentiles": salary.get("percentiles", {}),
            "salary_disclosure_rate": salary.get("salary_disclosure_rate"),
        },
        "top_skills": [
            {"name": s["skill"], "share": s["share"], "count": s["count"]}
            for s in skills.get("skills", [])
        ],
        "top_employers": [
            {"name": e["name"], "count": e["count"], "share": e["share"]}
            for e in employers.get("employers", [])
        ],
        "demand_trend": [
            {"period": p["period_start"], "count": p["count"],
                "growth": p.get("growth")}
            for p in demand.get("points", [])[-6:]  # last 6 periods
        ],
        "grade_distribution": [
            {"grade": d["key"], "share": d["share"], "count": d["count"]}
            for d in grade_dist.get("distribution", [])
        ],
        "format_distribution": [
            {"format": d["key"], "share": d["share"], "count": d["count"]}
            for d in format_dist.get("distribution", [])
        ],
    }
    return context


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Ты — эксперт-аналитик рынка IT-вакансий в России, специализирующийся на Frontend-разработке.
Тебе предоставлены ОБЕЗЛИЧЕННЫЕ агрегированные метрики рынка Frontend-вакансий.
На основе этих данных ты должен:
1. Кратко описать текущее состояние рынка (спрос, уровень зарплат, тренды).
2. Выделить ключевые навыки и технологии, которые сейчас наиболее востребованы.
3. Отметить заметные тренды (рост/падение спроса, изменение зарплат, распределение по грейдам и форматам работы).
4. Дать 3–5 практических рекомендаций соискателю (что изучать, на что обращать внимание).

Отвечай на русском языке. Будь конкретным, опирайся на цифры из предоставленных данных.
Не выдумывай данных, которых нет. Если данных недостаточно — скажи об этом.
Ответ структурируй: «Обзор рынка», «Востребованные навыки», «Тренды», «Рекомендации».\
"""


def build_prompt(context: dict[str, Any]) -> list[LLMMessage]:
    """Build the chat messages for the LLM based on aggregated context."""
    import json

    # Format context as readable text for the LLM
    ctx_text = json.dumps(context, ensure_ascii=False, indent=2, default=str)

    user_message = (
        "Вот агрегированные метрики рынка Frontend-вакансий в России "
        f"(грейд: {context.get('grade_filter', 'all')}):\n\n"
        f"```json\n{ctx_text}\n```\n\n"
        "Проанализируй эти данные и дай аналитическое резюме по рынку."
    )

    return [
        LLMMessage(role="system", content=_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_message),
    ]


# ---------------------------------------------------------------------------
# Extract highlights from the LLM response
# ---------------------------------------------------------------------------

def _extract_highlights(text: str) -> list[str]:
    """Best-effort extraction of key bullet points from the LLM text."""
    highlights: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Pick lines that look like bullet points or numbered items
        if stripped and (
            stripped.startswith("- ")
            or stripped.startswith("• ")
            or stripped.startswith("* ")
            or (len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)")
        ):
            clean = stripped.lstrip("-•* 0123456789.)")
            if clean:
                highlights.append(clean.strip())
    return highlights[:10]  # cap at 10


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_market_insight(
    session: AsyncSession,
    llm_client: LLMClient,
    *,
    period: str = "month",
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
    grade_label: str = "all",
) -> dict[str, Any]:
    """Generate (or return cached) LLM market insight.

    Returns
    -------
    dict with keys: summary, highlights, based_on, model, generated_at.

    Raises
    ------
    LLMError on provider failures (after retries).
    """
    # Check cache first
    cached = get_cached_insight(period, grade_label, date_from, date_to)
    if cached is not None:
        logger.info("market_insight_cache_hit",
                    period=period, grade=grade_label)
        result = {k: v for k, v in cached.items() if k != "_expires"}
        return result

    # Build anonymised context (NFR-16)
    context = await build_market_context(
        session,
        date_from=date_from,
        date_to=date_to,
        grade_id=grade_id,
        grade_label=grade_label,
    )

    sample_size = context.get("salary", {}).get("total_vacancies", 0)

    # Build prompt and call LLM
    messages = build_prompt(context)

    logger.info(
        "market_insight_request",
        period=period,
        grade=grade_label,
        sample_size=sample_size,
    )

    response = await llm_client.chat(messages)

    # Build the result
    highlights = _extract_highlights(response.content)
    result: dict[str, Any] = {
        "summary": response.content,
        "highlights": highlights,
        "based_on": {
            "sample_size": sample_size,
        },
        "model": response.model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache the result
    set_cached_insight(period, grade_label, date_from, date_to, result)

    logger.info(
        "market_insight_generated",
        model=response.model,
        tokens=response.usage.get("total_tokens"),
        highlights_count=len(highlights),
    )

    return result
