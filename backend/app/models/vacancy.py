"""Vacancy ORM model — центральная таблица."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    hh_vacancy_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    employer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employers.id", ondelete="SET NULL"), nullable=True
    )
    grade_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("grades.id"), nullable=True
    )
    experience_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    employment_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    hh_created_at: Mapped[datetime | None] = mapped_column(nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    source_type: Mapped[str] = mapped_column(
        Text, default="html", server_default="'html'")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingestion_runs.id"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    employer: Mapped["Employer"] = relationship(  # noqa: F821
        back_populates="vacancies", lazy="selectin"
    )
    grade: Mapped["Grade"] = relationship(  # noqa: F821
        back_populates="vacancies", lazy="selectin"
    )
    salary: Mapped["Salary | None"] = relationship(  # noqa: F821
        back_populates="vacancy", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    vacancy_skills: Mapped[list["VacancySkill"]] = relationship(  # noqa: F821
        back_populates="vacancy", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_vacancies_grade_published", "grade_id", "published_at"),
        Index("ix_vacancies_employer", "employer_id"),
    )
