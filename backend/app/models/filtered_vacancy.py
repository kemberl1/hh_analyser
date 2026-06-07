"""FilteredVacancy ORM model — аудит отфильтрованных (опционально, FR-46)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FilteredVacancy(Base):
    __tablename__ = "filtered_vacancies"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    hh_vacancy_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_stopword: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingestion_runs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_filtered_vacancies_run", "ingestion_run_id"),
        Index("ix_filtered_vacancies_hh_id", "hh_vacancy_id"),
    )
