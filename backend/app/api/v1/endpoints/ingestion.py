"""Ingestion status endpoint — GET /api/v1/ingestion/status (Phase 3).

Returns the last ingestion run summary and data freshness (FR-25, NFR-20).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.ingestion_run import IngestionRun
from app.schemas.ingestion import IngestionRunStatus, IngestionStatusResponse

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/status", response_model=IngestionStatusResponse)
async def get_ingestion_status(
    session: AsyncSession = Depends(get_session),
) -> IngestionStatusResponse:
    """Return the last ingestion run and data freshness.

    - ``last_run``: summary of the most recent ingestion run (by started_at).
    - ``data_freshness_hours``: hours since the last *successful* run finished.
      ``null`` if no successful run exists.
    """
    # Last run (any status)
    stmt_last = (
        select(IngestionRun)
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt_last)
    last_run_row = result.scalar_one_or_none()

    last_run: IngestionRunStatus | None = None
    if last_run_row is not None:
        last_run = IngestionRunStatus.model_validate(last_run_row)

    # Data freshness: hours since last successful run finished
    data_freshness_hours: float | None = None
    if last_run_row is not None and last_run_row.status in ("success", "partial"):
        if last_run_row.finished_at is not None:
            finished = last_run_row.finished_at
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - finished
            data_freshness_hours = round(delta.total_seconds() / 3600, 1)

    return IngestionStatusResponse(
        last_run=last_run,
        data_freshness_hours=data_freshness_hours,
    )
