"""Metrics endpoints — Phase 4.

REST API per docs/06-api-contract.md §3:
  GET /api/v1/metrics/salary
  GET /api/v1/metrics/salary/timeseries
  GET /api/v1/metrics/skills
  GET /api/v1/metrics/skills/cooccurrence
  GET /api/v1/metrics/employers
  GET /api/v1/metrics/demand
  GET /api/v1/metrics/distribution
  GET /api/v1/metrics/overview

All endpoints support common query filters: period, date_from, date_to, grade,
currency, salary_basis.  Metrics are computed on-the-fly from DB data
(with snapshot pre-computation available for fast reads).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.grade import Grade
from app.schemas.metrics import (
    CooccurrenceData,
    CooccurrenceResponse,
    DemandData,
    DemandResponse,
    DistributionData,
    DistributionResponse,
    EmployersData,
    EmployersResponse,
    MetricsMeta,
    OverviewData,
    OverviewResponse,
    SalaryData,
    SalaryPercentiles,
    SalaryRangeAvg,
    SalaryResponse,
    SalaryTimeseriesData,
    SalaryTimeseriesResponse,
    SkillsData,
    SkillsResponse,
)
from app.services.aggregation import (
    compute_demand_metrics,
    compute_distribution,
    compute_employers_metrics,
    compute_overview,
    compute_salary_metrics,
    compute_salary_timeseries,
    compute_skill_cooccurrence,
    compute_skills_metrics,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ---------------------------------------------------------------------------
# Query parameter enums
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


class DistByEnum(str, Enum):
    grade = "grade"
    format = "format"
    experience = "experience"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_grade_id(
    session: AsyncSession, grade: str
) -> int | None:
    """Resolve grade code to grade_id. Returns None for 'all'."""
    if grade == "all":
        return None
    result = await session.execute(
        select(Grade.id).where(Grade.code == grade)
    )
    row = result.scalar_one_or_none()
    return row


def _build_meta(
    period: str,
    date_from: date | None,
    date_to: date | None,
    grade: str,
    currency: str,
    salary_basis: str,
    sample_size: int = 0,
    low_confidence: bool = False,
) -> MetricsMeta:
    return MetricsMeta(
        period=period,
        date_from=date_from,
        date_to=date_to,
        grade=grade,
        currency=currency,
        salary_basis=salary_basis,
        computed_at=datetime.now(timezone.utc),
        low_confidence=low_confidence,
        sample_size=sample_size,
    )


# ---------------------------------------------------------------------------
# §3.1 GET /api/v1/metrics/salary
# ---------------------------------------------------------------------------

@router.get("/salary", response_model=SalaryResponse)
async def get_salary_metrics(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    currency: str = Query("RUB"),
    salary_basis: str = Query("net"),
) -> SalaryResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_salary_metrics(session, date_from, date_to, grade_id)

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, currency, salary_basis,
        sample_size=data.get("count", 0),
        low_confidence=data.get("low_confidence", False),
    )

    pct = data.get("percentiles", {})
    rng = data.get("range_avg", {})

    return SalaryResponse(
        meta=meta,
        data=SalaryData(
            median=data.get("median"),
            min=data.get("min"),
            max=data.get("max"),
            mean=data.get("mean"),
            percentiles=SalaryPercentiles(
                p10=pct.get("p10"),
                p25=pct.get("p25"),
                p50=pct.get("p50"),
                p75=pct.get("p75"),
                p90=pct.get("p90"),
            ),
            range_avg=SalaryRangeAvg(
                **{"from": rng.get("from"), "to": rng.get("to")}),
            salary_disclosure_rate=data.get("salary_disclosure_rate"),
            currency=currency,
            salary_basis=salary_basis,
        ),
    )


# ---------------------------------------------------------------------------
# §3.2 GET /api/v1/metrics/salary/timeseries
# ---------------------------------------------------------------------------

@router.get("/salary/timeseries", response_model=SalaryTimeseriesResponse)
async def get_salary_timeseries(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    currency: str = Query("RUB"),
    salary_basis: str = Query("net"),
) -> SalaryTimeseriesResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_salary_timeseries(
        session, period_type=period.value,
        date_from=date_from, date_to=date_to, grade_id=grade_id,
    )

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, currency, salary_basis,
        low_confidence=data.get("low_confidence", False),
    )

    return SalaryTimeseriesResponse(
        meta=meta,
        data=SalaryTimeseriesData(points=data.get("points", [])),
    )


# ---------------------------------------------------------------------------
# §3.3 GET /api/v1/metrics/skills
# ---------------------------------------------------------------------------

@router.get("/skills", response_model=SkillsResponse)
async def get_skills_metrics(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    limit: int = Query(20, ge=1, le=100),
) -> SkillsResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_skills_metrics(
        session, date_from, date_to, grade_id, limit=limit,
    )

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, "RUB", "net",
        sample_size=data.get("sample_size", 0),
        low_confidence=data.get("low_confidence", False),
    )

    return SkillsResponse(
        meta=meta,
        data=SkillsData(skills=data.get("skills", [])),
    )


# ---------------------------------------------------------------------------
# §3.4 GET /api/v1/metrics/skills/cooccurrence
# ---------------------------------------------------------------------------

@router.get("/skills/cooccurrence", response_model=CooccurrenceResponse)
async def get_skill_cooccurrence(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    limit: int = Query(20, ge=1, le=100),
) -> CooccurrenceResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_skill_cooccurrence(
        session, date_from, date_to, grade_id, limit=limit,
    )

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, "RUB", "net",
        sample_size=data.get("sample_size", 0),
        low_confidence=data.get("low_confidence", False),
    )

    return CooccurrenceResponse(
        meta=meta,
        data=CooccurrenceData(pairs=data.get("pairs", [])),
    )


# ---------------------------------------------------------------------------
# §3.5 GET /api/v1/metrics/employers
# ---------------------------------------------------------------------------

@router.get("/employers", response_model=EmployersResponse)
async def get_employers_metrics(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    limit: int = Query(20, ge=1, le=100),
) -> EmployersResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_employers_metrics(
        session, date_from, date_to, grade_id, limit=limit,
    )

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, "RUB", "net",
        sample_size=data.get("sample_size", 0),
        low_confidence=data.get("low_confidence", False),
    )

    return EmployersResponse(
        meta=meta,
        data=EmployersData(
            employers=data.get("employers", []),
            top10_concentration=data.get("top10_concentration", 0.0),
        ),
    )


# ---------------------------------------------------------------------------
# §3.6 GET /api/v1/metrics/demand
# ---------------------------------------------------------------------------

@router.get("/demand", response_model=DemandResponse)
async def get_demand_metrics(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
) -> DemandResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_demand_metrics(
        session, period_type=period.value,
        date_from=date_from, date_to=date_to, grade_id=grade_id,
    )

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, "RUB", "net",
        low_confidence=data.get("low_confidence", False),
    )

    return DemandResponse(
        meta=meta,
        data=DemandData(points=data.get("points", [])),
    )


# ---------------------------------------------------------------------------
# §3.7 GET /api/v1/metrics/distribution
# ---------------------------------------------------------------------------

@router.get("/distribution", response_model=DistributionResponse)
async def get_distribution(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    by: DistByEnum = Query(DistByEnum.grade),
) -> DistributionResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_distribution(
        session, by=by.value,
        date_from=date_from, date_to=date_to, grade_id=grade_id,
    )

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, "RUB", "net",
        sample_size=data.get("sample_size", 0),
        low_confidence=data.get("low_confidence", False),
    )

    return DistributionResponse(
        meta=meta,
        data=DistributionData(distribution=data.get("distribution", [])),
    )


# ---------------------------------------------------------------------------
# §3.8 GET /api/v1/metrics/overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    session: AsyncSession = Depends(get_session),
    period: PeriodEnum = Query(PeriodEnum.month),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    grade: GradeEnum = Query(GradeEnum.all),
    currency: str = Query("RUB"),
    salary_basis: str = Query("net"),
) -> OverviewResponse:
    grade_id = await _resolve_grade_id(session, grade.value)
    data = await compute_overview(session, date_from, date_to, grade_id)

    meta = _build_meta(
        period.value, date_from, date_to, grade.value, currency, salary_basis,
        sample_size=data.get("total_vacancies", 0),
        low_confidence=data.get("low_confidence", False),
    )

    return OverviewResponse(
        meta=meta,
        data=OverviewData(**data),
    )
