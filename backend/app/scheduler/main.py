"""Scheduler entrypoint — APScheduler worker process.

Phase 1: empty scaffold (no real jobs).
Phase 3: daily ingestion jobs will be added here.
"""

from __future__ import annotations

import signal
import sys

import structlog
from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging(settings.LOG_LEVEL)
logger = structlog.get_logger(__name__)


def _placeholder_job() -> None:
    """Placeholder job — will be replaced by real ingestion in Phase 3."""
    logger.info("scheduler_heartbeat",
                message="Scheduler is alive (no jobs configured yet)")


def main() -> None:
    """Start the blocking scheduler."""
    scheduler = BlockingScheduler()

    # Phase 3: real cron job will be registered here, e.g.:
    # scheduler.add_job(run_ingestion, CronTrigger(hour=settings.SCHEDULER_CRON_HOUR, ...))

    # For now, just a heartbeat every 60s to prove the process is alive
    scheduler.add_job(_placeholder_job, "interval", seconds=60, id="heartbeat")

    def _shutdown(signum: int, frame: object) -> None:
        logger.info("scheduler_shutdown_signal", signal=signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("scheduler_starting")
    scheduler.start()


if __name__ == "__main__":
    main()
