"""Tests for Phase 4 — aggregation service, period helpers, metric computations.

Tests use controlled data with known expected outputs.
No real network requests or external databases.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.aggregation import (
    LOW_CONFIDENCE_THRESHOLD,
    MSK_TZ,
    compute_demand_metrics,
    compute_distribution,
    compute_employers_metrics,
    compute_overview,
    compute_salary_metrics,
    compute_salary_timeseries,
    compute_skill_cooccurrence,
    compute_skills_metrics,
    enumerate_periods,
    period_end_for,
    period_start_for,
)


# ═══════════════════════════════════════════════════════════════════════════
# Period helper tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPeriodHelpers:
    """Test period bucketing utility functions."""

    def test_period_start_day(self):
        assert period_start_for(date(2026, 5, 15), "day") == date(2026, 5, 15)

    def test_period_start_week_monday(self):
        # 2026-05-15 is a Friday → week starts Monday 2026-05-11
        assert period_start_for(date(2026, 5, 15), "week") == date(2026, 5, 11)

    def test_period_start_week_on_monday(self):
        # 2026-05-11 is Monday
        assert period_start_for(date(2026, 5, 11), "week") == date(2026, 5, 11)

    def test_period_start_month(self):
        assert period_start_for(date(2026, 5, 15), "month") == date(2026, 5, 1)

    def test_period_start_year(self):
        assert period_start_for(date(2026, 5, 15), "year") == date(2026, 1, 1)

    def test_period_end_day(self):
        assert period_end_for(date(2026, 5, 15), "day") == date(2026, 5, 16)

    def test_period_end_week(self):
        assert period_end_for(date(2026, 5, 11), "week") == date(2026, 5, 18)

    def test_period_end_month(self):
        assert period_end_for(date(2026, 5, 1), "month") == date(2026, 6, 1)

    def test_period_end_month_december(self):
        assert period_end_for(date(2026, 12, 1), "month") == date(2027, 1, 1)

    def test_period_end_year(self):
        assert period_end_for(date(2026, 1, 1), "year") == date(2027, 1, 1)

    def test_enumerate_periods_months(self):
        periods = enumerate_periods(
            date(2026, 3, 1), date(2026, 5, 31), "month")
        assert periods == [date(2026, 3, 1), date(
            2026, 4, 1), date(2026, 5, 1)]

    def test_enumerate_periods_weeks(self):
        periods = enumerate_periods(
            date(2026, 5, 1), date(2026, 5, 14), "week")
        # May 1 is Friday → week starts Apr 27
        assert len(periods) >= 2

    def test_enumerate_periods_single_day(self):
        periods = enumerate_periods(
            date(2026, 5, 15), date(2026, 5, 15), "day")
        assert periods == [date(2026, 5, 15)]

    def test_period_start_invalid(self):
        with pytest.raises(ValueError, match="Unknown period_type"):
            period_start_for(date(2026, 5, 15), "quarter")

    def test_period_end_invalid(self):
        with pytest.raises(ValueError, match="Unknown period_type"):
            period_end_for(date(2026, 5, 15), "quarter")


# ═══════════════════════════════════════════════════════════════════════════
# Salary metric computation tests (M1)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_salary(
    point_estimates: list[float],
    froms: list[float | None] | None = None,
    tos: list[float | None] | None = None,
    total_count: int | None = None,
):
    """Create a mock AsyncSession that returns controlled salary data."""
    if total_count is None:
        total_count = len(point_estimates) + 5  # some vacancies without salary

    if froms is None:
        froms = [v * 0.8 for v in point_estimates]
    if tos is None:
        tos = [v * 1.2 for v in point_estimates]

    rows = [
        (pe, fr, to)
        for pe, fr, to in zip(point_estimates, froms, tos)
    ]

    session = AsyncMock()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # Total count query
            result.scalar.return_value = total_count
        else:
            # Salary rows query
            result.all.return_value = rows
        return result

    session.execute = mock_execute
    return session


class TestSalaryMetrics:
    """Test M1 salary metrics computation with known data."""

    @pytest.mark.asyncio
    async def test_basic_salary_metrics(self):
        """Known dataset → known median, min, max, mean, percentiles."""
        estimates = [100000, 150000, 200000, 250000, 300000]
        session = _make_mock_session_for_salary(estimates, total_count=10)

        result = await compute_salary_metrics(session)

        assert result["count"] == 5
        assert result["total_count"] == 10
        assert result["median"] == 200000.0
        assert result["min"] == 100000.0
        assert result["max"] == 300000.0
        assert result["mean"] == 200000.0
        assert result["salary_disclosure_rate"] == 0.5
        assert "percentiles" in result
        assert result["percentiles"]["p50"] == 200000.0
        # p25 should be between 100k and 200k
        assert 100000 <= result["percentiles"]["p25"] <= 200000
        # p75 should be between 200k and 300k
        assert 200000 <= result["percentiles"]["p75"] <= 300000

    @pytest.mark.asyncio
    async def test_salary_metrics_single_value(self):
        """Single salary value → median = min = max = that value."""
        estimates = [200000]
        session = _make_mock_session_for_salary(estimates, total_count=5)

        result = await compute_salary_metrics(session)

        assert result["count"] == 1
        assert result["median"] == 200000.0
        assert result["min"] == 200000.0
        assert result["max"] == 200000.0
        assert result["mean"] == 200000.0
        assert result["low_confidence"] is True  # n < 30

    @pytest.mark.asyncio
    async def test_salary_metrics_empty(self):
        """No salary data → all None, disclosure_rate = 0."""
        session = _make_mock_session_for_salary([], total_count=10)

        result = await compute_salary_metrics(session)

        assert result["count"] == 0
        assert result["median"] is None
        assert result["min"] is None
        assert result["max"] is None
        assert result["mean"] is None
        assert result["salary_disclosure_rate"] == 0.0
        assert result["low_confidence"] is True

    @pytest.mark.asyncio
    async def test_salary_metrics_no_vacancies(self):
        """No vacancies at all → disclosure rate is None."""
        session = _make_mock_session_for_salary([], total_count=0)

        result = await compute_salary_metrics(session)

        assert result["count"] == 0
        assert result["total_count"] == 0
        assert result["salary_disclosure_rate"] is None

    @pytest.mark.asyncio
    async def test_salary_percentiles_interpolation(self):
        """Verify numpy linear interpolation for percentiles."""
        # 10 evenly spaced values: 100k to 1M
        estimates = [100000 * (i + 1) for i in range(10)]
        session = _make_mock_session_for_salary(estimates, total_count=10)

        result = await compute_salary_metrics(session)

        # p50 = median of [100k..1M]
        expected_median = np.median(estimates)
        assert result["median"] == round(float(expected_median), 2)

        # p10 via numpy
        expected_p10 = np.percentile(estimates, 10)
        assert result["percentiles"]["p10"] == round(float(expected_p10), 2)

    @pytest.mark.asyncio
    async def test_salary_low_confidence_threshold(self):
        """Sample < 30 → low_confidence=True; ≥ 30 → False."""
        # Below threshold
        estimates_small = [200000] * 10
        session = _make_mock_session_for_salary(
            estimates_small, total_count=10)
        result = await compute_salary_metrics(session)
        assert result["low_confidence"] is True

        # At threshold
        estimates_large = [200000] * LOW_CONFIDENCE_THRESHOLD
        session = _make_mock_session_for_salary(
            estimates_large, total_count=30)
        result = await compute_salary_metrics(session)
        assert result["low_confidence"] is False

    @pytest.mark.asyncio
    async def test_salary_range_avg(self):
        """range_avg should be mean of from/to values."""
        estimates = [100000, 200000]
        froms = [80000, 160000]
        tos = [120000, 240000]
        session = _make_mock_session_for_salary(
            estimates, froms=froms, tos=tos, total_count=5)

        result = await compute_salary_metrics(session)

        assert result["range_avg"]["from"] == 120000.0  # (80k + 160k) / 2
        assert result["range_avg"]["to"] == 180000.0  # (120k + 240k) / 2


# ═══════════════════════════════════════════════════════════════════════════
# Skills metric tests (M2)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_skills(
    skill_rows: list[tuple[str, str, int]],
    total_count: int,
):
    """Mock session returning skill count rows.

    skill_rows: [(display_name, canonical_name, count), ...]
    """
    session = AsyncMock()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar.return_value = total_count
        else:
            result.all.return_value = skill_rows
        return result

    session.execute = mock_execute
    return session


class TestSkillsMetrics:
    """Test M2 skills metrics."""

    @pytest.mark.asyncio
    async def test_skills_basic(self):
        skill_rows = [
            ("React", "react", 40),
            ("TypeScript", "typescript", 35),
            ("JavaScript", "javascript", 30),
        ]
        session = _make_mock_session_for_skills(skill_rows, total_count=50)

        result = await compute_skills_metrics(session)

        assert len(result["skills"]) == 3
        assert result["skills"][0]["skill"] == "React"
        assert result["skills"][0]["count"] == 40
        assert result["skills"][0]["share"] == 0.8  # 40/50
        assert result["sample_size"] == 50

    @pytest.mark.asyncio
    async def test_skills_empty(self):
        session = _make_mock_session_for_skills([], total_count=0)

        result = await compute_skills_metrics(session)

        assert result["skills"] == []
        assert result["sample_size"] == 0
        assert result["low_confidence"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Employer metric tests (M3)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_employers(
    emp_rows: list[tuple[int, int, str, int]],
    total_count: int,
):
    """emp_rows: [(id, hh_employer_id, name, count), ...]"""
    session = AsyncMock()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar.return_value = total_count
        else:
            result.all.return_value = emp_rows
        return result

    session.execute = mock_execute
    return session


class TestEmployersMetrics:
    """Test M3 employer metrics."""

    @pytest.mark.asyncio
    async def test_employers_basic(self):
        emp_rows = [
            (1, 1001, "Yandex", 30),
            (2, 1002, "Sber", 20),
        ]
        session = _make_mock_session_for_employers(emp_rows, total_count=100)

        result = await compute_employers_metrics(session)

        assert len(result["employers"]) == 2
        assert result["employers"][0]["name"] == "Yandex"
        assert result["employers"][0]["share"] == 0.3
        assert result["top10_concentration"] == 0.5  # (30+20)/100

    @pytest.mark.asyncio
    async def test_employers_empty(self):
        session = _make_mock_session_for_employers([], total_count=0)

        result = await compute_employers_metrics(session)

        assert result["employers"] == []
        assert result["top10_concentration"] == 0.0
        assert result["low_confidence"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Demand (timeseries) metric tests (M4)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_demand(
    published_dates: list[datetime],
):
    """Mock session returning published_at values."""
    session = AsyncMock()
    rows = [(d,) for d in published_dates]

    async def mock_execute(stmt):
        result = MagicMock()
        result.all.return_value = rows
        return result

    session.execute = mock_execute
    return session


class TestDemandMetrics:
    """Test M4 demand (vacancy count) timeseries."""

    @pytest.mark.asyncio
    async def test_demand_monthly_buckets(self):
        """Vacancies in March and April → two monthly buckets."""
        dates = [
            datetime(2026, 3, 10, tzinfo=MSK_TZ),
            datetime(2026, 3, 15, tzinfo=MSK_TZ),
            datetime(2026, 3, 20, tzinfo=MSK_TZ),
            datetime(2026, 4, 5, tzinfo=MSK_TZ),
            datetime(2026, 4, 10, tzinfo=MSK_TZ),
        ]
        session = _make_mock_session_for_demand(dates)

        result = await compute_demand_metrics(session, period_type="month")

        assert len(result["points"]) == 2
        # March: 3 vacancies
        assert result["points"][0]["period_start"] == "2026-03-01"
        assert result["points"][0]["count"] == 3
        assert result["points"][0]["growth"] is None  # first period
        # April: 2 vacancies, growth = (2-3)/3
        assert result["points"][1]["period_start"] == "2026-04-01"
        assert result["points"][1]["count"] == 2
        assert abs(result["points"][1]["growth"] - (-1 / 3)) < 0.01

    @pytest.mark.asyncio
    async def test_demand_empty(self):
        session = _make_mock_session_for_demand([])

        result = await compute_demand_metrics(session, period_type="month")

        assert result["points"] == []
        assert result["low_confidence"] is True

    @pytest.mark.asyncio
    async def test_demand_weekly_buckets(self):
        """Week bucketing groups by ISO week start (Monday)."""
        # Mon May 11 and Wed May 13 → same week bucket
        dates = [
            datetime(2026, 5, 11, 10, 0, tzinfo=MSK_TZ),
            datetime(2026, 5, 13, 10, 0, tzinfo=MSK_TZ),
        ]
        session = _make_mock_session_for_demand(dates)

        result = await compute_demand_metrics(session, period_type="week")

        assert len(result["points"]) == 1
        assert result["points"][0]["count"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# Salary timeseries tests (M4.2)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_salary_ts(
    rows: list[tuple[datetime, float]],
):
    """rows: [(published_at, point_estimate), ...]"""
    session = AsyncMock()

    async def mock_execute(stmt):
        result = MagicMock()
        result.all.return_value = rows
        return result

    session.execute = mock_execute
    return session


class TestSalaryTimeseries:
    """Test M4.2 salary timeseries."""

    @pytest.mark.asyncio
    async def test_salary_ts_monthly(self):
        rows = [
            (datetime(2026, 3, 10, tzinfo=MSK_TZ), 200000),
            (datetime(2026, 3, 20, tzinfo=MSK_TZ), 250000),
            (datetime(2026, 4, 5, tzinfo=MSK_TZ), 300000),
        ]
        session = _make_mock_session_for_salary_ts(rows)

        result = await compute_salary_timeseries(session, period_type="month")

        assert len(result["points"]) == 2
        # March: median of (200k, 250k) = 225k
        assert result["points"][0]["median"] == 225000.0
        assert result["points"][0]["count"] == 2
        # April: median of (300k) = 300k
        assert result["points"][1]["median"] == 300000.0

    @pytest.mark.asyncio
    async def test_salary_ts_empty(self):
        session = _make_mock_session_for_salary_ts([])

        result = await compute_salary_timeseries(session, period_type="month")

        assert result["points"] == []
        assert result["low_confidence"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Distribution tests (M5.1–M5.3)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_distribution(
    rows: list[tuple[str, str, int]],
):
    """rows: [(key, label, count), ...]"""
    session = AsyncMock()

    async def mock_execute(stmt):
        result = MagicMock()
        result.all.return_value = rows
        return result

    session.execute = mock_execute
    return session


class TestDistribution:
    """Test M5.1–M5.3 distribution metrics."""

    @pytest.mark.asyncio
    async def test_grade_distribution(self):
        rows = [
            ("junior", "Junior", 200),
            ("middle", "Middle", 500),
            ("senior", "Senior", 300),
        ]
        session = _make_mock_session_for_distribution(rows)

        result = await compute_distribution(session, by="grade")

        assert len(result["distribution"]) == 3
        assert result["distribution"][0]["key"] == "junior"
        assert result["distribution"][0]["share"] == 0.2  # 200/1000
        assert result["distribution"][1]["share"] == 0.5
        assert result["sample_size"] == 1000

    @pytest.mark.asyncio
    async def test_distribution_empty(self):
        session = _make_mock_session_for_distribution([])

        result = await compute_distribution(session, by="grade")

        assert result["distribution"] == []
        assert result["sample_size"] == 0
        assert result["low_confidence"] is True

    @pytest.mark.asyncio
    async def test_distribution_with_none_key(self):
        """Unknown values get key='unknown'."""
        rows = [
            (None, None, 50),
            ("remote", "remote", 30),
        ]
        session = _make_mock_session_for_distribution(rows)

        result = await compute_distribution(session, by="format")

        assert result["distribution"][0]["key"] == "unknown"
        assert result["distribution"][0]["label"] == "Unknown"

    @pytest.mark.asyncio
    async def test_distribution_invalid_by(self):
        session = AsyncMock()
        with pytest.raises(ValueError, match="Unknown distribution dimension"):
            await compute_distribution(session, by="invalid")


# ═══════════════════════════════════════════════════════════════════════════
# Skill co-occurrence tests (M5.4)
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_session_for_cooccurrence(
    vacancy_skill_rows: list[tuple[int, str]],
    total_count: int,
):
    """vacancy_skill_rows: [(vacancy_id, skill_display_name), ...]"""
    session = AsyncMock()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar.return_value = total_count
        else:
            result.all.return_value = vacancy_skill_rows
        return result

    session.execute = mock_execute
    return session


class TestSkillCooccurrence:
    """Test M5.4 skill co-occurrence."""

    @pytest.mark.asyncio
    async def test_cooccurrence_basic(self):
        rows = [
            (1, "React"),
            (1, "TypeScript"),
            (2, "React"),
            (2, "TypeScript"),
            (2, "Redux"),
            (3, "Vue"),
        ]
        session = _make_mock_session_for_cooccurrence(rows, total_count=3)

        result = await compute_skill_cooccurrence(session)

        # React+TypeScript appears in vacancies 1 and 2 → count=2
        pairs = result["pairs"]
        rt_pair = next((p for p in pairs if set(
            [p["a"], p["b"]]) == {"React", "TypeScript"}), None)
        assert rt_pair is not None
        assert rt_pair["count"] == 2

    @pytest.mark.asyncio
    async def test_cooccurrence_empty(self):
        session = _make_mock_session_for_cooccurrence([], total_count=0)

        result = await compute_skill_cooccurrence(session)

        assert result["pairs"] == []
        assert result["low_confidence"] is True

    @pytest.mark.asyncio
    async def test_cooccurrence_single_skill_vacancy(self):
        """Vacancy with only one skill → no pairs."""
        rows = [
            (1, "React"),
        ]
        session = _make_mock_session_for_cooccurrence(rows, total_count=1)

        result = await compute_skill_cooccurrence(session)

        assert result["pairs"] == []
