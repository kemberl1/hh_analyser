"""Salary ORM model — зарплата (1:1 с вакансией)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Salary(Base):
    __tablename__ = "salaries"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vacancies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    amount_from: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True)
    amount_to: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    gross: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    amount_from_rub_net: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True)
    amount_to_rub_net: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True)
    point_estimate_rub_net: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    vacancy: Mapped["Vacancy"] = relationship(  # noqa: F821
        back_populates="salary", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_salaries_point_estimate", "point_estimate_rub_net"),
    )
