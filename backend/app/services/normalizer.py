"""Normalizer — deterministic transformation of raw vacancy data to domain model.

Handles: salary normalization (currency→RUB, gross→net, point_estimate),
employer upsert, skill canonicalization, grade resolution (AFTER relevance filter, FR-47),
employment format, published_at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.services.source_interface import RawVacancy

logger = structlog.get_logger(__name__)


@dataclass
class NormalizedSalary:
    """Normalized salary data ready for DB."""

    amount_from: float | None = None
    amount_to: float | None = None
    currency: str | None = None
    gross: bool | None = None
    amount_from_rub_net: float | None = None
    amount_to_rub_net: float | None = None
    point_estimate_rub_net: float | None = None


@dataclass
class NormalizedVacancy:
    """Fully normalized vacancy ready for DB upsert."""

    hh_vacancy_id: int
    title: str
    url: str | None = None
    employer_name: str | None = None
    employer_hh_id: int | None = None
    employer_url: str | None = None
    salary: NormalizedSalary | None = None
    experience_raw: str | None = None
    employment_format: str = "unknown"
    area_name: str | None = None
    published_at: datetime | None = None
    grade_code: str = "unknown"  # junior/middle/senior/unknown
    skills: list[str] = field(default_factory=list)
    source_type: str = "html"
    raw_html: str | None = None
    raw_payload: dict | None = None


class Normalizer:
    """Deterministic, testable normalization of raw vacancy data."""

    def __init__(self, ndfl_rate: float | None = None) -> None:
        self._ndfl = ndfl_rate if ndfl_rate is not None else settings.NDFL_RATE

    def normalize(self, raw: RawVacancy) -> NormalizedVacancy:
        """Normalize a single raw vacancy."""
        salary = self._normalize_salary(raw)
        grade = self._resolve_grade(raw)
        skills = self._canonicalize_skills(raw.skills)
        employment = raw.employment_format or "unknown"
        published = raw.published_at or datetime.now(timezone.utc)

        return NormalizedVacancy(
            hh_vacancy_id=raw.hh_vacancy_id,
            title=raw.title,
            url=raw.url,
            employer_name=raw.employer_name,
            employer_hh_id=raw.employer_id,
            employer_url=raw.employer_url,
            salary=salary,
            experience_raw=raw.experience_raw,
            employment_format=employment,
            area_name=raw.area_name,
            published_at=published,
            grade_code=grade,
            skills=skills,
            source_type=raw.source_type,
            raw_html=raw.raw_html,
            raw_payload=raw.raw_payload,
        )

    def _normalize_salary(self, raw: RawVacancy) -> NormalizedSalary | None:
        """Normalize salary: currency→RUB, gross→net, point_estimate."""
        if raw.salary_from is None and raw.salary_to is None:
            return None

        currency = (raw.salary_currency or "RUR").upper()
        gross = raw.salary_gross

        # For Phase 2 MVP: only handle RUR/RUB directly.
        # Currency conversion requires currency_rates table; placeholder.
        rate_to_rub = self._get_rate_to_rub(currency)

        amount_from = raw.salary_from
        amount_to = raw.salary_to

        # Convert to RUB
        from_rub = amount_from * rate_to_rub if amount_from else None
        to_rub = amount_to * rate_to_rub if amount_to else None

        # Gross → Net
        from_rub_net = self._gross_to_net(from_rub, gross)
        to_rub_net = self._gross_to_net(to_rub, gross)

        # Point estimate (§04-metrics 1.4)
        point_estimate = self._calc_point_estimate(from_rub_net, to_rub_net)

        return NormalizedSalary(
            amount_from=amount_from,
            amount_to=amount_to,
            currency=currency,
            gross=gross,
            amount_from_rub_net=from_rub_net,
            amount_to_rub_net=to_rub_net,
            point_estimate_rub_net=point_estimate,
        )

    def _gross_to_net(self, amount: float | None, gross: bool | None) -> float | None:
        """Convert gross to net. If gross is None, assume gross (conservative)."""
        if amount is None:
            return None
        if gross is True or gross is None:
            return round(amount * (1 - self._ndfl), 2)
        return round(amount, 2)

    @staticmethod
    def _get_rate_to_rub(currency: str) -> float:
        """Get exchange rate to RUB.

        Phase 2 MVP: RUR/RUB=1.0, USD≈90, EUR≈100 (hardcoded fallback).
        Full implementation with currency_rates table in later phases.
        """
        rates = {
            "RUR": 1.0,
            "RUB": 1.0,
            "USD": 90.0,
            "EUR": 100.0,
            "KZT": 0.2,
            "UAH": 2.5,
            "BYR": 28.0,
            "GEL": 34.0,
            "UZS": 0.007,
        }
        return rates.get(currency, 1.0)

    @staticmethod
    def _calc_point_estimate(
        from_net: float | None, to_net: float | None
    ) -> float | None:
        """Calculate point estimate for metrics (§04-metrics 1.4)."""
        if from_net is not None and to_net is not None:
            return round((from_net + to_net) / 2, 2)
        if from_net is not None:
            return from_net
        if to_net is not None:
            return to_net
        return None

    @staticmethod
    def _resolve_grade(raw: RawVacancy) -> str:
        """Determine grade: Junior/Middle/Senior/unknown (FR-6, FR-47).

        Called AFTER relevance filter.
        Hybrid heuristic by experience field and title/description keywords.
        Priority: explicit keyword in title > experience field > unknown.
        """
        title = (raw.title or "").lower()
        description = (raw.description or "").lower()
        experience = (raw.experience_raw or "").lower()

        # Title keywords (highest priority)
        title_grade = _match_grade_keywords(title)
        if title_grade:
            return title_grade

        # Description keywords
        desc_grade = _match_grade_keywords(description)
        if desc_grade:
            return desc_grade

        # Experience field mapping
        exp_mapping = {
            "noexperience": "junior",
            "between1and3": "middle",
            "between3and6": "senior",
            "morethan6": "senior",
        }
        # Normalize experience string (hh.ru may return text like "Нет опыта")
        exp_clean = experience.replace(" ", "").replace("-", "")
        for key, grade in exp_mapping.items():
            if key in exp_clean:
                return grade

        # Russian experience text heuristics
        if "нет опыта" in experience or "без опыта" in experience:
            return "junior"
        if "1–3" in experience or "от 1 до 3" in experience:
            return "middle"
        if "3–6" in experience or "от 3 до 6" in experience:
            return "senior"
        if "более 6" in experience or "6 и более" in experience:
            return "senior"

        return "unknown"

    @staticmethod
    def _canonicalize_skills(skills: list[str]) -> list[str]:
        """Canonicalize skill names: lowercase, strip, deduplicate.

        Full alias resolution via skill_aliases table done in persistence layer.
        """
        seen: set[str] = set()
        result: list[str] = []
        for s in skills:
            canonical = s.strip().lower()
            canonical = re.sub(r"\s+", " ", canonical)
            if canonical and canonical not in seen:
                seen.add(canonical)
                result.append(canonical)
        return result


def _match_grade_keywords(text: str) -> str | None:
    """Match grade keywords in text."""
    # Order matters: check longer patterns first
    junior_patterns = [
        r"\bjunior\b", r"\bjun\b", r"\bджуниор\b", r"\bджун\b",
        r"\bмладший\b", r"\bстажер\b", r"\bстажёр\b", r"\bintern\b",
    ]
    middle_patterns = [
        r"\bmiddle\b", r"\bmid\b", r"\bмидл\b", r"\bмидлл\b",
    ]
    senior_patterns = [
        r"\bsenior\b", r"\bsr\b", r"\bсеньор\b", r"\bсиньор\b",
        r"\bведущий\b", r"\blead\b", r"\bтехлид\b", r"\btech\s*lead\b",
        r"\bпринципал\b", r"\bprincipal\b",
    ]

    for pat in senior_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return "senior"
    for pat in middle_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return "middle"
    for pat in junior_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return "junior"

    return None
