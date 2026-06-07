"""CurrencyRate ORM model — курсы валют."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CurrencyRate(Base):
    __tablename__ = "currency_rates"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    rate_to_rub: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False)

    __table_args__ = (
        UniqueConstraint("currency", "rate_date",
                         name="uq_currency_rates_currency_date"),
    )
