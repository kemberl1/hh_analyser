"""Tests for Phase 4 — metrics API endpoints.

Tests endpoint responses match the contract structure from docs/06-api-contract.md.
Uses the existing test client (conftest.py) and mocks the aggregation service
to return controlled data without hitting a real database.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

MOCK_SALARY_DATA = {
    "count": 100,
    "total_count": 200,
    "median": 220000.0,
    "min": 90000.0,
    "max": 450000.0,
    "mean": 228500.0,
    "percentiles": {
        "p10": 130000.0,
        "p25": 170000.0,
        "p50": 220000.0,
        "p75": 280000.0,
        "p90": 340000.0,
    },
    "range_avg": {"from": 195000.0, "to": 255000.0},
    "salary_disclosure_rate": 0.5,
    "low_confidence": False,
}

MOCK_SKILLS_DATA = {
    "skills": [
        {"skill": "React", "canonical": "react", "count": 80, "share": 0.8},
        {"skill": "TypeScript", "canonical": "typescript", "count": 70, "share": 0.7},
    ],
    "sample_size": 100,
    "low_confidence": False,
}

MOCK_EMPLOYERS_DATA = {
    "employers": [
        {"employer_id": 1234, "name": "Yandex", "count": 30, "share": 0.15},
        {"employer_id": 5678, "name": "Sber", "count": 20, "share": 0.1},
    ],
    "top10_concentration": 0.25,
    "sample_size": 200,
    "low_confidence": False,
}

MOCK_DEMAND_DATA = {
    "points": [
        {"period_start": "2026-04-01", "count": 180, "growth": None},
        {"period_start": "2026-05-01", "count": 200, "growth": 0.1111},
    ],
    "low_confidence": False,
}

MOCK_SALARY_TS_DATA = {
    "points": [
        {"period_start": "2026-04-01", "median": 210000.0,
            "p25": 160000.0, "p75": 270000.0, "count": 180},
        {"period_start": "2026-05-01", "median": 220000.0,
            "p25": 170000.0, "p75": 280000.0, "count": 200},
    ],
    "low_confidence": False,
}

MOCK_DISTRIBUTION_DATA = {
    "distribution": [
        {"key": "junior", "label": "Junior", "count": 40, "share": 0.2},
        {"key": "middle", "label": "Middle", "count": 100, "share": 0.5},
        {"key": "senior", "label": "Senior", "count": 60, "share": 0.3},
    ],
    "sample_size": 200,
    "low_confidence": False,
}

MOCK_COOCCURRENCE_DATA = {
    "pairs": [
        {"a": "React", "b": "TypeScript", "count": 60, "share": 0.3},
    ],
    "sample_size": 200,
    "low_confidence": False,
}

MOCK_OVERVIEW_DATA = {
    "salary": {"median": 220000.0, "p25": 170000.0, "p75": 280000.0},
    "total_vacancies": 200,
    "salary_disclosure_rate": 0.5,
    "top_skills": [{"skill": "React", "share": 0.8}],
    "top_employers": [{"name": "Yandex", "count": 30}],
    "grade_distribution": [{"key": "middle", "share": 0.5}],
    "demand_growth_mom": 0.1111,
    "low_confidence": False,
}


# ═══════════════════════════════════════════════════════════════════════════
# Helper to mock grade resolution
# ═══════════════════════════════════════════════════════════════════════════

def _mock_resolve_grade_id(grade_code):
    """Simulate _resolve_grade_id: map code→id."""
    mapping = {"junior": 1, "middle": 2, "senior": 3}
    return mapping.get(grade_code)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSalaryEndpoint:
    """§3.1 GET /api/v1/metrics/salary"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_salary_metrics", new_callable=AsyncMock, return_value=MOCK_SALARY_DATA)
    async def test_salary_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/salary")
        assert resp.status_code == 200
        body = resp.json()
        # Contract structure
        assert "meta" in body
        assert "data" in body
        assert body["meta"]["period"] == "month"
        assert body["meta"]["grade"] == "all"
        assert body["meta"]["currency"] == "RUB"
        assert body["meta"]["salary_basis"] == "net"
        assert body["data"]["median"] == 220000.0
        assert body["data"]["percentiles"]["p50"] == 220000.0
        assert body["data"]["salary_disclosure_rate"] == 0.5
        assert body["data"]["range_avg"]["from"] == 195000.0

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=2)
    @patch("app.api.v1.endpoints.metrics.compute_salary_metrics", new_callable=AsyncMock, return_value=MOCK_SALARY_DATA)
    async def test_salary_with_grade_filter(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/salary?grade=middle")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["grade"] == "middle"

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_salary_metrics", new_callable=AsyncMock, return_value=MOCK_SALARY_DATA)
    async def test_salary_with_date_range(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/salary?date_from=2026-05-01&date_to=2026-05-31")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["date_from"] == "2026-05-01"
        assert body["meta"]["date_to"] == "2026-05-31"

    @pytest.mark.asyncio
    async def test_salary_invalid_period(self, client):
        resp = await client.get("/api/v1/metrics/salary?period=quarter")
        assert resp.status_code == 422


class TestSalaryTimeseriesEndpoint:
    """§3.2 GET /api/v1/metrics/salary/timeseries"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_salary_timeseries", new_callable=AsyncMock, return_value=MOCK_SALARY_TS_DATA)
    async def test_salary_timeseries_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/salary/timeseries")
        assert resp.status_code == 200
        body = resp.json()
        assert "meta" in body
        assert "data" in body
        assert "points" in body["data"]
        assert len(body["data"]["points"]) == 2
        assert body["data"]["points"][0]["median"] == 210000.0


class TestSkillsEndpoint:
    """§3.3 GET /api/v1/metrics/skills"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_skills_metrics", new_callable=AsyncMock, return_value=MOCK_SKILLS_DATA)
    async def test_skills_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/skills")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "skills" in body["data"]
        assert len(body["data"]["skills"]) == 2
        assert body["data"]["skills"][0]["skill"] == "React"
        assert body["data"]["skills"][0]["share"] == 0.8

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_skills_metrics", new_callable=AsyncMock, return_value=MOCK_SKILLS_DATA)
    async def test_skills_with_limit(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/skills?limit=5")
        assert resp.status_code == 200


class TestCooccurrenceEndpoint:
    """§3.4 GET /api/v1/metrics/skills/cooccurrence"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_skill_cooccurrence", new_callable=AsyncMock, return_value=MOCK_COOCCURRENCE_DATA)
    async def test_cooccurrence_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/skills/cooccurrence")
        assert resp.status_code == 200
        body = resp.json()
        assert "pairs" in body["data"]
        assert len(body["data"]["pairs"]) == 1
        assert body["data"]["pairs"][0]["a"] == "React"


class TestEmployersEndpoint:
    """§3.5 GET /api/v1/metrics/employers"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_employers_metrics", new_callable=AsyncMock, return_value=MOCK_EMPLOYERS_DATA)
    async def test_employers_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/employers")
        assert resp.status_code == 200
        body = resp.json()
        assert "employers" in body["data"]
        assert body["data"]["top10_concentration"] == 0.25
        assert body["data"]["employers"][0]["name"] == "Yandex"


class TestDemandEndpoint:
    """§3.6 GET /api/v1/metrics/demand"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_demand_metrics", new_callable=AsyncMock, return_value=MOCK_DEMAND_DATA)
    async def test_demand_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/demand")
        assert resp.status_code == 200
        body = resp.json()
        assert "points" in body["data"]
        assert len(body["data"]["points"]) == 2
        assert body["data"]["points"][1]["growth"] == 0.1111


class TestDistributionEndpoint:
    """§3.7 GET /api/v1/metrics/distribution"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_distribution", new_callable=AsyncMock, return_value=MOCK_DISTRIBUTION_DATA)
    async def test_distribution_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/distribution?by=grade")
        assert resp.status_code == 200
        body = resp.json()
        assert "distribution" in body["data"]
        assert len(body["data"]["distribution"]) == 3
        assert body["data"]["distribution"][1]["key"] == "middle"

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_distribution", new_callable=AsyncMock, return_value=MOCK_DISTRIBUTION_DATA)
    async def test_distribution_format(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/distribution?by=format")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_distribution_invalid_by(self, client):
        resp = await client.get("/api/v1/metrics/distribution?by=invalid")
        assert resp.status_code == 422


class TestOverviewEndpoint:
    """§3.8 GET /api/v1/metrics/overview"""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_overview", new_callable=AsyncMock, return_value=MOCK_OVERVIEW_DATA)
    async def test_overview_200(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert "meta" in body
        assert "data" in body
        assert body["data"]["salary"]["median"] == 220000.0
        assert body["data"]["total_vacancies"] == 200
        assert body["data"]["salary_disclosure_rate"] == 0.5
        assert len(body["data"]["top_skills"]) == 1
        assert body["data"]["top_skills"][0]["skill"] == "React"
        assert body["data"]["demand_growth_mom"] == 0.1111

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_overview", new_callable=AsyncMock, return_value=MOCK_OVERVIEW_DATA)
    async def test_overview_with_period_filter(self, mock_compute, mock_grade, client):
        resp = await client.get("/api/v1/metrics/overview?period=week&grade=junior")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["period"] == "week"
        assert body["meta"]["grade"] == "junior"


# ═══════════════════════════════════════════════════════════════════════════
# Combined: filter parameter forwarding tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFilterParameters:
    """Verify all common filter parameters are accepted without errors."""

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_salary_metrics", new_callable=AsyncMock, return_value=MOCK_SALARY_DATA)
    async def test_all_period_types(self, mock_compute, mock_grade, client):
        for period in ["day", "week", "month", "year"]:
            resp = await client.get(f"/api/v1/metrics/salary?period={period}")
            assert resp.status_code == 200, f"Failed for period={period}"
            assert resp.json()["meta"]["period"] == period

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.metrics._resolve_grade_id", new_callable=AsyncMock, return_value=None)
    @patch("app.api.v1.endpoints.metrics.compute_salary_metrics", new_callable=AsyncMock, return_value=MOCK_SALARY_DATA)
    async def test_all_grade_types(self, mock_compute, mock_grade, client):
        for grade in ["junior", "middle", "senior", "all"]:
            resp = await client.get(f"/api/v1/metrics/salary?grade={grade}")
            assert resp.status_code == 200, f"Failed for grade={grade}"
            assert resp.json()["meta"]["grade"] == grade
