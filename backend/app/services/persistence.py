"""Persistence service — idempotent upsert of normalized vacancies into DB.

Handles: employer upsert, vacancy upsert (ON CONFLICT hh_vacancy_id),
salary upsert, skill upsert + vacancy_skills, ingestion_runs tracking.
published_at is NOT overwritten on update (FR-11, §3).
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employer import Employer
from app.models.filtered_vacancy import FilteredVacancy
from app.models.ingestion_run import IngestionRun
from app.models.salary import Salary
from app.models.skill import Skill
from app.models.vacancy import Vacancy
from app.models.vacancy_skill import VacancySkill
from app.services.normalizer import NormalizedVacancy
from app.services.relevance import RelevanceResult

logger = structlog.get_logger(__name__)


async def create_ingestion_run(session: AsyncSession) -> IngestionRun:
    """Create a new ingestion_run with status=running."""
    run = IngestionRun(
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    session.add(run)
    await session.flush()
    return run


async def finish_ingestion_run(
    session: AsyncSession,
    run: IngestionRun,
    status: str = "success",
) -> None:
    """Update ingestion_run with final status and timestamp."""
    run.finished_at = datetime.now(timezone.utc)
    run.status = status
    await session.flush()


async def upsert_vacancy(
    session: AsyncSession,
    nv: NormalizedVacancy,
    run: IngestionRun,
) -> tuple[bool, bool]:
    """Idempotent upsert of a normalized vacancy.

    Returns (is_created, is_updated).
    published_at is NOT overwritten on update (AD-6).
    """
    # 1. Upsert employer
    employer_id = None
    if nv.employer_hh_id and nv.employer_name:
        employer_id = await _upsert_employer(session, nv)

    # 2. Resolve grade_id
    grade_id = await _resolve_grade_id(session, nv.grade_code)

    # 3. Upsert vacancy
    now = datetime.now(timezone.utc)
    stmt = pg_insert(Vacancy).values(
        hh_vacancy_id=nv.hh_vacancy_id,
        title=nv.title,
        employer_id=employer_id,
        grade_id=grade_id,
        experience_raw=nv.experience_raw,
        employment_format=nv.employment_format,
        area_name=nv.area_name,
        published_at=nv.published_at,
        url=nv.url,
        source_type=nv.source_type,
        raw_payload=nv.raw_payload,
        raw_html=nv.raw_html,
        ingestion_run_id=run.id,
        first_seen_at=now,
        last_seen_at=now,
        updated_at=now,
    )

    # ON CONFLICT: update most fields, but NOT published_at or first_seen_at
    stmt = stmt.on_conflict_do_update(
        index_elements=["hh_vacancy_id"],
        set_={
            "title": stmt.excluded.title,
            "employer_id": stmt.excluded.employer_id,
            "grade_id": stmt.excluded.grade_id,
            "experience_raw": stmt.excluded.experience_raw,
            "employment_format": stmt.excluded.employment_format,
            "area_name": stmt.excluded.area_name,
            "url": stmt.excluded.url,
            "source_type": stmt.excluded.source_type,
            "raw_payload": stmt.excluded.raw_payload,
            "raw_html": stmt.excluded.raw_html,
            "last_seen_at": now,
            "updated_at": now,
            # published_at intentionally NOT updated
            # first_seen_at intentionally NOT updated
        },
    )

    result = await session.execute(stmt)
    await session.flush()

    # Determine if created or updated
    # PostgreSQL: if xmax == 0 it was an insert, otherwise update
    # With returning we can check; but simpler: query by hh_vacancy_id
    vacancy = (
        await session.execute(
            select(Vacancy).where(Vacancy.hh_vacancy_id == nv.hh_vacancy_id)
        )
    ).scalar_one()

    is_created = vacancy.first_seen_at == vacancy.last_seen_at  # close enough heuristic
    is_updated = not is_created

    # 4. Upsert salary
    await _upsert_salary(session, vacancy.id, nv)

    # 5. Upsert skills + vacancy_skills
    await _upsert_skills(session, vacancy.id, nv.skills)

    return is_created, is_updated


async def save_filtered_vacancy(
    session: AsyncSession,
    hh_vacancy_id: int,
    title: str | None,
    result: RelevanceResult,
    run: IngestionRun,
) -> None:
    """Save a filtered (rejected) vacancy to audit table (FR-46)."""
    fv = FilteredVacancy(
        hh_vacancy_id=hh_vacancy_id,
        title=title,
        reason=result.reason,
        matched_stopword=result.matched_stopword,
        ingestion_run_id=run.id,
    )
    session.add(fv)
    await session.flush()


async def _upsert_employer(session: AsyncSession, nv: NormalizedVacancy) -> int | None:
    """Upsert employer by hh_employer_id, return internal id."""
    if not nv.employer_hh_id:
        return None

    stmt = pg_insert(Employer).values(
        hh_employer_id=nv.employer_hh_id,
        name=nv.employer_name or "Unknown",
        url=nv.employer_url,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["hh_employer_id"],
        set_={
            "name": stmt.excluded.name,
            "url": stmt.excluded.url,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await session.execute(stmt)
    await session.flush()

    result = await session.execute(
        select(Employer.id).where(Employer.hh_employer_id == nv.employer_hh_id)
    )
    row = result.scalar_one_or_none()
    return row


async def _resolve_grade_id(session: AsyncSession, grade_code: str) -> int | None:
    """Resolve grade code to grade.id."""
    from app.models.grade import Grade

    result = await session.execute(
        select(Grade.id).where(Grade.code == grade_code)
    )
    return result.scalar_one_or_none()


async def _upsert_salary(
    session: AsyncSession, vacancy_id: int, nv: NormalizedVacancy
) -> None:
    """Upsert salary for vacancy."""
    if nv.salary is None:
        # Remove existing salary if vacancy has no salary now
        existing = (
            await session.execute(
                select(Salary).where(Salary.vacancy_id == vacancy_id)
            )
        ).scalar_one_or_none()
        if existing:
            await session.delete(existing)
        return

    s = nv.salary
    stmt = pg_insert(Salary).values(
        vacancy_id=vacancy_id,
        amount_from=s.amount_from,
        amount_to=s.amount_to,
        currency=s.currency,
        gross=s.gross,
        amount_from_rub_net=s.amount_from_rub_net,
        amount_to_rub_net=s.amount_to_rub_net,
        point_estimate_rub_net=s.point_estimate_rub_net,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["vacancy_id"],
        set_={
            "amount_from": stmt.excluded.amount_from,
            "amount_to": stmt.excluded.amount_to,
            "currency": stmt.excluded.currency,
            "gross": stmt.excluded.gross,
            "amount_from_rub_net": stmt.excluded.amount_from_rub_net,
            "amount_to_rub_net": stmt.excluded.amount_to_rub_net,
            "point_estimate_rub_net": stmt.excluded.point_estimate_rub_net,
            "computed_at": datetime.now(timezone.utc),
        },
    )
    await session.execute(stmt)


async def _upsert_skills(
    session: AsyncSession, vacancy_id: int, skills: list[str]
) -> None:
    """Upsert skills and vacancy_skills links."""
    if not skills:
        return

    # Delete old vacancy_skills for this vacancy (idempotent rebuild)
    await session.execute(
        text("DELETE FROM vacancy_skills WHERE vacancy_id = :vid"),
        {"vid": vacancy_id},
    )

    for skill_name in skills:
        canonical = skill_name.lower().strip()
        display = skill_name.strip()

        # Upsert skill
        stmt = pg_insert(Skill).values(
            canonical_name=canonical,
            display_name=display,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["canonical_name"])
        await session.execute(stmt)

        # Get skill id
        result = await session.execute(
            select(Skill.id).where(Skill.canonical_name == canonical)
        )
        skill_id = result.scalar_one_or_none()
        if skill_id is None:
            continue

        # Insert vacancy_skill
        vs_stmt = pg_insert(VacancySkill).values(
            vacancy_id=vacancy_id,
            skill_id=skill_id,
            source="key_skills",
        )
        vs_stmt = vs_stmt.on_conflict_do_nothing()
        await session.execute(vs_stmt)

    await session.flush()
