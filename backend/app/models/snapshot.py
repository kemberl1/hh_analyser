"""Snapshot ORM model — precomputed aggregations (Phase 4, §2.10 data-model)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, Index, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    metric_type: Mapped[str] = mapped_column(Text, nullable=False)
    period_type: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    grade_id: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    gross_basis: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "metric_type", "period_type", "period_start",
            "grade_id", "currency", "gross_basis",
            name="uq_snapshots_slice",
        ),
        Index(
            "ix_snapshots_lookup",
            "metric_type", "period_type", "period_start",
        ),
    )
