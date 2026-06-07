"""Skill and SkillAlias ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    aliases: Mapped[list["SkillAlias"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", lazy="selectin"
    )
    vacancy_skills: Mapped[list["VacancySkill"]] = relationship(  # noqa: F821
        back_populates="skill", lazy="selectin"
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    skill: Mapped["Skill"] = relationship(
        back_populates="aliases", lazy="selectin")
