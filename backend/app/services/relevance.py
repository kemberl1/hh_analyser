"""Relevance Filter — rule-based scoring (§2.3a, FR-41–FR-47).

Pipeline: parse → **relevance filter** → normalize → persist.
Irrelevant vacancies (Fullstack, Backend, PM, QA, DevOps, analyst, designer, etc.)
are rejected and NOT saved to the vacancies table.

Scoring: score = Σ(positive weights) − Σ(stop weights)
Title signals are multiplied by RELEVANCE_TITLE_WEIGHT_MULTIPLIER.
Hard stop-signals in title cause immediate rejection (configurable).
Threshold: score >= RELEVANCE_THRESHOLD → relevant.
Dictionaries loaded from `relevance_terms` table (configurable, FR-44).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.relevance_term import RelevanceTerm
from app.services.source_interface import RawVacancy

logger = structlog.get_logger(__name__)


@dataclass
class RelevanceResult:
    """Result of relevance check for a single vacancy."""

    relevant: bool
    score: float
    reason: str | None = None  # 'stopword', 'low_score', 'hard_stop_title'
    matched_stopword: str | None = None


@dataclass
class TermEntry:
    """In-memory representation of a relevance term."""

    term: str
    kind: str  # 'positive' / 'stop'
    field_scope: str  # 'title' / 'description' / 'any'
    weight: float


class RelevanceFilter:
    """Rule-based relevance filter for raw vacancies.

    Loads dictionaries from DB (relevance_terms table) on init.
    Falls back to empty if table has no data.
    """

    def __init__(self, terms: list[TermEntry] | None = None) -> None:
        self._terms = terms or []
        self._threshold = settings.RELEVANCE_THRESHOLD
        self._hard_stop_on_title = settings.RELEVANCE_HARD_STOP_ON_TITLE
        self._title_multiplier = settings.RELEVANCE_TITLE_WEIGHT_MULTIPLIER

    @classmethod
    async def from_db(cls, session: AsyncSession) -> "RelevanceFilter":
        """Load active terms from relevance_terms table."""
        result = await session.execute(
            select(RelevanceTerm).where(RelevanceTerm.active.is_(True))
        )
        rows = result.scalars().all()
        terms = [
            TermEntry(
                term=r.term.lower(),
                kind=r.kind,
                field_scope=r.field_scope,
                weight=float(r.weight),
            )
            for r in rows
        ]
        logger.info("relevance_terms_loaded", positive=sum(1 for t in terms if t.kind == "positive"),
                    stop=sum(1 for t in terms if t.kind == "stop"))
        return cls(terms=terms)

    def check(self, vacancy: RawVacancy) -> RelevanceResult:
        """Check if a vacancy is relevant (Frontend) or junk.

        Returns RelevanceResult with score and decision.
        """
        title = (vacancy.title or "").lower()
        description = (vacancy.description or "").lower()
        skills_text = " ".join(
            vacancy.skills).lower() if vacancy.skills else ""

        # Combine description + skills for 'description' scope
        body = f"{description} {skills_text}"

        score = 0.0
        matched_stop: str | None = None

        for term_entry in self._terms:
            pattern = re.compile(re.escape(term_entry.term), re.IGNORECASE)

            # Check title match
            title_match = bool(pattern.search(title))
            # Check body (description + skills) match
            body_match = bool(pattern.search(body))

            # Determine which scopes apply
            applies_title = term_entry.field_scope in ("title", "any")
            applies_body = term_entry.field_scope in ("description", "any")

            weight = term_entry.weight

            if term_entry.kind == "positive":
                if title_match and applies_title:
                    score += weight * self._title_multiplier
                if body_match and applies_body:
                    score += weight
            elif term_entry.kind == "stop":
                # Hard stop on title (FR-43)
                if title_match and applies_title:
                    if self._hard_stop_on_title:
                        return RelevanceResult(
                            relevant=False,
                            score=-999.0,
                            reason="hard_stop_title",
                            matched_stopword=term_entry.term,
                        )
                    score -= weight * self._title_multiplier
                    matched_stop = term_entry.term
                if body_match and applies_body:
                    score -= weight
                    if not matched_stop:
                        matched_stop = term_entry.term

        if score >= self._threshold:
            return RelevanceResult(relevant=True, score=score)
        else:
            return RelevanceResult(
                relevant=False,
                score=score,
                reason="low_score",
                matched_stopword=matched_stop,
            )
