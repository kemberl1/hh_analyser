"""Backfill service — segmented search to bypass hh.ru ~2000 results limit.

Phase 8: one-shot full backfill of ALL Frontend vacancies from hh.ru.

Source: the project's PRIMARY source is HTML scraping of hh.ru
(``HtmlVacancySource``); ``api.hh.ru`` is a disabled-by-default fallback
(``HH_API_FALLBACK_ENABLED=false``) that does not work in this environment.
Backfill therefore drives the **HTML** search by default and only uses the
JSON API when the fallback flag is explicitly enabled.

Strategy: date-based recursive segmentation.
1. Start with the requested date range (``days_back``).
2. Query the search for the segment; read the "found" count
   (HTML: parse the "Найдено N вакансий" results counter; API: ``found`` field).
3. If found >= BACKFILL_SEGMENT_THRESHOLD (~1900), split the segment in half
   and recurse (hh.ru only lets you browse the first ~2000 results).
4. Otherwise, paginate through all pages of the segment, collecting vacancy IDs
   (and, for HTML, their detail URLs).
5. Deduplicate IDs globally, fetch details, apply
   RelevanceFilter → Normalizer → persist (``published_at`` = publication date).
6. Commit per-batch for resumability.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from aiolimiter import AsyncLimiter
from selectolax.parser import HTMLParser
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.html_source import CaptchaDetectedError, HtmlVacancySource
from app.services.normalizer import Normalizer
from app.services.persistence import (
    create_ingestion_run,
    finish_ingestion_run,
    save_filtered_vacancy,
    upsert_vacancy,
)
from app.services.relevance import RelevanceFilter
from app.services.source_interface import RawVacancy

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
# hh.ru returns at most ~2000 browsable results per query.  We use a
# conservative threshold to trigger splitting *before* hitting the hard cap.
BACKFILL_SEGMENT_THRESHOLD: int = 1900
# Minimum segment duration before we stop splitting.  hh.ru HTML search filters
# by *date* (day granularity), so there is no point splitting below one day.
MIN_SEGMENT_HOURS: int = 24
# Maximum pages to paginate within a single segment (safety cap).
MAX_PAGES_PER_SEGMENT: int = 100
# Items per page for backfill search.
ITEMS_PER_PAGE: int = 100  # hh.ru supports up to 100 results per page


@dataclass
class BackfillStats:
    """Mutable counters shared across the recursive walk."""

    segments_processed: int = 0
    segments_split: int = 0
    ids_collected: int = 0
    ids_unique: int = 0
    details_fetched: int = 0
    created: int = 0
    updated: int = 0
    filtered: int = 0
    errors: int = 0
    detail_errors: int = 0
    captcha_blocks: int = 0


@dataclass
class DateSegment:
    """A [date_from, date_to) half-open interval."""

    date_from: datetime
    date_to: datetime

    @property
    def duration(self) -> timedelta:
        return self.date_to - self.date_from

    def split(self) -> tuple[DateSegment, DateSegment]:
        """Split into two roughly equal halves."""
        mid = self.date_from + self.duration / 2
        return (
            DateSegment(self.date_from, mid),
            DateSegment(mid, self.date_to),
        )

    def __repr__(self) -> str:
        return (
            f"Segment({self.date_from.strftime('%Y-%m-%dT%H:%M')}"
            f" → {self.date_to.strftime('%Y-%m-%dT%H:%M')})"
        )


class BackfillService:
    """Orchestrates the segmented backfill of ALL Frontend vacancies.

    Default source is HTML (the project's primary source).  When
    ``HH_API_FALLBACK_ENABLED`` is true the JSON API path is used instead — a
    flag-driven switch consistent with the rest of the system.
    """

    def __init__(
        self,
        session: AsyncSession,
        relevance_filter: RelevanceFilter,
        *,
        days_back: int = 30,
        segment_threshold: int = BACKFILL_SEGMENT_THRESHOLD,
        min_segment_hours: int = MIN_SEGMENT_HOURS,
        progress_callback: Any | None = None,
    ) -> None:
        self._session = session
        self._relevance_filter = relevance_filter
        self._normalizer = Normalizer()
        self._limiter = AsyncLimiter(
            max_rate=settings.HH_RATE_LIMIT_RPS,
            time_period=1.0,
        )
        self._days_back = days_back
        self._segment_threshold = segment_threshold
        self._min_segment_hours = min_segment_hours
        self._progress_cb = progress_callback

        # Source selection — HTML is primary, API is the disabled fallback.
        self._use_api = bool(settings.HH_API_FALLBACK_ENABLED)
        # Reuse the primary HTML source for detail parsing (publication date,
        # salary, skills, captcha detection, polite crawling).
        self._html = HtmlVacancySource()
        self._selectors = settings.HTML_SELECTORS

        # Global dedup set (vacancy IDs already seen in this run) + URL map.
        self._seen_ids: set[int] = set()
        self._id_urls: dict[int, str] = {}
        self._stats = BackfillStats()

    # ── Public entry point ─────────────────────────────────────────────
    async def run(self) -> dict[str, Any]:
        """Execute the full backfill.  Returns summary dict."""
        t0 = time.monotonic()

        # Create a single ingestion_run for the whole backfill
        run = await create_ingestion_run(self._session)
        run.meta = {
            "type": "backfill",
            "days_back": self._days_back,
            "source": "api" if self._use_api else "html",
        }
        await self._session.commit()
        logger.info("backfill_started", run_id=run.id,
                    days_back=self._days_back,
                    source="api" if self._use_api else "html")

        now = datetime.now(timezone.utc)
        root_segment = DateSegment(
            date_from=now - timedelta(days=self._days_back),
            date_to=now,
        )

        # HTML uses hh.ru (https://hh.ru); API uses api.hh.ru.
        base_url = settings.HH_API_BASE_URL if self._use_api else settings.HH_BASE_URL
        async with httpx.AsyncClient(
            base_url=base_url if self._use_api else "",
            headers={"User-Agent": settings.HH_USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            self._client = client

            # Phase 1: Collect ALL vacancy IDs via recursive segmentation
            logger.info("backfill_phase1_collecting_ids",
                        segment=str(root_segment))
            try:
                await self._collect_segment_ids(root_segment)
            except CaptchaDetectedError:
                self._stats.captcha_blocks += 1
                logger.warning("backfill_phase1_captcha_abort")
            self._stats.ids_unique = len(self._seen_ids)
            logger.info(
                "backfill_phase1_complete",
                total_ids=self._stats.ids_collected,
                unique_ids=self._stats.ids_unique,
                segments_processed=self._stats.segments_processed,
                segments_split=self._stats.segments_split,
            )

            # Phase 2: Fetch details + filter + normalize + persist
            logger.info("backfill_phase2_processing",
                        unique_ids=self._stats.ids_unique)
            all_ids = sorted(self._seen_ids)
            batch_size = 50  # commit every N vacancies

            for i, vac_id in enumerate(all_ids, start=1):
                try:
                    raw = await self._fetch_vacancy_detail(vac_id)
                    if raw is None:
                        self._stats.detail_errors += 1
                        continue
                    self._stats.details_fetched += 1

                    # Apply relevance filter
                    rel_result = self._relevance_filter.check(raw)
                    if not rel_result.relevant:
                        self._stats.filtered += 1
                        if settings.RELEVANCE_AUDIT_ENABLED:
                            await save_filtered_vacancy(
                                self._session, raw.hh_vacancy_id,
                                raw.title, rel_result, run,
                            )
                        continue

                    # Normalize + persist
                    normalized = self._normalizer.normalize(raw)
                    is_created, is_updated = await upsert_vacancy(
                        self._session, normalized, run,
                    )
                    if is_created:
                        self._stats.created += 1
                    else:
                        self._stats.updated += 1

                except CaptchaDetectedError:
                    self._stats.captcha_blocks += 1
                    logger.warning("backfill_detail_captcha", vac_id=vac_id)
                    await asyncio.sleep(random.uniform(10, 30))
                except Exception:
                    self._stats.errors += 1
                    logger.exception("backfill_vacancy_error", vac_id=vac_id)

                # Periodic commit + progress
                if i % batch_size == 0:
                    await self._session.commit()
                    if self._progress_cb:
                        self._progress_cb(i, len(all_ids), self._stats)
                    logger.info(
                        "backfill_progress",
                        processed=i,
                        total=len(all_ids),
                        created=self._stats.created,
                        filtered=self._stats.filtered,
                    )

            # Final commit
            await self._session.commit()

        # Finalize ingestion_run
        run.found_total = self._stats.ids_unique
        run.created_count = self._stats.created
        run.updated_count = self._stats.updated
        run.filtered_count = self._stats.filtered
        run.error_count = self._stats.errors + self._stats.detail_errors
        status = "success" if self._stats.errors == 0 else "partial"
        await finish_ingestion_run(self._session, run, status=status)
        await self._session.commit()

        elapsed = time.monotonic() - t0
        summary = {
            "run_id": run.id,
            "status": status,
            "source": "api" if self._use_api else "html",
            "duration_s": round(elapsed, 1),
            "days_back": self._days_back,
            "segments_processed": self._stats.segments_processed,
            "segments_split": self._stats.segments_split,
            "ids_collected": self._stats.ids_collected,
            "ids_unique": self._stats.ids_unique,
            "details_fetched": self._stats.details_fetched,
            "created": self._stats.created,
            "updated": self._stats.updated,
            "filtered": self._stats.filtered,
            "errors": self._stats.errors,
            "detail_errors": self._stats.detail_errors,
            "captcha_blocks": self._stats.captcha_blocks,
        }
        logger.info("backfill_complete", **summary)
        return summary

    # ── Phase 1: Recursive segment collection ──────────────────────────

    async def _collect_segment_ids(self, segment: DateSegment) -> None:
        """Recursively collect vacancy IDs for a date segment.

        If the segment has >= threshold results, split it in half.
        Otherwise paginate through all pages.
        """
        found = await self._get_segment_found_count(segment)
        logger.info(
            "backfill_segment_probe",
            segment=str(segment),
            found=found,
            threshold=self._segment_threshold,
        )

        if found == 0:
            self._stats.segments_processed += 1
            return

        if found >= self._segment_threshold and segment.duration > timedelta(
            hours=self._min_segment_hours
        ):
            # Split and recurse
            self._stats.segments_split += 1
            left, right = segment.split()
            await self._collect_segment_ids(left)
            await self._collect_segment_ids(right)
            return

        # Paginate through the segment.  Determine the actual page size from
        # the first page (hh.ru HTML may clamp ``per_page``), then derive how
        # many pages are needed.
        page = 0
        page_size: int | None = None
        pages_to_fetch = MAX_PAGES_PER_SEGMENT
        while page < pages_to_fetch:
            pairs = await self._fetch_search_page(segment, page)
            self._stats.ids_collected += len(pairs)
            for vid, url in pairs:
                if vid not in self._seen_ids:
                    self._seen_ids.add(vid)
                    if url:
                        self._id_urls[vid] = url

            if page == 0:
                page_size = len(pairs) or ITEMS_PER_PAGE
                pages_needed = (found + page_size - 1) // page_size
                pages_to_fetch = min(pages_needed, MAX_PAGES_PER_SEGMENT)

            if len(pairs) < (page_size or ITEMS_PER_PAGE):
                break  # last (partial) page
            page += 1

        self._stats.segments_processed += 1

    @retry(
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError),
        ),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=3, max=60, jitter=5),
        reraise=True,
    )
    async def _get_segment_found_count(self, segment: DateSegment) -> int:
        """Probe the search to get the total ``found`` for a segment."""
        if self._use_api:
            async with self._limiter:
                await asyncio.sleep(random.uniform(0.3, 0.8))
                params = self._build_search_params(segment, page=0, per_page=1)
                resp = await self._client.get(
                    settings.HH_API_BASE_URL + "/vacancies", params=params,
                )
                resp.raise_for_status()
                data = resp.json()
            return int(data.get("found", 0))

        # HTML: fetch the first search page and parse the results counter.
        html = await self._fetch_search_html(segment, page=0)
        return self._parse_results_count(html)

    @retry(
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError),
        ),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=3, max=60, jitter=5),
        reraise=True,
    )
    async def _fetch_search_page(
        self, segment: DateSegment, page: int,
    ) -> list[tuple[int, str]]:
        """Fetch a single search page within a date segment.

        Returns a list of ``(vacancy_id, detail_url)`` pairs.  For the API path
        the URL is the canonical ``/vacancy/{id}`` page.
        """
        if self._use_api:
            async with self._limiter:
                await asyncio.sleep(random.uniform(0.5, 1.5))
                params = self._build_search_params(
                    segment, page=page, per_page=ITEMS_PER_PAGE,
                )
                resp = await self._client.get(
                    settings.HH_API_BASE_URL + "/vacancies", params=params,
                )
                resp.raise_for_status()
                data = resp.json()
            items = data.get("items", [])
            return [
                (int(item["id"]),
                 item.get("alternate_url")
                 or f"{settings.HH_BASE_URL}/vacancy/{item['id']}")
                for item in items if "id" in item
            ]

        # HTML path.
        html = await self._fetch_search_html(segment, page=page)
        return self._extract_search_links(html)

    async def _fetch_search_html(self, segment: DateSegment, page: int) -> str:
        """Fetch a hh.ru HTML search page with rate-limit, delay, captcha check."""
        async with self._limiter:
            delay = random.uniform(
                settings.HH_REQUEST_DELAY_MIN, settings.HH_REQUEST_DELAY_MAX)
            await asyncio.sleep(delay)
            params = self._build_search_params(
                segment, page=page, per_page=ITEMS_PER_PAGE)
            resp = await self._client.get(
                settings.HH_BASE_URL + settings.HH_SEARCH_PATH, params=params,
            )
            resp.raise_for_status()
            html = resp.text
        if self._html._is_captcha(html):
            self._stats.captcha_blocks += 1
            raise CaptchaDetectedError(
                f"Captcha on search page {page} for {segment}")
        return html

    def _extract_search_links(self, html: str) -> list[tuple[int, str]]:
        """Extract (vacancy_id, url) pairs from a search-results HTML page."""
        tree = HTMLParser(html)
        links = tree.css(self._selectors.get(
            "vacancy_link", "a.serp-item__title"))
        if not links:
            links = tree.css(self._selectors.get(
                "vacancy_link_alt", "a[data-qa='serp-item__title']"))

        pairs: list[tuple[int, str]] = []
        seen_on_page: set[int] = set()
        for node in links:
            href = node.attributes.get("href", "") or ""
            vac_id = HtmlVacancySource._extract_vacancy_id(href)
            if vac_id and vac_id not in seen_on_page:
                seen_on_page.add(vac_id)
                full_url = href if href.startswith(
                    "http") else settings.HH_BASE_URL + href
                pairs.append((vac_id, full_url))
        return pairs

    def _parse_results_count(self, html: str) -> int:
        """Parse the "Найдено N вакансий" counter from a search page."""
        tree = HTMLParser(html)
        text = ""
        for key in ("results_count", "results_count_alt"):
            sel = self._selectors.get(key)
            if not sel:
                continue
            node = tree.css_first(sel)
            if node:
                text = node.text(strip=True)
                if text:
                    break

        if not text:
            logger.warning("backfill_results_count_not_found")
            return 0

        # Normalise non-breaking / thin spaces inside numbers and extract digits.
        cleaned = text.replace("\xa0", "").replace("\u202f", "").replace(
            "\u2009", "").replace(" ", "")
        match = re.search(r"(\d+)", cleaned)
        if match:
            return int(match.group(1))
        logger.warning("backfill_results_count_unparsed", text=text[:80])
        return 0

    # ── Phase 2: Detail fetching ───────────────────────────────────────

    async def _fetch_vacancy_detail(self, vac_id: int) -> RawVacancy | None:
        """Fetch a single vacancy detail.

        HTML (default): reuse ``HtmlVacancySource`` parsing — keeps
        ``published_at`` = publication date, salary/skills, captcha handling.
        API (fallback): query api.hh.ru JSON.
        """
        if not self._use_api:
            url = self._id_urls.get(vac_id) or (
                f"{settings.HH_BASE_URL}/vacancy/{vac_id}")
            return await self._html._fetch_vacancy_detail(
                self._client, vac_id, url)

        return await self._fetch_vacancy_detail_api(vac_id)

    @retry(
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError),
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=3),
        reraise=True,
    )
    async def _fetch_vacancy_detail_api(self, vac_id: int) -> RawVacancy | None:
        """Fetch single vacancy detail from api.hh.ru (fallback path)."""
        async with self._limiter:
            await asyncio.sleep(random.uniform(0.3, 1.0))
            resp = await self._client.get(
                settings.HH_API_BASE_URL + f"/vacancies/{vac_id}")
            resp.raise_for_status()
            data = resp.json()

        salary = data.get("salary") or {}
        salary_from = salary.get("from")
        salary_to = salary.get("to")
        salary_currency = salary.get("currency")
        salary_gross = salary.get("gross")

        employer = data.get("employer") or {}
        employer_name = employer.get("name")
        employer_hh_id = int(employer["id"]) if employer.get("id") else None
        employer_url = employer.get("alternate_url")

        experience = data.get("experience") or {}
        experience_raw = experience.get("id")

        schedule = data.get("schedule") or {}
        employment_format = _map_schedule(schedule.get("id", ""))

        key_skills = data.get("key_skills") or []
        skills = [ks["name"] for ks in key_skills if "name" in ks]

        description = data.get("description", "")

        published_str = data.get("published_at", "")
        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00"),
                )
            except ValueError:
                pass

        area = data.get("area") or {}
        area_name = area.get("name")

        return RawVacancy(
            hh_vacancy_id=vac_id,
            title=data.get("name", ""),
            url=data.get("alternate_url"),
            employer_name=employer_name,
            employer_id=employer_hh_id,
            employer_url=employer_url,
            salary_from=float(salary_from) if salary_from else None,
            salary_to=float(salary_to) if salary_to else None,
            salary_currency=salary_currency,
            salary_gross=salary_gross,
            experience_raw=experience_raw,
            employment_format=employment_format,
            area_name=area_name,
            published_at=published_at,
            description=description,
            skills=skills,
            source_type="api",
            raw_payload=data,
        )

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_search_params(
        segment: DateSegment, *, page: int, per_page: int,
    ) -> dict[str, str]:
        """Build query params for the search with date boundaries.

        hh.ru honours ``date_from`` / ``date_to`` in BOTH the HTML search
        (https://hh.ru/search/vacancy) and the JSON API, but with DIFFERENT
        date formats (verified live):

        * HTML search accepts ONLY ``DD.MM.YYYY``.  The ISO ``YYYY-MM-DD`` form
          is silently ignored and returns the full, unfiltered result set —
          which would defeat segmentation entirely.
        * The JSON API (fallback) accepts ISO 8601 ``YYYY-MM-DDThh:mm:ss%z``.

        Day precision is sufficient: even a single day of Frontend vacancies
        stays well below the ~2000 browsable-results cap.
        """
        base = settings.HH_SEARCH_PARAMS
        if settings.HH_API_FALLBACK_ENABLED:
            date_from = segment.date_from.strftime("%Y-%m-%dT%H:%M:%S%z")
            date_to = segment.date_to.strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            # hh.ru HTML search requires DD.MM.YYYY (inclusive on both ends).
            date_from = segment.date_from.strftime("%d.%m.%Y")
            date_to = segment.date_to.strftime("%d.%m.%Y")
        return {
            "text": base.get("text", "frontend developer"),
            "area": base.get("area", "113"),
            "per_page": str(per_page),
            "page": str(page),
            "date_from": date_from,
            "date_to": date_to,
            "order_by": "publication_time",
        }


def _map_schedule(schedule_id: str) -> str:
    """Map hh.ru schedule id to our employment_format enum."""
    mapping = {
        "remote": "remote",
        "fullDay": "office",
        "flexible": "hybrid",
        "shift": "office",
        "flyInFlyOut": "office",
    }
    return mapping.get(schedule_id, "unknown")


async def run_backfill(
    session: AsyncSession,
    *,
    days_back: int = 30,
    segment_threshold: int = BACKFILL_SEGMENT_THRESHOLD,
    min_segment_hours: int = MIN_SEGMENT_HOURS,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: load relevance filter from DB and run backfill.

    This is the function called by CLI and scheduler.
    """
    relevance_filter = await RelevanceFilter.from_db(session)
    service = BackfillService(
        session=session,
        relevance_filter=relevance_filter,
        days_back=days_back,
        segment_threshold=segment_threshold,
        min_segment_hours=min_segment_hours,
        progress_callback=progress_callback,
    )
    return await service.run()
