"""Scheduler entrypoint — APScheduler worker process (Phase 3).

Runs as a **separate process** from the API (see §2 architecture).
Registers a daily cron job that calls the ingestion pipeline.

Usage:
    python -m app.scheduler.main              # start scheduler (cron mode)
    python -m app.scheduler.main --run-now    # run job immediately, then exit
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.logging import setup_logging
from app.scheduler.jobs import _run_daily_ingestion

setup_logging(settings.LOG_LEVEL)
logger = structlog.get_logger(__name__)

# Job ID constant for the daily ingestion job
INGESTION_JOB_ID = "daily_ingestion"


def build_scheduler() -> AsyncIOScheduler:
    """Build and configure the AsyncIOScheduler with the daily ingestion job.

    Returns a scheduler instance (not yet started).
    """
    scheduler = AsyncIOScheduler(
        timezone=settings.SCHEDULER_TIMEZONE,
    )

    trigger = CronTrigger(
        hour=settings.SCHEDULER_CRON_HOUR,
        minute=settings.SCHEDULER_CRON_MINUTE,
        timezone=settings.SCHEDULER_TIMEZONE,
    )

    scheduler.add_job(
        _run_daily_ingestion,
        trigger=trigger,
        id=INGESTION_JOB_ID,
        name="Daily vacancy ingestion",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=settings.SCHEDULER_MISFIRE_GRACE_TIME,
        replace_existing=True,
    )

    return scheduler


async def _run_now_and_exit() -> None:
    """Run the ingestion job immediately (for testing / manual trigger), then exit."""
    logger.info("scheduler_run_now_mode")
    summary = await _run_daily_ingestion()
    logger.info("scheduler_run_now_complete", **summary)


def main() -> None:
    """Entry point: parse args → either --run-now or start the cron scheduler."""
    parser = argparse.ArgumentParser(
        description="HH Analyser Scheduler (Phase 3)")
    parser.add_argument(
        "--run-now",
        action="store_true",
        default=False,
        help="Run the ingestion job immediately and exit (no cron loop)",
    )
    args = parser.parse_args()

    if args.run_now:
        asyncio.run(_run_now_and_exit())
        sys.exit(0)

    # --- Normal cron mode ---
    scheduler = build_scheduler()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(signum: int, frame: object) -> None:
        logger.info("scheduler_shutdown_signal", signal=signum)
        scheduler.shutdown(wait=False)
        loop.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info(
        "scheduler_starting",
        cron=f"{settings.SCHEDULER_CRON_HOUR:02d}:{settings.SCHEDULER_CRON_MINUTE:02d}",
        timezone=settings.SCHEDULER_TIMEZONE,
        max_pages=settings.SCHEDULER_MAX_PAGES or settings.HH_MAX_PAGES,
        misfire_grace_time=settings.SCHEDULER_MISFIRE_GRACE_TIME,
    )

    scheduler.start()

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)
        loop.close()
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    main()
