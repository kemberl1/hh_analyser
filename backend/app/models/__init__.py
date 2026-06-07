"""ORM models — import all models here so Alembic sees them via Base.metadata."""

from app.db.base import Base  # noqa: F401

from app.models.currency_rate import CurrencyRate  # noqa: F401
from app.models.employer import Employer  # noqa: F401
from app.models.filtered_vacancy import FilteredVacancy  # noqa: F401
from app.models.grade import Grade  # noqa: F401
from app.models.ingestion_run import IngestionRun  # noqa: F401
from app.models.relevance_term import RelevanceTerm  # noqa: F401
from app.models.salary import Salary  # noqa: F401
from app.models.skill import Skill, SkillAlias  # noqa: F401
from app.models.vacancy import Vacancy  # noqa: F401
from app.models.vacancy_skill import VacancySkill  # noqa: F401
