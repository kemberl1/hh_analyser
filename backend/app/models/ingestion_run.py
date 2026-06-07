"""IngestionRun ORM model — журнал прогонов сбора."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="running")
    found_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    created_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    filtered_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    api_fallback_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    captcha_block_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
