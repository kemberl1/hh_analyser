"""VacancySource — abstract interface for vacancy data sources (AD-3)."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawVacancy:
    """Raw vacancy data extracted from source (before relevance filtering / normalization)."""

    hh_vacancy_id: int
    title: str
    url: str | None = None
    employer_name: str | None = None
    employer_id: int | None = None  # hh employer id
    employer_url: str | None = None
    salary_from: float | None = None
    salary_to: float | None = None
    salary_currency: str | None = None
    salary_gross: bool | None = None
    experience_raw: str | None = None
    employment_format: str | None = None
    area_name: str | None = None
    published_at: datetime | None = None
    description: str | None = None
    skills: list[str] = field(default_factory=list)
    source_type: str = "html"
    raw_html: str | None = None
    raw_payload: dict[str, Any] | None = None


class VacancySource(abc.ABC):
    """Abstract interface for fetching vacancies from hh.ru (AD-3, FR-2/FR-3)."""

    @abc.abstractmethod
    async def fetch_vacancies(self, max_pages: int | None = None) -> list[RawVacancy]:
        """Fetch raw vacancy data. Returns list of RawVacancy."""
        ...

    @abc.abstractmethod
    def source_name(self) -> str:
        """Return human-readable source name for logging."""
        ...
