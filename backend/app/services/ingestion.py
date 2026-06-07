"""Ingestion pipeline — orchestrates: parse → relevance filter → normalize → persist.

Follows §2.4 architecture: Scheduler / CLI calls this pipeline.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.api_source import ApiVacancySource
from app.services.html_source import HtmlVacancySource
from app.services.normalizer import Normalizer
from app.services.persistence import (
    create_ingestion_run,
    finish_ingestion_run,
    save_filtered_vacancy,
    upsert_vacancy,
)
from app.services.relevance import RelevanceFilter
from app.services.source_interface import VacancySource

logger = structlog.get_logger(__name__)


async def run_ingestion(session: AsyncSession, max_pages: int | None = None) -> dict:
    """Execute the full ingestion pipeline.

    1. Create ingestion_run (running)
    2. Select source (HTML primary / API fallback)
    3. Fetch raw vacancies
    4. For each vacancy: relevance filter → normalize → upsert
    5. Update ingestion_run counters
    6. Return summary dict

    Args:
        session: async DB session.
        max_pages: override page limit for testing.

    Returns:
        dict with summary counters.
    """
    # 1. Create run
    run = await create_ingestion_run(session)
    await session.commit()
    logger.info("ingestion_started", run_id=run.id)

    # 2. Select source
    source: VacancySource
    api_fallback_count = 0

    if settings.HH_SOURCE == "api" or settings.HH_API_FALLBACK_ENABLED:
        # Try API if explicitly selected or as fallback
        if settings.HH_SOURCE == "api":
            source = ApiVacancySource()
            logger.info("source_selected", source="api", reason="config")
        else:
            source = HtmlVacancySource()
            logger.info("source_selected", source="html", reason="primary")
    else:
        source = HtmlVacancySource()
        logger.info("source_selected", source="html", reason="primary_default")

    # 3. Load relevance filter from DB
    relevance_filter = await RelevanceFilter.from_db(session)
    normalizer = Normalizer()

    # 4. Fetch raw vacancies
    try:
        raw_vacancies = await source.fetch_vacancies(max_pages=max_pages)
    except Exception:
        logger.exception("source_fetch_failed", source=source.source_name())
        run.status = "failed"
        run.error_count = 1
        await session.commit()
        return {"status": "failed", "error": "source_fetch_failed"}

    run.found_total = len(raw_vacancies)

    # Track captcha count from HTML source
    if isinstance(source, HtmlVacancySource):
        run.captcha_block_count = source.captcha_count

    logger.info("raw_vacancies_fetched", count=len(
        raw_vacancies), source=source.source_name())

    # 5. Process each vacancy
    created = 0
    updated = 0
    filtered = 0
    errors = 0

    for raw in raw_vacancies:
        try:
            # 5a. Relevance filter (FR-41)
            rel_result = relevance_filter.check(raw)

            if not rel_result.relevant:
                filtered += 1
                # Optional audit (FR-46)
                if settings.RELEVANCE_AUDIT_ENABLED:
                    await save_filtered_vacancy(
                        session, raw.hh_vacancy_id, raw.title, rel_result, run
                    )
                continue

            # 5b. Normalize (grade is resolved here, AFTER filter — FR-47)
            normalized = normalizer.normalize(raw)

            # 5c. Persist (idempotent upsert)
            is_created, is_updated = await upsert_vacancy(session, normalized, run)
            if is_created:
                created += 1
            else:
                updated += 1

        except Exception:
            errors += 1
            logger.exception("vacancy_processing_error",
                             hh_id=raw.hh_vacancy_id)

    # 6. Update run counters
    run.created_count = created
    run.updated_count = updated
    run.filtered_count = filtered
    run.error_count = errors
    run.api_fallback_count = api_fallback_count

    status = "success" if errors == 0 else "partial"
    await finish_ingestion_run(session, run, status=status)
    await session.commit()

    summary = {
        "run_id": run.id,
        "status": status,
        "found_total": run.found_total,
        "created": created,
        "updated": updated,
        "filtered": filtered,
        "errors": errors,
        "captcha_blocks": run.captcha_block_count,
        "api_fallback": api_fallback_count,
    }
    logger.info("ingestion_complete", **summary)
    return summary
