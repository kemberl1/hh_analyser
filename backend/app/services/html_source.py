"""HtmlVacancySource — PRIMARY source: HTML scraping of hh.ru (FR-2, FR-37–FR-40)."""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime, timezone
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

from app.core.config import settings
from app.services.source_interface import RawVacancy, VacancySource

logger = structlog.get_logger(__name__)


class CaptchaDetectedError(Exception):
    """Raised when captcha/block is detected on hh.ru page."""


class HtmlVacancySource(VacancySource):
    """Primary source: HTML parsing of hh.ru search + vacancy pages.

    Features:
    - Polite crawling: User-Agent, delays, aiolimiter rate-limit (NFR-8/9/10)
    - Configurable CSS selectors (FR-37)
    - Captcha/block detection without bypass (FR-39)
    - Pagination (FR-38)
    - Saves raw_html (FR-40)
    - Retry with backoff+jitter (tenacity, NFR-31)
    """

    def __init__(self) -> None:
        self._selectors = settings.HTML_SELECTORS
        self._limiter = AsyncLimiter(
            max_rate=settings.HH_RATE_LIMIT_RPS,
            time_period=1.0,
        )
        self._captcha_count = 0

    @property
    def captcha_count(self) -> int:
        return self._captcha_count

    def source_name(self) -> str:
        return "html"

    async def fetch_vacancies(self, max_pages: int | None = None) -> list[RawVacancy]:
        """Fetch vacancies by crawling hh.ru search pages + individual vacancy pages."""
        max_pages = max_pages or settings.HH_MAX_PAGES
        self._captcha_count = 0
        vacancies: list[RawVacancy] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": settings.HH_USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            # Step 1: Crawl search pages to get vacancy links
            vacancy_links = await self._crawl_search_pages(client, max_pages)
            logger.info(
                "search_crawl_complete",
                total_links=len(vacancy_links),
                pages_crawled=max_pages,
            )

            # Step 2: Fetch each vacancy detail
            for idx, (vac_id, vac_url) in enumerate(vacancy_links):
                try:
                    raw = await self._fetch_vacancy_detail(client, vac_id, vac_url)
                    if raw is not None:
                        vacancies.append(raw)
                except CaptchaDetectedError:
                    self._captcha_count += 1
                    logger.warning("captcha_on_detail", url=vac_url,
                                   captcha_total=self._captcha_count)
                    # Back off on captcha (FR-39)
                    await asyncio.sleep(random.uniform(10, 30))
                except Exception:
                    logger.exception("vacancy_detail_error", url=vac_url)

                if idx % 10 == 0 and idx > 0:
                    logger.info("vacancy_fetch_progress",
                                fetched=idx, total=len(vacancy_links))

        logger.info(
            "html_source_complete",
            total_vacancies=len(vacancies),
            captcha_blocks=self._captcha_count,
        )
        return vacancies

    async def _crawl_search_pages(
        self, client: httpx.AsyncClient, max_pages: int
    ) -> list[tuple[int, str]]:
        """Crawl search result pages, return list of (hh_vacancy_id, url)."""
        vacancy_links: list[tuple[int, str]] = []
        seen_ids: set[int] = set()

        for page in range(max_pages):
            try:
                html = await self._fetch_page(
                    client,
                    settings.HH_BASE_URL + settings.HH_SEARCH_PATH,
                    params={**settings.HH_SEARCH_PARAMS, "page": str(page)},
                )
            except CaptchaDetectedError:
                self._captcha_count += 1
                logger.warning("captcha_on_search", page=page,
                               captcha_total=self._captcha_count)
                await asyncio.sleep(random.uniform(10, 30))
                break

            tree = HTMLParser(html)

            # Try primary selector, then alt
            links = tree.css(self._selectors.get(
                "vacancy_link", "a.serp-item__title"))
            if not links:
                links = tree.css(self._selectors.get(
                    "vacancy_link_alt", "a[data-qa='serp-item__title']"))

            if not links:
                logger.warning("no_vacancy_links_on_page", page=page)
                break

            for link_node in links:
                href = link_node.attributes.get("href", "")
                vac_id = self._extract_vacancy_id(href)
                if vac_id and vac_id not in seen_ids:
                    seen_ids.add(vac_id)
                    # Normalize URL
                    full_url = href if href.startswith(
                        "http") else settings.HH_BASE_URL + href
                    vacancy_links.append((vac_id, full_url))

            # Check for next page
            next_btn = tree.css_first(self._selectors.get(
                "next_page", "a[data-qa='pager-next']"))
            if not next_btn:
                logger.info("no_next_page", stopped_at=page)
                break

        return vacancy_links

    @retry(
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=3),
        reraise=True,
    )
    async def _fetch_page(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
    ) -> str:
        """Fetch a page with rate limiting, delay, and retry."""
        async with self._limiter:
            delay = random.uniform(
                settings.HH_REQUEST_DELAY_MIN, settings.HH_REQUEST_DELAY_MAX)
            await asyncio.sleep(delay)

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            html = resp.text

            # Captcha detection (FR-39)
            if self._is_captcha(html):
                raise CaptchaDetectedError(f"Captcha detected on {url}")

            return html

    async def _fetch_vacancy_detail(
        self, client: httpx.AsyncClient, vac_id: int, url: str
    ) -> RawVacancy | None:
        """Fetch and parse a single vacancy page."""
        html = await self._fetch_page(client, url)
        tree = HTMLParser(html)

        sel = self._selectors

        # Title
        title_node = tree.css_first(
            sel.get("title", "h1[data-qa='vacancy-title']"))
        title = title_node.text(strip=True) if title_node else ""
        if not title:
            logger.warning("no_title_found", vac_id=vac_id, url=url)
            return None

        # Salary
        salary_from, salary_to, salary_currency, salary_gross = self._parse_salary(
            tree)

        # Employer
        emp_node = tree.css_first(
            sel.get("employer_name", "a[data-qa='vacancy-company-name']"))
        employer_name = emp_node.text(strip=True) if emp_node else None
        employer_url = emp_node.attributes.get("href") if emp_node else None
        employer_hh_id = self._extract_employer_id(
            employer_url) if employer_url else None

        # Experience
        exp_node = tree.css_first(
            sel.get("experience", "span[data-qa='vacancy-experience']"))
        experience_raw = exp_node.text(strip=True) if exp_node else None

        # Employment format
        fmt_node = tree.css_first(
            sel.get("employment_mode",
                    "p[data-qa='vacancy-view-employment-mode']")
        )
        employment_format = self._parse_employment_format(
            fmt_node.text(strip=True) if fmt_node else ""
        )

        # Description
        desc_node = tree.css_first(
            sel.get("description", "div[data-qa='vacancy-description']")
        )
        description = desc_node.text(strip=True) if desc_node else None

        # Skills
        skill_nodes = tree.css(
            sel.get("skills", "div[data-qa='skills-element']"))
        skills: list[str] = []
        for sn in skill_nodes:
            tag = sn.css_first(
                sel.get("skill_tag", "span[data-qa='bloko-tag__text']"))
            if tag:
                skills.append(tag.text(strip=True))
            else:
                text = sn.text(strip=True)
                if text:
                    skills.append(text)

        # Published date
        published_at = self._parse_published_date(tree)

        # Area (from search page or vacancy — often in breadcrumbs; simplify)
        area_name = None  # will be extracted if available from description/meta

        return RawVacancy(
            hh_vacancy_id=vac_id,
            title=title,
            url=url,
            employer_name=employer_name,
            employer_id=employer_hh_id,
            employer_url=employer_url,
            salary_from=salary_from,
            salary_to=salary_to,
            salary_currency=salary_currency,
            salary_gross=salary_gross,
            experience_raw=experience_raw,
            employment_format=employment_format,
            area_name=area_name,
            published_at=published_at,
            description=description,
            skills=skills,
            source_type="html",
            raw_html=html,
        )

    def _parse_salary(self, tree: HTMLParser) -> tuple[float | None, float | None, str | None, bool | None]:
        """Parse salary from vacancy page HTML."""
        sel = self._selectors
        salary_node = tree.css_first(
            sel.get("salary", "div[data-qa='vacancy-salary']"))
        if not salary_node:
            return None, None, None, None

        text = salary_node.text(strip=True)
        return self._parse_salary_text(text)

    @staticmethod
    def _parse_salary_text(text: str) -> tuple[float | None, float | None, str | None, bool | None]:
        """Parse salary text like '100 000 – 150 000 руб. на руки' into components."""
        if not text:
            return None, None, None, None

        text = text.replace("\xa0", " ").replace(" ", " ").strip()

        # Determine gross/net
        gross = None
        text_lower = text.lower()
        if "на руки" in text_lower or "net" in text_lower:
            gross = False
        elif "до вычета" in text_lower or "gross" in text_lower:
            gross = True

        # Determine currency
        currency = None
        if "руб" in text_lower or "₽" in text:
            currency = "RUR"
        elif "usd" in text_lower or "$" in text:
            currency = "USD"
        elif "eur" in text_lower or "€" in text:
            currency = "EUR"

        # Extract numbers
        numbers = re.findall(r"[\d\s]+", text)
        parsed_numbers: list[float] = []
        for n in numbers:
            cleaned = n.replace(" ", "").strip()
            if cleaned and cleaned.isdigit():
                parsed_numbers.append(float(cleaned))

        salary_from = None
        salary_to = None

        if "от" in text_lower and "до" in text_lower and len(parsed_numbers) >= 2:
            salary_from = parsed_numbers[0]
            salary_to = parsed_numbers[1]
        elif "от" in text_lower and parsed_numbers:
            salary_from = parsed_numbers[0]
        elif "до" in text_lower and parsed_numbers:
            salary_to = parsed_numbers[0]
        elif len(parsed_numbers) >= 2:
            salary_from = parsed_numbers[0]
            salary_to = parsed_numbers[1]
        elif len(parsed_numbers) == 1:
            salary_from = parsed_numbers[0]

        return salary_from, salary_to, currency, gross

    def _parse_published_date(self, tree: HTMLParser) -> datetime | None:
        """Extract published_at from vacancy page."""
        sel = self._selectors
        # Try configured CSS selectors first
        for selector_key in ("published_date", "published_date_alt"):
            selector = sel.get(selector_key, "")
            if selector:
                node = tree.css_first(selector)
                if node:
                    text = node.text(strip=True)
                    dt = self._parse_russian_date(text)
                    if dt:
                        return dt

        # Fallback: locate text node "Вакансия опубликована" (magritte redesign —
        # no stable data-qa on this element, only CSS-hashed class names).
        for node in tree.css("div"):
            raw_text = node.text(deep=False, strip=True) or ""
            if raw_text.startswith("Вакансия опубликована"):
                full_text = node.text(strip=True)
                dt = self._parse_russian_date(full_text)
                if dt:
                    return dt

        return None

    @staticmethod
    def _parse_russian_date(text: str) -> datetime | None:
        """Parse Russian date text like 'Вакансия опубликована 5 июня 2026' to datetime."""
        if not text:
            return None
        text = text.lower().strip()

        months = {
            "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
            "мая": 5, "май": 5, "июн": 6, "июл": 7, "август": 8,
            "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
        }

        # Extract day + month + year
        match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
        if match:
            day = int(match.group(1))
            month_text = match.group(2)
            year = int(match.group(3))
            month = None
            for key, val in months.items():
                if month_text.startswith(key):
                    month = val
                    break
            if month:
                try:
                    return datetime(year, month, day, tzinfo=timezone.utc)
                except ValueError:
                    pass

        # Try day + month (current year)
        match2 = re.search(r"(\d{1,2})\s+(\w+)", text)
        if match2:
            day = int(match2.group(1))
            month_text = match2.group(2)
            month = None
            for key, val in months.items():
                if month_text.startswith(key):
                    month = val
                    break
            if month:
                try:
                    return datetime(datetime.now().year, month, day, tzinfo=timezone.utc)
                except ValueError:
                    pass

        return None

    @staticmethod
    def _extract_vacancy_id(url: str) -> int | None:
        """Extract numeric vacancy ID from hh.ru URL like /vacancy/12345?..."""
        match = re.search(r"/vacancy/(\d+)", url)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_employer_id(url: str | None) -> int | None:
        """Extract employer ID from employer URL /employer/12345."""
        if not url:
            return None
        match = re.search(r"/employer/(\d+)", url)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _parse_employment_format(text: str) -> str:
        """Normalize employment format text to canonical values.

        Handles both legacy 'Удалённая работа' and magritte 'Формат работы:удалённо'.
        """
        if not text:
            return "unknown"
        text_lower = text.lower()
        # Strip possible "формат работы:" prefix from magritte redesign
        if "формат работы" in text_lower:
            text_lower = text_lower.split(
                "формат работы")[-1].strip().lstrip(":").strip()
        if "удалён" in text_lower or "remote" in text_lower:
            return "remote"
        if "гибрид" in text_lower or "hybrid" in text_lower:
            return "hybrid"
        if "офис" in text_lower or "office" in text_lower or "на месте" in text_lower:
            return "office"
        return "unknown"

    def _is_captcha(self, html: str) -> bool:
        """Detect captcha/block page (FR-39)."""
        sel = self._selectors
        tree = HTMLParser(html)
        captcha_form = tree.css_first(
            sel.get("captcha_form", "form.HHCaptchaForm"))
        captcha_img = tree.css_first(
            sel.get("captcha_img", "img.hhcaptcha-picture"))
        if captcha_form or captcha_img:
            return True
        # Additional heuristics
        if "captcha" in html.lower() and len(html) < 5000:
            return True
        return False
