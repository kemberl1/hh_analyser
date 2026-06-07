"""Grade ORM model (справочник грейдов)."""

from __future__ import annotations

from sqlalchemy import SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    vacancies: Mapped[list["Vacancy"]] = relationship(  # noqa: F821
        back_populates="grade", lazy="selectin"
    )
