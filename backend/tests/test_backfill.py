"""Tests for Phase 8 — Backfill service with segmented search."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.backfill import (
    BACKFILL_SEGMENT_THRESHOLD,
    ITEMS_PER_PAGE,
    BackfillService,
    BackfillStats,
    DateSegment,
    run_backfill,
)
from app.services.relevance import RelevanceFilter, RelevanceResult, TermEntry
from app.services.seed import POSITIVE_TERMS, STOP_TERMS
from app.services.source_interface import RawVacancy


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_relevance_filter() -> RelevanceFilter:
    """Build a filter with seed terms (no DB needed)."""
    terms = []
    for term, scope, weight in POSITIVE_TERMS:
        terms.append(
            TermEntry(term=term.lower(), kind="positive",
                      field_scope=scope, weight=weight)
        )
    for term, scope, weight in STOP_TERMS:
        terms.append(
            TermEntry(term=term.lower(), kind="stop",
                      field_scope=scope, weight=weight)
        )
    return RelevanceFilter(terms=terms)


def _make_vacancy_api_response(
    vac_id: int,
    title: str = "Frontend Developer (React)",
    *,
    description: str = "React, JavaScript, TypeScript SPA разработка",
    skills: list[str] | None = None,
    published_at: str = "2026-06-01T12:00:00+0300",
) -> dict[str, Any]:
    """Build a mock hh.ru vacancy detail response."""
    if skills is None:
        skills = ["React", "JavaScript", "TypeScript"]
    return {
        "id": str(vac_id),
        "name": title,
        "alternate_url": f"https://hh.ru/vacancy/{vac_id}",
        "employer": {"id": "100", "name": "TestCorp", "alternate_url": None},
        "salary": {"from": 150000, "to": 250000, "currency": "RUR", "gross": True},
        "experience": {"id": "between1And3"},
        "schedule": {"id": "remote"},
        "key_skills": [{"name": s} for s in skills],
        "description": description,
        "published_at": published_at,
        "area": {"name": "Москва"},
    }


def _make_search_response(
    vacancy_ids: list[int],
    found: int | None = None,
    pages: int = 1,
) -> dict[str, Any]:
    """Build a mock search results page response."""
    if found is None:
        found = len(vacancy_ids)
    return {
        "items": [{"id": str(vid)} for vid in vacancy_ids],
        "found": found,
        "pages": pages,
        "per_page": ITEMS_PER_PAGE,
    }


# ── DateSegment unit tests ─────────────────────────────────────────────────


class TestDateSegment:
    """Tests for the DateSegment dataclass."""

    def test_duration(self):
        now = datetime.now(timezone.utc)
        seg = DateSegment(now - timedelta(days=10), now)
        assert seg.duration == timedelta(days=10)

    def test_split_produces_two_halves(self):
        now = datetime.now(timezone.utc)
        seg = DateSegment(now - timedelta(days=10), now)
        left, right = seg.split()
        # Left covers first 5 days, right covers last 5 days
        assert left.date_from == seg.date_from
        assert right.date_to == seg.date_to
        assert left.date_to == right.date_from
        # Halves approximately equal
        delta = abs(left.duration - right.duration)
        assert delta < timedelta(seconds=1)

    def test_split_of_split(self):
        """Recursive splitting produces 4 segments."""
        now = datetime.now(timezone.utc)
        root = DateSegment(now - timedelta(days=8), now)
        left, right = root.split()
        ll, lr = left.split()
        rl, rr = right.split()
        # Each segment ~2 days
        for seg in (ll, lr, rl, rr):
            assert timedelta(days=1, hours=23) < seg.duration < timedelta(
                days=2, seconds=2)

    def test_repr(self):
        seg = DateSegment(
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
        )
        r = repr(seg)
        assert "2026-01-01" in r
        assert "2026-01-15" in r


# ── BackfillStats tests ───────────────────────────────────────────────────


class TestBackfillStats:
    def test_defaults(self):
        stats = BackfillStats()
        assert stats.segments_processed == 0
        assert stats.created == 0
        assert stats.filtered == 0
        assert stats.errors == 0


# ── BackfillService integration tests (mocked HTTP) ───────────────────────


class TestBackfillServiceSegmentation:
    """Tests the recursive segmentation logic."""

    @pytest.mark.asyncio
    async def test_small_segment_no_split(self):
        """If found < threshold, segment is not split."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=7,
            segment_threshold=1900,
        )

        # Mock: segment has 500 vacancies
        with patch.object(
            service, "_get_segment_found_count", new_callable=AsyncMock
        ) as mock_count, patch.object(
            service, "_fetch_search_page", new_callable=AsyncMock
        ) as mock_page:
            mock_count.return_value = 500
            # 5 pages of 100 (id, url) pairs each
            mock_page.side_effect = [
                [(j, f"https://hh.ru/vacancy/{j}")
                 for j in range(i * 100, (i + 1) * 100)]
                for i in range(5)
            ]

            now = datetime.now(timezone.utc)
            seg = DateSegment(now - timedelta(days=7), now)
            await service._collect_segment_ids(seg)

        assert service._stats.segments_processed == 1
        assert service._stats.segments_split == 0
        assert len(service._seen_ids) == 500

    @pytest.mark.asyncio
    async def test_large_segment_splits(self):
        """If found >= threshold, segment is split recursively."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=10,
            segment_threshold=100,  # low threshold to trigger splitting
        )

        call_count = 0

        async def fake_found_count(segment: DateSegment) -> int:
            nonlocal call_count
            call_count += 1
            # Root segment and first-level halves return 150 (above threshold)
            # Second-level (quarter-segments) return 50 (below threshold)
            if segment.duration > timedelta(days=3):
                return 150
            return 50

        async def fake_search_page(
            segment: DateSegment, page: int
        ) -> list[tuple[int, str]]:
            # Return a small set of (id, url) pairs per leaf segment
            base = int(segment.date_from.timestamp()) % 10000
            return [
                (base + page * 100 + i,
                 f"https://hh.ru/vacancy/{base + page * 100 + i}")
                for i in range(50)
            ]

        with patch.object(
            service, "_get_segment_found_count", side_effect=fake_found_count
        ), patch.object(
            service, "_fetch_search_page", side_effect=fake_search_page
        ):
            now = datetime.now(timezone.utc)
            seg = DateSegment(now - timedelta(days=10), now)
            await service._collect_segment_ids(seg)

        # Root splits once → 2 halves of 5 days, each splits → 4 leaf segments
        assert service._stats.segments_split >= 2
        assert service._stats.segments_processed >= 4
        assert len(service._seen_ids) > 0

    @pytest.mark.asyncio
    async def test_zero_found_no_pagination(self):
        """Segment with 0 vacancies: skip without pagination."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=5,
        )

        with patch.object(
            service, "_get_segment_found_count", new_callable=AsyncMock
        ) as mock_count, patch.object(
            service, "_fetch_search_page", new_callable=AsyncMock
        ) as mock_page:
            mock_count.return_value = 0

            seg = DateSegment(
                datetime.now(timezone.utc) - timedelta(days=5),
                datetime.now(timezone.utc),
            )
            await service._collect_segment_ids(seg)

            mock_page.assert_not_called()

        assert service._stats.segments_processed == 1
        assert len(service._seen_ids) == 0


class TestBackfillServiceDedup:
    """Tests global deduplication of vacancy IDs."""

    @pytest.mark.asyncio
    async def test_dedup_across_segments(self):
        """Same vacancy ID appearing in multiple segments is counted once."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=10,
            segment_threshold=100,
        )

        # Simulate two leaf segments returning overlapping IDs
        call_idx = [0]

        async def fake_found(seg):
            return 50  # below threshold, always leaf

        async def fake_page(seg, page):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return [(i, f"https://hh.ru/vacancy/{i}")
                        for i in (1, 2, 3, 4, 5)]
            else:
                # overlap: 4 and 5
                return [(i, f"https://hh.ru/vacancy/{i}")
                        for i in (4, 5, 6, 7, 8)]

        with patch.object(service, "_get_segment_found_count", side_effect=fake_found):
            with patch.object(service, "_fetch_search_page", side_effect=fake_page):
                now = datetime.now(timezone.utc)
                # Process two segments manually
                seg1 = DateSegment(now - timedelta(days=10),
                                   now - timedelta(days=5))
                seg2 = DateSegment(now - timedelta(days=5), now)
                await service._collect_segment_ids(seg1)
                await service._collect_segment_ids(seg2)

        # 5 + 5 collected, but only 8 unique
        assert len(service._seen_ids) == 8
        assert service._seen_ids == {1, 2, 3, 4, 5, 6, 7, 8}


class TestBackfillServiceRelevance:
    """Tests that relevance filter is applied during backfill."""

    @pytest.mark.asyncio
    async def test_irrelevant_vacancies_filtered(self):
        """Backend/DevOps vacancies are filtered out, not persisted."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=7,
        )

        # Pre-populate with IDs
        service._seen_ids = {1, 2, 3}

        # Mock detail fetching: 1 relevant, 2 irrelevant
        responses = {
            1: _make_vacancy_api_response(1, "Senior Frontend Developer (React)"),
            2: _make_vacancy_api_response(2, "Backend Developer (Java, Spring)"),
            3: _make_vacancy_api_response(3, "DevOps Engineer (Kubernetes, Docker)"),
        }

        async def fake_detail(vac_id):
            data = responses[vac_id]
            salary = data.get("salary", {})
            employer = data.get("employer", {})
            experience = data.get("experience", {})
            schedule = data.get("schedule", {})
            area = data.get("area", {})
            published_str = data.get("published_at", "")
            published_at = None
            if published_str:
                try:
                    published_at = datetime.fromisoformat(
                        published_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            return RawVacancy(
                hh_vacancy_id=vac_id,
                title=data["name"],
                url=data.get("alternate_url"),
                employer_name=employer.get("name"),
                employer_id=int(employer["id"]) if employer.get(
                    "id") else None,
                salary_from=float(salary["from"]) if salary.get(
                    "from") else None,
                salary_to=float(salary["to"]) if salary.get("to") else None,
                salary_currency=salary.get("currency"),
                salary_gross=salary.get("gross"),
                experience_raw=experience.get("id"),
                employment_format="remote",
                area_name=area.get("name"),
                published_at=published_at,
                description=data.get("description", ""),
                skills=[ks["name"] for ks in data.get("key_skills", [])],
                source_type="api",
                raw_payload=data,
            )

        with patch.object(
            service, "_fetch_vacancy_detail", side_effect=fake_detail
        ), patch(
            "app.services.backfill.create_ingestion_run", new_callable=AsyncMock
        ) as mock_create_run, patch(
            "app.services.backfill.finish_ingestion_run", new_callable=AsyncMock
        ), patch(
            "app.services.backfill.upsert_vacancy", new_callable=AsyncMock
        ) as mock_upsert, patch(
            "app.services.backfill.save_filtered_vacancy", new_callable=AsyncMock
        ) as mock_save_filtered, patch.object(
            service, "_collect_segment_ids", new_callable=AsyncMock
        ):
            # Create a mock run
            mock_run = MagicMock()
            mock_run.id = 1
            mock_create_run.return_value = mock_run
            mock_upsert.return_value = (True, False)

            # Set up client mock
            service._client = MagicMock()

            summary = await service.run()

        # Only 1 Frontend vacancy should pass the filter
        assert summary["created"] >= 1
        # At least 1 should be filtered (backend or devops)
        assert summary["filtered"] >= 1


class TestBackfillBuildSearchParams:
    """Tests for search parameter construction."""

    def test_params_include_date_range_html_default(self):
        """Default (HTML) source emits DD.MM.YYYY — the only format hh.ru
        HTML search honours (verified live)."""
        seg = DateSegment(
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
        params = BackfillService._build_search_params(
            seg, page=2, per_page=100)

        assert params["page"] == "2"
        assert params["per_page"] == "100"
        assert params["date_from"] == "01.01.2026"
        assert params["date_to"] == "15.01.2026"
        assert params["order_by"] == "publication_time"
        assert "text" in params
        assert "area" in params

    def test_params_date_range_api_iso(self):
        """API fallback path emits ISO 8601 date boundaries."""
        seg = DateSegment(
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
        with patch("app.services.backfill.settings.HH_API_FALLBACK_ENABLED", True):
            params = BackfillService._build_search_params(
                seg, page=0, per_page=1)
        assert params["date_from"].startswith("2026-01-01T")
        assert params["date_to"].startswith("2026-01-15T")

    def test_params_text_from_config(self):
        seg = DateSegment(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        params = BackfillService._build_search_params(seg, page=0, per_page=1)
        assert params["text"] == "frontend developer"


class TestBackfillHtmlHelpers:
    """Tests for the HTML-source helpers (counter + link extraction)."""

    def _service(self) -> BackfillService:
        return BackfillService(
            session=AsyncMock(),
            relevance_filter=_build_relevance_filter(),
            days_back=7,
        )

    def test_default_source_is_html(self):
        svc = self._service()
        assert svc._use_api is False

    def test_parse_results_count(self):
        svc = self._service()
        html = (
            "<html><body>"
            "<h1 data-qa='title'>Найдено 1\u00a0426 вакансий«frontend»</h1>"
            "</body></html>"
        )
        assert svc._parse_results_count(html) == 1426

    def test_parse_results_count_missing(self):
        svc = self._service()
        assert svc._parse_results_count("<html><body></body></html>") == 0

    def test_extract_search_links(self):
        svc = self._service()
        html = (
            "<html><body>"
            "<a data-qa='serp-item__title' href='/vacancy/111?from=x'>A</a>"
            "<a data-qa='serp-item__title' href='https://hh.ru/vacancy/222'>B</a>"
            "<a data-qa='serp-item__title' href='/vacancy/111?dup'>dup</a>"
            "</body></html>"
        )
        pairs = svc._extract_search_links(html)
        ids = [vid for vid, _ in pairs]
        assert ids == [111, 222]  # dup of 111 removed within page
        assert pairs[0][1] == "https://hh.ru/vacancy/111?from=x"
        assert pairs[1][1] == "https://hh.ru/vacancy/222"


# ── run_backfill wrapper test ─────────────────────────────────────────────


class TestRunBackfill:
    """Tests for the top-level run_backfill convenience function."""

    @pytest.mark.asyncio
    async def test_run_backfill_calls_service(self):
        """run_backfill loads filter from DB and delegates to BackfillService."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()

        with patch(
            "app.services.backfill.RelevanceFilter.from_db",
            new_callable=AsyncMock,
        ) as mock_from_db, patch(
            "app.services.backfill.BackfillService.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_from_db.return_value = _build_relevance_filter()
            mock_run.return_value = {"status": "success", "created": 42}

            result = await run_backfill(session, days_back=14)

        mock_from_db.assert_awaited_once_with(session)
        mock_run.assert_awaited_once()
        assert result["status"] == "success"
        assert result["created"] == 42


# ── Edge cases ─────────────────────────────────────────────────────────────


class TestBackfillEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_min_segment_stops_splitting(self):
        """If segment is less than min_segment_hours, paginate even if over threshold."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=1,
            segment_threshold=10,
            min_segment_hours=24,  # 24h minimum
        )

        async def fake_found(seg):
            return 50  # Above threshold (10), but segment <= min_segment_hours

        async def fake_page(seg, page):
            return [(100 + i, f"https://hh.ru/vacancy/{100 + i}")
                    for i in range(50)]

        with patch.object(service, "_get_segment_found_count", side_effect=fake_found):
            with patch.object(service, "_fetch_search_page", side_effect=fake_page):
                seg = DateSegment(
                    datetime.now(timezone.utc) - timedelta(hours=23),
                    datetime.now(timezone.utc),
                )
                await service._collect_segment_ids(seg)

        # Should NOT split because duration < min_segment_hours
        assert service._stats.segments_split == 0
        assert service._stats.segments_processed == 1
        assert len(service._seen_ids) == 50

    @pytest.mark.asyncio
    async def test_last_page_partial_stops_pagination(self):
        """When a page returns fewer items than per_page, stop paginating."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=5,
        )

        call_count = [0]

        async def fake_found(seg):
            return 250  # implies 3 pages

        def _pairs(rng):
            return [(i, f"https://hh.ru/vacancy/{i}") for i in rng]

        async def fake_page(seg, page):
            call_count[0] += 1
            if page == 0:
                return _pairs(range(100))
            elif page == 1:
                return _pairs(range(100, 200))
            elif page == 2:
                return _pairs(range(200, 250))  # only 50 items → last page
            else:
                return _pairs(range(250, 300))  # should not be called

        with patch.object(service, "_get_segment_found_count", side_effect=fake_found):
            with patch.object(service, "_fetch_search_page", side_effect=fake_page):
                seg = DateSegment(
                    datetime.now(timezone.utc) - timedelta(days=5),
                    datetime.now(timezone.utc),
                )
                await service._collect_segment_ids(seg)

        assert call_count[0] == 3  # stopped after partial page
        assert len(service._seen_ids) == 250

    @pytest.mark.asyncio
    async def test_detail_fetch_error_increments_counter(self):
        """If detail fetch fails, error counter increments and processing continues."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()

        rf = _build_relevance_filter()
        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=5,
        )
        service._seen_ids = {1, 2}

        call_idx = [0]

        async def fake_detail(vac_id):
            call_idx[0] += 1
            if vac_id == 1:
                return None  # simulate fetch failure
            return RawVacancy(
                hh_vacancy_id=2,
                title="Frontend Developer",
                description="React JavaScript TypeScript",
                skills=["React", "JavaScript"],
                source_type="api",
            )

        with patch.object(
            service, "_fetch_vacancy_detail", side_effect=fake_detail
        ), patch(
            "app.services.backfill.create_ingestion_run", new_callable=AsyncMock
        ) as mock_create_run, patch(
            "app.services.backfill.finish_ingestion_run", new_callable=AsyncMock
        ), patch(
            "app.services.backfill.upsert_vacancy", new_callable=AsyncMock
        ) as mock_upsert, patch.object(
            service, "_collect_segment_ids", new_callable=AsyncMock
        ):
            mock_run = MagicMock()
            mock_run.id = 1
            mock_create_run.return_value = mock_run
            mock_upsert.return_value = (True, False)
            service._client = MagicMock()

            summary = await service.run()

        assert summary["detail_errors"] == 1
        # Vacancy 2 should still process
        assert summary["details_fetched"] == 1

    @pytest.mark.asyncio
    async def test_progress_callback_invoked(self):
        """Progress callback is called periodically."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()

        rf = _build_relevance_filter()
        progress_calls = []

        def on_progress(current, total, stats):
            progress_calls.append((current, total))

        service = BackfillService(
            session=session,
            relevance_filter=rf,
            days_back=1,
            progress_callback=on_progress,
        )
        # 100 IDs → callback should fire at 50, 100
        service._seen_ids = set(range(100))

        async def fake_detail(vac_id):
            return RawVacancy(
                hh_vacancy_id=vac_id,
                title="Frontend Developer",
                description="React JavaScript TypeScript frontend",
                skills=["React", "JavaScript"],
                source_type="api",
            )

        with patch.object(
            service, "_fetch_vacancy_detail", side_effect=fake_detail
        ), patch(
            "app.services.backfill.create_ingestion_run", new_callable=AsyncMock
        ) as mock_create_run, patch(
            "app.services.backfill.finish_ingestion_run", new_callable=AsyncMock
        ), patch(
            "app.services.backfill.upsert_vacancy", new_callable=AsyncMock
        ) as mock_upsert, patch.object(
            service, "_collect_segment_ids", new_callable=AsyncMock
        ):
            mock_run = MagicMock()
            mock_run.id = 1
            mock_create_run.return_value = mock_run
            mock_upsert.return_value = (True, False)
            service._client = MagicMock()

            await service.run()

        # With batch_size=50, callback should fire at 50 and 100
        assert len(progress_calls) == 2
        assert progress_calls[0][0] == 50
        assert progress_calls[1][0] == 100
