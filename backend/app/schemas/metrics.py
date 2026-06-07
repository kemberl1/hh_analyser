"""Pydantic v2 schemas for metrics API responses — Phase 4.

Matches the JSON contract in docs/06-api-contract.md §3.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common meta envelope (§1.3)
# ---------------------------------------------------------------------------

class MetricsMeta(BaseModel):
    """Shared metadata envelope for all metric endpoints."""
    period: str = "month"
    date_from: date | None = None
    date_to: date | None = None
    grade: str = "all"
    currency: str = "RUB"
    salary_basis: str = "net"
    computed_at: datetime | None = None
    low_confidence: bool = False
    sample_size: int = 0


# ---------------------------------------------------------------------------
# §3.1 — Salary
# ---------------------------------------------------------------------------

class SalaryPercentiles(BaseModel):
    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None


class SalaryRangeAvg(BaseModel):
    """Average salary range boundaries."""
    model_config = {"populate_by_name": True}

    from_: float | None = Field(None, alias="from")
    to: float | None = None


class SalaryData(BaseModel):
    median: float | None = None
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    percentiles: SalaryPercentiles = SalaryPercentiles()
    range_avg: SalaryRangeAvg = SalaryRangeAvg()
    salary_disclosure_rate: float | None = None
    currency: str = "RUB"
    salary_basis: str = "net"


class SalaryResponse(BaseModel):
    meta: MetricsMeta
    data: SalaryData


# ---------------------------------------------------------------------------
# §3.2 — Salary timeseries
# ---------------------------------------------------------------------------

class SalaryTimeseriesPoint(BaseModel):
    period_start: str
    median: float
    p25: float
    p75: float
    count: int


class SalaryTimeseriesData(BaseModel):
    points: list[SalaryTimeseriesPoint] = []


class SalaryTimeseriesResponse(BaseModel):
    meta: MetricsMeta
    data: SalaryTimeseriesData


# ---------------------------------------------------------------------------
# §3.3 — Skills
# ---------------------------------------------------------------------------

class SkillItem(BaseModel):
    skill: str
    canonical: str
    count: int
    share: float


class SkillsData(BaseModel):
    skills: list[SkillItem] = []


class SkillsResponse(BaseModel):
    meta: MetricsMeta
    data: SkillsData


# ---------------------------------------------------------------------------
# §3.4 — Skill co-occurrence
# ---------------------------------------------------------------------------

class CooccurrencePair(BaseModel):
    a: str
    b: str
    count: int
    share: float


class CooccurrenceData(BaseModel):
    pairs: list[CooccurrencePair] = []


class CooccurrenceResponse(BaseModel):
    meta: MetricsMeta
    data: CooccurrenceData


# ---------------------------------------------------------------------------
# §3.5 — Employers
# ---------------------------------------------------------------------------

class EmployerItem(BaseModel):
    employer_id: int
    name: str
    count: int
    share: float


class EmployersData(BaseModel):
    employers: list[EmployerItem] = []
    top10_concentration: float = 0.0


class EmployersResponse(BaseModel):
    meta: MetricsMeta
    data: EmployersData


# ---------------------------------------------------------------------------
# §3.6 — Demand
# ---------------------------------------------------------------------------

class DemandPoint(BaseModel):
    period_start: str
    count: int
    growth: float | None = None


class DemandData(BaseModel):
    points: list[DemandPoint] = []


class DemandResponse(BaseModel):
    meta: MetricsMeta
    data: DemandData


# ---------------------------------------------------------------------------
# §3.7 — Distribution
# ---------------------------------------------------------------------------

class DistributionItem(BaseModel):
    key: str
    label: str
    count: int
    share: float


class DistributionData(BaseModel):
    distribution: list[DistributionItem] = []


class DistributionResponse(BaseModel):
    meta: MetricsMeta
    data: DistributionData


# ---------------------------------------------------------------------------
# §3.8 — Overview
# ---------------------------------------------------------------------------

class OverviewSalary(BaseModel):
    median: float | None = None
    p25: float | None = None
    p75: float | None = None


class OverviewSkillItem(BaseModel):
    skill: str
    share: float


class OverviewEmployerItem(BaseModel):
    name: str
    count: int


class OverviewGradeItem(BaseModel):
    key: str
    share: float


class OverviewData(BaseModel):
    salary: OverviewSalary = OverviewSalary()
    total_vacancies: int = 0
    salary_disclosure_rate: float | None = None
    top_skills: list[OverviewSkillItem] = []
    top_employers: list[OverviewEmployerItem] = []
    grade_distribution: list[OverviewGradeItem] = []
    demand_growth_mom: float | None = None


class OverviewResponse(BaseModel):
    meta: MetricsMeta
    data: OverviewData
