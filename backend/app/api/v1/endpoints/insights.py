"""Insights endpoints — Phase 6.

REST API per docs/06-api-contract.md §5.1:
  GET /api/v1/insights/market — LLM-generated market analysis

Graceful degradation:
  • LLM_ENABLED=false → 200 with disabled message
  • LLM error/timeout → 200 with error message (no crash)
  • All cases return the {meta, data} envelope
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.grade import Grade
from app.schemas.insights import (
    InsightBasedOn,
    InsightData,
    InsightMeta,
    MarketInsightResponse,
)
from app.services.llm.base import LLMError
from app.services.llm.factory import get_llm_client
from app.services.market_insights import generate_market_insight

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


# ---------------------------------------------------------------------------
# Query parameter enums (reuse pattern from metrics)
# ---------------------------------------------------------------------------

class PeriodEnum(str, Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class GradeEnum(str, Enum):
    junior = "junior"
    middle = "middle"
    senior = "senior"
    all = "all"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_grade_id(
    session: AsyncSession, grade: str
) -> int | None:
    """Resolve grade code to grade_id.  Returns None for 'all'."""
    if grade == "all":
        return None
    result = await session.execute(
        select(Grade.id).where(Grade.code == grade)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# GET /api/v1/insights/market
# ---------------------------------------------------------------------------

@router.get("/market", response_model=MarketInsightResponse)
async def get_market_insight(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
) -> MarketInsightResponse:
    """Return LLM-generated market analysis insight.

    Handles three states gracefully:
    1. LLM enabled & working → full insight
    2. LLM disabled (LLM_ENABLED=false or no API_KEY) → disabled message
    3. LLM error (timeout/auth/provider) → error message
    """
    llm_client = get_llm_client()

    # --- State 2: LLM disabled ---
    if llm_client is None:
        logger.info("insights_llm_disabled")
        return MarketInsightResponse(
            meta=InsightMeta(
                period=period.value,
                grade=grade.value,
                llm_enabled=False,
                generated_at=datetime.now(timezone.utc).isoformat(),
            ),
            data=InsightData(
                summary="LLM-анализ рынка временно недоступен. "
                        "Функция отключена или API-ключ не настроен.",
                highlights=[],
                based_on=InsightBasedOn(sample_size=0),
            ),
        )

    # --- State 1 & 3: LLM enabled — try to generate ---
    try:
        grade_id = await _resolve_grade_id(session, grade.value)

        result = await generate_market_insight(
            session,
            llm_client,
            period=period.value,
            date_from=date_from,
            date_to=date_to,
            grade_id=grade_id,
            grade_label=grade.value,
        )

        # Check if result came from cache
        is_cached = "_expires" not in result  # always true since we strip it

        return MarketInsightResponse(
            meta=InsightMeta(
                period=period.value,
                grade=grade.value,
                model=result.get("model"),
                generated_at=result.get("generated_at"),
                cached=False,  # marker for frontend
                llm_enabled=True,
            ),
            data=InsightData(
                summary=result.get("summary", ""),
                highlights=result.get("highlights", []),
                based_on=InsightBasedOn(
                    sample_size=result.get(
                        "based_on", {}).get("sample_size", 0),
                ),
            ),
        )

    except LLMError as exc:
        # --- State 3: LLM error (graceful degradation) ---
        logger.error(
            "insights_llm_error",
            error=str(exc),
            status_code=exc.status_code,
            retryable=exc.retryable,
        )
        return MarketInsightResponse(
            meta=InsightMeta(
                period=period.value,
                grade=grade.value,
                llm_enabled=True,
                generated_at=datetime.now(timezone.utc).isoformat(),
            ),
            data=InsightData(
                summary="Не удалось получить анализ рынка от ИИ. "
                        "Попробуйте повторить запрос позже.",
                highlights=[],
                based_on=InsightBasedOn(sample_size=0),
            ),
        )

    except Exception as exc:
        # Unexpected error — still don't crash
        logger.exception("insights_unexpected_error", error=str(exc))
        return MarketInsightResponse(
            meta=InsightMeta(
                period=period.value,
                grade=grade.value,
                llm_enabled=True,
                generated_at=datetime.now(timezone.utc).isoformat(),
            ),
            data=InsightData(
                summary="Произошла непредвиденная ошибка при генерации анализа.",
                highlights=[],
                based_on=InsightBasedOn(sample_size=0),
            ),
        )
