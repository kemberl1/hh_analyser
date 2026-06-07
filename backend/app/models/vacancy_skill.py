"""VacancySkill ORM model — M:N связь вакансия ↔ навык."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class VacancySkill(Base):
    __tablename__ = "vacancy_skills"

    vacancy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(
        Text, default="key_skills", server_default="'key_skills'"
    )

    vacancy: Mapped["Vacancy"] = relationship(  # noqa: F821
        back_populates="vacancy_skills", lazy="selectin"
    )
    skill: Mapped["Skill"] = relationship(  # noqa: F821
        back_populates="vacancy_skills", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_vacancy_skills_skill_id", "skill_id"),
    )
