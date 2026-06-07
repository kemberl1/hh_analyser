"""Tests for Phase 3 — Scheduler jobs, configuration, overlap, and error handling.

All network access is mocked — no real requests to hh.ru.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.main import INGESTION_JOB_ID, build_scheduler


# ---------------------------------------------------------------------------
# 1. Scheduler configuration tests
# ---------------------------------------------------------------------------


class TestSchedulerConfiguration:
    """Verify the scheduler is configured with the correct cron trigger,
    max_instances=1, coalesce=True, and misfire_grace_time."""

    def test_build_scheduler_returns_scheduler(self):
        """build_scheduler() returns an AsyncIOScheduler instance."""
        scheduler = build_scheduler()
        assert scheduler is not None
        # Should have the daily_ingestion job registered
        job = scheduler.get_job(INGESTION_JOB_ID)
        assert job is not None

    def test_job_has_cron_trigger(self):
        """The ingestion job uses a CronTrigger."""
        scheduler = build_scheduler()
        job = scheduler.get_job(INGESTION_JOB_ID)
        assert isinstance(job.trigger, CronTrigger)

    def test_job_max_instances_is_one(self):
        """max_instances=1 prevents overlapping runs."""
        scheduler = build_scheduler()
        job = scheduler.get_job(INGESTION_JOB_ID)
        assert job.max_instances == 1

    def test_job_coalesce_is_true(self):
        """coalesce=True merges missed runs into one."""
        scheduler = build_scheduler()
        job = scheduler.get_job(INGESTION_JOB_ID)
        assert job.coalesce is True

    def test_job_misfire_grace_time(self):
        """misfire_grace_time is set from settings."""
        from app.core.config import settings

        scheduler = build_scheduler()
        job = scheduler.get_job(INGESTION_JOB_ID)
        assert job.misfire_grace_time == settings.SCHEDULER_MISFIRE_GRACE_TIME

    def test_cron_trigger_hour_minute_from_settings(self):
        """The cron trigger hour/minute match settings."""
        from app.core.config import settings

        scheduler = build_scheduler()
        job = scheduler.get_job(INGESTION_JOB_ID)
        trigger = job.trigger
        # CronTrigger stores fields as expressions
        # We verify by checking the scheduled time matches config
        assert str(settings.SCHEDULER_CRON_HOUR) in str(trigger)
        assert str(settings.SCHEDULER_CRON_MINUTE) in str(trigger)


# ---------------------------------------------------------------------------
# 2. Overlap protection tests
# ---------------------------------------------------------------------------


class TestOverlapProtection:
    """Verify that concurrent ingestion runs are prevented."""

    @pytest.mark.asyncio
    async def test_overlap_skipped_when_lock_held(self):
        """If the ingestion lock is already held, the job returns 'skipped'."""
        from app.scheduler.jobs import _ingestion_lock, _run_daily_ingestion

        # Acquire the lock manually to simulate an active run
        await _ingestion_lock.acquire()
        try:
            result = await _run_daily_ingestion()
            assert result["status"] == "skipped"
            assert result["reason"] == "overlap"
        finally:
            _ingestion_lock.release()


# ---------------------------------------------------------------------------
# 3. Job calls ingestion service and handles errors
# ---------------------------------------------------------------------------


class TestIngestionJobExecution:
    """Verify the job calls run_ingestion and handles exceptions gracefully."""

    @pytest.mark.asyncio
    async def test_job_calls_ingestion_pipeline(self):
        """The job calls run_ingestion and returns its summary."""
        mock_summary = {
            "run_id": 1,
            "status": "success",
            "found_total": 100,
            "created": 50,
            "updated": 40,
            "filtered": 8,
            "errors": 2,
            "captcha_blocks": 0,
            "api_fallback": 0,
        }

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.scheduler.jobs.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.scheduler.jobs.seed_relevance_terms",
                new_callable=AsyncMock,
            ) as mock_seed,
            patch(
                "app.scheduler.jobs.run_ingestion",
                new_callable=AsyncMock,
                return_value=mock_summary,
            ) as mock_run,
        ):
            from app.scheduler.jobs import _run_daily_ingestion

            result = await _run_daily_ingestion()

        assert result == mock_summary
        mock_seed.assert_awaited_once()
        mock_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_job_handles_exception_without_crashing(self):
        """If an unexpected exception occurs, the job catches it and returns
        a failure dict — the scheduler process does NOT crash."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.scheduler.jobs.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.scheduler.jobs.seed_relevance_terms",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB connection lost"),
            ),
        ):
            from app.scheduler.jobs import _run_daily_ingestion

            result = await _run_daily_ingestion()

        assert result["status"] == "failed"
        assert result["error"] == "unexpected_exception"

    @pytest.mark.asyncio
    async def test_job_handles_ingestion_failure(self):
        """If run_ingestion itself raises, the job catches it gracefully."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.scheduler.jobs.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "app.scheduler.jobs.seed_relevance_terms",
                new_callable=AsyncMock,
            ),
            patch(
                "app.scheduler.jobs.run_ingestion",
                new_callable=AsyncMock,
                side_effect=Exception("Unexpected ingestion error"),
            ),
        ):
            from app.scheduler.jobs import _run_daily_ingestion

            result = await _run_daily_ingestion()

        assert result["status"] == "failed"
        assert result["error"] == "unexpected_exception"


# ---------------------------------------------------------------------------
# 4. Ingestion status endpoint tests
# ---------------------------------------------------------------------------


class TestIngestionStatusEndpoint:
    """Verify GET /api/v1/ingestion/status returns correct data."""

    @pytest.mark.asyncio
    async def test_status_no_runs(self, client):
        """When no ingestion runs exist, returns null last_run."""
        from app.db.session import get_session
        from app.main import app

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def _override():
            yield mock_session

        app.dependency_overrides[get_session] = _override
        try:
            resp = await client.get("/api/v1/ingestion/status")
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["last_run"] is None
        assert data["data_freshness_hours"] is None

    @pytest.mark.asyncio
    async def test_status_with_successful_run(self, client):
        """When a successful run exists, returns its data and freshness."""
        from app.db.session import get_session
        from app.main import app
        from app.models.ingestion_run import IngestionRun

        mock_run = IngestionRun(
            id=42,
            started_at=datetime(2026, 6, 6, 3, 0, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 6, 3, 14, 0, tzinfo=timezone.utc),
            status="success",
            found_total=100,
            created_count=50,
            updated_count=40,
            error_count=0,
            filtered_count=10,
            api_fallback_count=0,
            captcha_block_count=0,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def _override():
            yield mock_session

        app.dependency_overrides[get_session] = _override
        try:
            resp = await client.get("/api/v1/ingestion/status")
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["last_run"]["id"] == 42
        assert data["last_run"]["status"] == "success"
        assert data["last_run"]["found_total"] == 100
        assert data["data_freshness_hours"] is not None
        assert isinstance(data["data_freshness_hours"], float)
