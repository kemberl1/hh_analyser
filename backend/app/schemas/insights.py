"""Pydantic v2 schemas for LLM insights API — Phase 6.

Matches the JSON contract in docs/06-api-contract.md §5.1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# §5.1 — Market Insight
# ---------------------------------------------------------------------------

class InsightMeta(BaseModel):
    """Metadata envelope for insight endpoints."""
    period: str = "month"
    grade: str = "all"
    model: str | None = None
    generated_at: str | None = None
    cached: bool = False
    llm_enabled: bool = True


class InsightBasedOn(BaseModel):
    """What data the insight was based on."""
    sample_size: int = 0


class InsightData(BaseModel):
    """LLM-generated market insight payload."""
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    based_on: InsightBasedOn = InsightBasedOn()


class MarketInsightResponse(BaseModel):
    """Full response for GET /api/v1/insights/market."""
    meta: InsightMeta
    data: InsightData


class InsightDisabledData(BaseModel):
    """Response data when LLM is disabled."""
    summary: str = "LLM-анализ рынка временно недоступен."
    highlights: list[str] = Field(default_factory=list)
    based_on: InsightBasedOn = InsightBasedOn()


class InsightErrorData(BaseModel):
    """Response data when LLM request fails."""
    summary: str = "Не удалось получить анализ рынка. Попробуйте позже."
    highlights: list[str] = Field(default_factory=list)
    based_on: InsightBasedOn = InsightBasedOn()
