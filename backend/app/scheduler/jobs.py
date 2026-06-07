"""Scheduler jobs — async job wrappers for APScheduler.

Phase 3: daily ingestion job that calls the existing ingestion pipeline.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.core.config import settings
from app.db.session import async_session_factory
from app.services.ingestion import run_ingestion
from app.services.seed import seed_relevance_terms

logger = structlog.get_logger(__name__)

# Simple asyncio Lock to prevent overlapping ingestion runs within the same process.
# Combined with APScheduler's max_instances=1 + coalesce=True for belt-and-suspenders.
_ingestion_lock = asyncio.Lock()


async def _run_daily_ingestion() -> dict:
    """Execute the ingestion pipeline with full observability.

    - Logs start/finish/duration/counters via structlog.
    - Exceptions are caught, logged, and recorded in ingestion_runs (status=failed).
    - Never raises — the scheduler process stays alive.

    Returns:
        Summary dict from the ingestion pipeline, or error dict.
    """
    if _ingestion_lock.locked():
        logger.warning(
            "ingestion_job_skipped",
            reason="previous run still active (lock held)",
        )
        return {"status": "skipped", "reason": "overlap"}

    async with _ingestion_lock:
        max_pages = settings.SCHEDULER_MAX_PAGES or settings.HH_MAX_PAGES
        logger.info(
            "ingestion_job_started",
            max_pages=max_pages,
            timezone=settings.SCHEDULER_TIMEZONE,
            cron=f"{settings.SCHEDULER_CRON_HOUR:02d}:{settings.SCHEDULER_CRON_MINUTE:02d}",
        )
        t0 = time.monotonic()

        try:
            async with async_session_factory() as session:
                # Ensure relevance terms are seeded (idempotent)
                await seed_relevance_terms(session)

                summary = await run_ingestion(session, max_pages=max_pages)

            elapsed = time.monotonic() - t0
            logger.info(
                "ingestion_job_finished",
                duration_s=round(elapsed, 2),
                **summary,
            )
            return summary

        except Exception:
            elapsed = time.monotonic() - t0
            logger.exception(
                "ingestion_job_failed",
                duration_s=round(elapsed, 2),
            )
            # The ingestion pipeline itself writes status=failed to ingestion_runs
            # when source_fetch_failed. For truly unexpected errors (e.g. DB down),
            # we log here but do NOT re-raise — scheduler must stay alive.
            return {"status": "failed", "error": "unexpected_exception"}


def daily_ingestion_job() -> None:
    """Synchronous wrapper for APScheduler (runs the async job in the event loop).

    APScheduler's AsyncIOScheduler will call this in the running event loop
    via add_job with the async function directly. This sync wrapper exists
    as a fallback for BlockingScheduler if ever needed.
    """
    asyncio.get_event_loop().run_until_complete(_run_daily_ingestion())
