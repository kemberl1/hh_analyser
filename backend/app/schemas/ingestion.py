"""Pydantic schemas for ingestion status endpoint (Phase 3, §2.2 api-contract)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IngestionRunStatus(BaseModel):
    """Schema for a single ingestion run summary."""

    id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    found_total: int = 0
    created_count: int = 0
    updated_count: int = 0
    error_count: int = 0
    filtered_count: int = 0
    api_fallback_count: int = 0
    captcha_block_count: int = 0

    model_config = {"from_attributes": True}


class IngestionStatusResponse(BaseModel):
    """Response for GET /api/v1/ingestion/status."""

    last_run: IngestionRunStatus | None = None
    data_freshness_hours: float | None = None
