from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.models.mixins import TimestampMixin


class Fine(Base, TimestampMixin):
    """One row per day-accrued, not a running total — stored separately
    from Bill.amount_due so the original gas consumption calculation is
    never modified by late-fee accrual."""

    __tablename__ = "fines"
    # Idempotency key for the daily fine-accrual job: a second run on the
    # same day for the same bill is a no-op, not a duplicate charge.
    __table_args__ = (UniqueConstraint("bill_id", "accrual_date"),)

    fine_id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.bill_id"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    accrual_date: Mapped[date] = mapped_column(Date, nullable=False)
