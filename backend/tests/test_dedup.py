"""Tests for dedup/idempotent upsert — no DB required (logic-level tests).

For full integration tests with DB, use test_integration.py.
These tests verify the persistence logic contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.normalizer import Normalizer, NormalizedVacancy, NormalizedSalary
from app.services.source_interface import RawVacancy


class TestDedupLogic:
    """Test that normalization produces deterministic output for same input."""

    def setup_method(self):
        self.normalizer = Normalizer(ndfl_rate=0.13)

    def test_same_input_same_output(self):
        """Same raw vacancy → same normalized output (deterministic)."""
        raw = RawVacancy(
            hh_vacancy_id=100,
            title="Junior Frontend Developer",
            salary_from=80000,
            salary_to=120000,
            salary_currency="RUR",
            salary_gross=False,
            experience_raw="noExperience",
            skills=["React", "JavaScript"],
        )
        nv1 = self.normalizer.normalize(raw)
        nv2 = self.normalizer.normalize(raw)

        assert nv1.hh_vacancy_id == nv2.hh_vacancy_id
        assert nv1.title == nv2.title
        assert nv1.grade_code == nv2.grade_code
        assert nv1.salary.point_estimate_rub_net == nv2.salary.point_estimate_rub_net
        assert nv1.skills == nv2.skills

    def test_hh_vacancy_id_preserved(self):
        """hh_vacancy_id is carried through normalization (dedup key)."""
        raw = RawVacancy(hh_vacancy_id=999, title="Test")
        nv = self.normalizer.normalize(raw)
        assert nv.hh_vacancy_id == 999

    def test_published_at_from_raw(self):
        """published_at comes from raw data (not current time) when available."""
        dt = datetime(2026, 6, 1, tzinfo=timezone.utc)
        raw = RawVacancy(hh_vacancy_id=200, title="Test", published_at=dt)
        nv = self.normalizer.normalize(raw)
        assert nv.published_at == dt

    def test_published_at_fallback_to_now(self):
        """published_at falls back to now() when not available."""
        raw = RawVacancy(hh_vacancy_id=201, title="Test", published_at=None)
        nv = self.normalizer.normalize(raw)
        assert nv.published_at is not None
        # Should be close to now
        diff = abs((datetime.now(timezone.utc) -
                   nv.published_at).total_seconds())
        assert diff < 5  # within 5 seconds

    def test_repeated_normalization_stability(self):
        """Multiple normalizations of same data produce stable results."""
        raw = RawVacancy(
            hh_vacancy_id=300,
            title="Senior Frontend Developer",
            salary_from=300000,
            salary_to=450000,
            salary_currency="RUR",
            salary_gross=True,
            skills=["Vue.js", "TypeScript", "vue.js"],  # duplicate
        )
        results = [self.normalizer.normalize(raw) for _ in range(10)]
        # All should be identical
        for nv in results:
            assert nv.grade_code == "senior"
            assert nv.salary.point_estimate_rub_net == results[0].salary.point_estimate_rub_net
            assert nv.skills == ["vue.js", "typescript"]


class TestSourceTypePreserved:
    """Test that source_type and raw data are preserved through normalization."""

    def test_html_source(self):
        raw = RawVacancy(
            hh_vacancy_id=400, title="Test",
            source_type="html", raw_html="<html>...</html>",
        )
        nv = Normalizer().normalize(raw)
        assert nv.source_type == "html"
        assert nv.raw_html == "<html>...</html>"
        assert nv.raw_payload is None

    def test_api_source(self):
        raw = RawVacancy(
            hh_vacancy_id=401, title="Test",
            source_type="api", raw_payload={"id": 401, "name": "Test"},
        )
        nv = Normalizer().normalize(raw)
        assert nv.source_type == "api"
        assert nv.raw_payload == {"id": 401, "name": "Test"}
        assert nv.raw_html is None
