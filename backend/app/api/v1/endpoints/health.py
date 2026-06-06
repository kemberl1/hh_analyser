"""Health-check endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine
from app.schemas.health import HealthResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health status and DB connectivity."""
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("db_health_check_failed", error=str(exc))
        db_status = "unavailable"

    return HealthResponse(status="ok", db=db_status)
