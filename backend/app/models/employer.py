"""Employer ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    hh_employer_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    trusted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vacancies: Mapped[list["Vacancy"]] = relationship(  # noqa: F821
        back_populates="employer", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_employers_name", "name"),
    )
