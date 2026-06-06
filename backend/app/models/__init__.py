"""ORM models — import all models here so Alembic sees them via Base.metadata."""

from app.db.base import Base  # noqa: F401

# Models will be added in Phase 2 migrations.
# Import them here when created so metadata is populated:
# from app.models.employer import Employer  # noqa: F401
# from app.models.vacancy import Vacancy  # noqa: F401
# ...
