"""RelevanceTerm ORM model — конфигурируемые словари релевантности (FR-44)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Index, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RelevanceTerm(Base):
    __tablename__ = "relevance_terms"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False)  # 'positive' / 'stop'
    field_scope: Mapped[str] = mapped_column(
        Text, default="any", server_default="'any'")
    weight: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=1.0, server_default="1.0")
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("term", "kind", "field_scope",
                         name="uq_relevance_terms_term_kind_scope"),
        Index("ix_relevance_terms_kind_active", "kind", "active"),
    )
