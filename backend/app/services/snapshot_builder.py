"""Snapshot builder — precompute and store metric snapshots.

Phase 4: Builds snapshots for all metric_type × period_type × grade combinations.
Called after each ingestion run (scheduler) and/or via CLI.
Atomic replacement: delete old snapshots for the slice, insert new ones.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grade import Grade
from app.models.snapshot import Snapshot
from app.models.vacancy import Vacancy
from app.services.aggregation import (
    MSK_TZ,
    compute_demand_metrics,
    compute_distribution,
    compute_employers_metrics,
    compute_overview,
    compute_salary_metrics,
    compute_salary_timeseries,
    compute_skill_cooccurrence,
    compute_skills_metrics,
    period_start_for,
)

logger = structlog.get_logger(__name__)

# All period types to precompute
PERIOD_TYPES = ["day", "week", "month", "year"]

# Metric types mapped to their compute functions
METRIC_TYPES = [
    "salary",
    "skills",
    "employers",
    "demand_trend",
    "salary_timeseries",
    "grade_distribution",
    "format_distribution",
    "experience_distribution",
    "skill_cooccurrence",
    "overview",
]


async def _get_grade_ids(session: AsyncSession) -> list[int | None]:
    """Return list of grade IDs plus None (= all grades)."""
    result = await session.execute(select(Grade.id))
    ids = [r[0] for r in result.all()]
    return [None] + ids  # None means "all grades"


async def _get_date_range(session: AsyncSession) -> tuple[date | None, date | None]:
    """Get min/max published_at from vacancies."""
    result = await session.execute(
        select(
            func.min(Vacancy.published_at),
            func.max(Vacancy.published_at),
        )
    )
    row = result.one_or_none()
    if row is None or row[0] is None:
        return None, None

    min_dt = row[0]
    max_dt = row[1]
    # Convert to MSK dates
    if min_dt.tzinfo is None:
        min_dt = min_dt.replace(tzinfo=timezone.utc)
    if max_dt.tzinfo is None:
        max_dt = max_dt.replace(tzinfo=timezone.utc)

    return min_dt.astimezone(MSK_TZ).date(), max_dt.astimezone(MSK_TZ).date()


# Need func import
from sqlalchemy import func  # noqa: E402


async def _upsert_snapshot(
    session: AsyncSession,
    metric_type: str,
    period_type: str,
    period_start: date,
    grade_id: int | None,
    payload: dict,
    currency: str = "RUB",
    gross_basis: bool = False,
) -> None:
    """Insert or replace a single snapshot row."""
    now = datetime.now(timezone.utc)
    stmt = pg_insert(Snapshot).values(
        metric_type=metric_type,
        period_type=period_type,
        period_start=period_start,
        grade_id=grade_id,
        currency=currency,
        gross_basis=gross_basis,
        payload=payload,
        computed_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_snapshots_slice",
        set_={
            "payload": stmt.excluded.payload,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    await session.execute(stmt)


async def build_snapshots(
    session: AsyncSession,
    period_types: list[str] | None = None,
) -> dict:
    """Build all metric snapshots.

    Args:
        session: Async DB session.
        period_types: Which period granularities to compute. Defaults to all.

    Returns:
        Summary dict with counts.
    """
    if period_types is None:
        period_types = PERIOD_TYPES

    grade_ids = await _get_grade_ids(session)
    date_min, date_max = await _get_date_range(session)

    if date_min is None or date_max is None:
        logger.warning("snapshot_build_skipped", reason="no vacancies in DB")
        return {"status": "skipped", "reason": "no_data", "snapshots_written": 0}

    total_written = 0
    logger.info(
        "snapshot_build_started",
        date_min=str(date_min),
        date_max=str(date_max),
        period_types=period_types,
        grade_count=len(grade_ids),
    )

    for pt in period_types:
        for gid in grade_ids:
            try:
                # M1 — Salary
                salary_payload = await compute_salary_metrics(
                    session, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "salary", pt, period_start_for(date_min, pt),
                    gid, salary_payload,
                )
                total_written += 1

                # M2 — Skills
                skills_payload = await compute_skills_metrics(
                    session, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "skills", pt, period_start_for(date_min, pt),
                    gid, skills_payload,
                )
                total_written += 1

                # M3 — Employers
                employers_payload = await compute_employers_metrics(
                    session, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "employers", pt, period_start_for(date_min, pt),
                    gid, employers_payload,
                )
                total_written += 1

                # M4.1/M4.3 — Demand trend
                demand_payload = await compute_demand_metrics(
                    session, period_type=pt, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "demand_trend", pt, period_start_for(
                        date_min, pt),
                    gid, demand_payload,
                )
                total_written += 1

                # M4.2 — Salary timeseries
                ts_payload = await compute_salary_timeseries(
                    session, period_type=pt, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "salary_timeseries", pt, period_start_for(
                        date_min, pt),
                    gid, ts_payload,
                )
                total_written += 1

                # M5.1 — Grade distribution
                grade_dist = await compute_distribution(
                    session, "grade", date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "grade_distribution", pt, period_start_for(
                        date_min, pt),
                    gid, grade_dist,
                )
                total_written += 1

                # M5.2 — Format distribution
                format_dist = await compute_distribution(
                    session, "format", date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "format_distribution", pt, period_start_for(
                        date_min, pt),
                    gid, format_dist,
                )
                total_written += 1

                # M5.3 — Experience distribution
                exp_dist = await compute_distribution(
                    session, "experience", date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "experience_distribution", pt, period_start_for(
                        date_min, pt),
                    gid, exp_dist,
                )
                total_written += 1

                # M5.4 — Skill co-occurrence
                cooc_payload = await compute_skill_cooccurrence(
                    session, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "skill_cooccurrence", pt, period_start_for(
                        date_min, pt),
                    gid, cooc_payload,
                )
                total_written += 1

                # Overview
                overview_payload = await compute_overview(
                    session, date_from=date_min, date_to=date_max, grade_id=gid
                )
                await _upsert_snapshot(
                    session, "overview", pt, period_start_for(date_min, pt),
                    gid, overview_payload,
                )
                total_written += 1

            except Exception:
                logger.exception(
                    "snapshot_build_error",
                    metric_type="batch",
                    period_type=pt,
                    grade_id=gid,
                )

    await session.commit()
    logger.info("snapshot_build_finished", snapshots_written=total_written)
    return {"status": "success", "snapshots_written": total_written}
