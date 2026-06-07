"""ApiVacancySource — FALLBACK source: api.hh.ru (FR-3, disabled by default)."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import settings
from app.services.source_interface import RawVacancy, VacancySource

logger = structlog.get_logger(__name__)


class ApiVacancySource(VacancySource):
    """Fallback source: api.hh.ru REST API.

    Disabled by default (HH_API_FALLBACK_ENABLED=false).
    When enabled, fetches vacancies via GET /vacancies + GET /vacancies/{id}.
    """

    def __init__(self) -> None:
        self._limiter = AsyncLimiter(
            max_rate=settings.HH_RATE_LIMIT_RPS,
            time_period=1.0,
        )

    def source_name(self) -> str:
        return "api"

    async def fetch_vacancies(self, max_pages: int | None = None) -> list[RawVacancy]:
        """Fetch vacancies from api.hh.ru."""
        max_pages = max_pages or settings.HH_MAX_PAGES
        vacancies: list[RawVacancy] = []

        async with httpx.AsyncClient(
            base_url=settings.HH_API_BASE_URL,
            headers={"User-Agent": settings.HH_USER_AGENT},
            timeout=30.0,
        ) as client:
            # Step 1: Search pages
            vacancy_ids: list[int] = []
            for page in range(max_pages):
                try:
                    items, has_more = await self._fetch_search_page(client, page)
                    vacancy_ids.extend(items)
                    if not has_more:
                        break
                except Exception:
                    logger.exception("api_search_page_error", page=page)
                    break

            logger.info("api_search_complete", total_ids=len(vacancy_ids))

            # Step 2: Fetch details
            for vac_id in vacancy_ids:
                try:
                    raw = await self._fetch_vacancy_detail(client, vac_id)
                    if raw:
                        vacancies.append(raw)
                except Exception:
                    logger.exception("api_vacancy_detail_error", vac_id=vac_id)

        return vacancies

    @retry(
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=3),
        reraise=True,
    )
    async def _fetch_search_page(
        self, client: httpx.AsyncClient, page: int
    ) -> tuple[list[int], bool]:
        """Fetch one search page, return (vacancy_ids, has_more)."""
        async with self._limiter:
            await asyncio.sleep(random.uniform(0.5, 1.5))
            params: dict[str, Any] = {
                "text": settings.HH_SEARCH_PARAMS.get("text", "frontend developer"),
                "area": settings.HH_SEARCH_PARAMS.get("area", "113"),
                "per_page": str(settings.HH_ITEMS_PER_PAGE),
                "page": str(page),
            }
            resp = await client.get("/vacancies", params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("items", [])
        ids = [int(item["id"]) for item in items if "id" in item]
        pages = data.get("pages", 0)
        has_more = page + 1 < pages
        return ids, has_more

    @retry(
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=3),
        reraise=True,
    )
    async def _fetch_vacancy_detail(
        self, client: httpx.AsyncClient, vac_id: int
    ) -> RawVacancy | None:
        """Fetch single vacancy detail from api.hh.ru."""
        async with self._limiter:
            await asyncio.sleep(random.uniform(0.3, 1.0))
            resp = await client.get(f"/vacancies/{vac_id}")
            resp.raise_for_status()
            data = resp.json()

        # Parse salary
        salary = data.get("salary") or {}
        salary_from = salary.get("from")
        salary_to = salary.get("to")
        salary_currency = salary.get("currency")
        salary_gross = salary.get("gross")

        # Employer
        employer = data.get("employer") or {}
        employer_name = employer.get("name")
        employer_hh_id = int(employer["id"]) if employer.get("id") else None
        employer_url = employer.get("alternate_url")

        # Experience
        experience = data.get("experience") or {}
        experience_raw = experience.get("id")

        # Employment format
        schedule = data.get("schedule") or {}
        employment_format = self._map_schedule(schedule.get("id", ""))

        # Skills
        key_skills = data.get("key_skills") or []
        skills = [ks["name"] for ks in key_skills if "name" in ks]

        # Description
        description = data.get("description", "")

        # Published date
        published_str = data.get("published_at", "")
        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Area
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

    @staticmethod
    def _map_schedule(schedule_id: str) -> str:
        mapping = {
            "remote": "remote",
            "fullDay": "office",
            "flexible": "hybrid",
            "shift": "office",
            "flyInFlyOut": "office",
        }
        return mapping.get(schedule_id, "unknown")
