"""Seed script — populate initial relevance_terms and skill_aliases.

Run via CLI: python -m app.cli seed
Or called programmatically during ingestion if tables are empty.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.relevance_term import RelevanceTerm

logger = structlog.get_logger(__name__)

# ── Positive markers (Frontend) ──────────────────────────────────────────
POSITIVE_TERMS = [
    # English
    ("frontend", "any", 2.0),
    ("front-end", "any", 2.0),
    ("front end", "any", 2.0),
    ("react", "any", 1.5),
    ("vue", "any", 1.5),
    ("vue.js", "any", 1.5),
    ("angular", "any", 1.5),
    ("javascript", "any", 1.0),
    ("typescript", "any", 1.0),
    ("html", "any", 0.5),
    ("css", "any", 0.5),
    ("sass", "any", 0.5),
    ("scss", "any", 0.5),
    ("less", "any", 0.5),
    ("webpack", "any", 0.5),
    ("vite", "any", 0.5),
    ("next.js", "any", 1.0),
    ("nextjs", "any", 1.0),
    ("nuxt", "any", 1.0),
    ("svelte", "any", 1.0),
    ("redux", "any", 0.5),
    ("mobx", "any", 0.5),
    ("tailwind", "any", 0.5),
    # Russian
    ("фронтенд", "any", 2.0),
    ("фронт-энд", "any", 2.0),
    ("фронтэнд", "any", 2.0),
    ("верстка", "any", 1.0),
    ("верстальщик", "any", 1.5),
    ("вёрстка", "any", 1.0),
]

# ── Stop-signals (irrelevant roles) ──────────────────────────────────────
STOP_TERMS = [
    # Fullstack / Backend
    ("fullstack", "any", 2.0),
    ("full-stack", "any", 2.0),
    ("full stack", "any", 2.0),
    ("фуллстек", "any", 2.0),
    ("фулстек", "any", 2.0),
    ("фулл-стек", "any", 2.0),
    ("backend", "any", 2.0),
    ("back-end", "any", 2.0),
    ("back end", "any", 2.0),
    ("бэкенд", "any", 2.0),
    ("бекенд", "any", 2.0),
    ("бэк-энд", "any", 2.0),
    # Management / PM
    ("руководитель проект", "any", 3.0),
    ("руководитель проектов", "any", 3.0),
    ("project manager", "any", 3.0),
    ("менеджер проект", "any", 3.0),
    ("product manager", "any", 3.0),
    ("продакт менеджер", "any", 3.0),
    ("продукт менеджер", "any", 3.0),
    ("тимлид", "any", 1.0),
    ("team lead", "any", 1.0),
    # QA / Testing
    ("qa", "title", 3.0),
    ("тестировщик", "any", 3.0),
    ("тестирование", "title", 2.0),
    ("quality assurance", "any", 3.0),
    ("автоматизатор тестирования", "any", 3.0),
    # DevOps / Infra
    ("devops", "any", 3.0),
    ("девопс", "any", 3.0),
    ("sre", "title", 3.0),
    ("системный администратор", "any", 3.0),
    ("infrastructure", "title", 2.0),
    # Analytics / Data
    ("аналитик", "title", 3.0),
    ("analyst", "title", 3.0),
    ("data engineer", "any", 3.0),
    ("data scientist", "any", 3.0),
    ("дата инженер", "any", 3.0),
    ("bi разработчик", "any", 3.0),
    # Design
    ("дизайнер", "title", 3.0),
    ("designer", "title", 3.0),
    ("ux/ui", "title", 2.0),
    ("ui/ux", "title", 2.0),
    ("графический дизайнер", "any", 3.0),
    # Other irrelevant
    ("ios", "title", 2.0),
    ("android", "title", 2.0),
    ("mobile", "title", 2.0),
    ("мобильный", "title", 2.0),
    ("1с", "title", 3.0),
    ("1c", "title", 3.0),
    ("sap", "title", 3.0),
    ("java ", "title", 1.5),  # note trailing space to avoid "javascript"
    ("python", "title", 1.5),
    ("c#", "title", 2.0),
    (".net", "title", 2.0),
    ("php", "title", 1.5),
    ("golang", "title", 2.0),
    ("go разработчик", "title", 2.0),
    ("rust", "title", 2.0),
]


async def seed_relevance_terms(session: AsyncSession) -> int:
    """Insert seed relevance_terms if not already present.

    Returns number of terms inserted.
    """
    count = 0

    for term, scope, weight in POSITIVE_TERMS:
        stmt = pg_insert(RelevanceTerm).values(
            term=term.lower(),
            kind="positive",
            field_scope=scope,
            weight=weight,
            active=True,
        )
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_relevance_terms_term_kind_scope"
        )
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:
            count += result.rowcount

    for term, scope, weight in STOP_TERMS:
        stmt = pg_insert(RelevanceTerm).values(
            term=term.lower(),
            kind="stop",
            field_scope=scope,
            weight=weight,
            active=True,
        )
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_relevance_terms_term_kind_scope"
        )
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:
            count += result.rowcount

    await session.commit()
    logger.info("relevance_terms_seeded", inserted=count)
    return count
