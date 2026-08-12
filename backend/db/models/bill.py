from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import BillStatus
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class Bill(Base, TimestampMixin):
    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("billing_period_id", "resident_id"),)

    bill_id: Mapped[int] = mapped_column(primary_key=True)
    billing_period_id: Mapped[int] = mapped_column(ForeignKey("billing_periods.billing_period_id"), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.resident_id"), nullable=False)
    meter_reading_id: Mapped[int | None] = mapped_column(ForeignKey("meter_readings.meter_reading_id"))

    previous_reading_value: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    current_reading_value: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    # Server-computed: current - previous. Never accepted from a client.
    consumption_units: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    # Snapshotted from BillingPeriod at generation time — a later admin
    # rate change must never retroactively alter an already-issued bill.
    rate_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Server-computed: consumption_units * rate_per_unit.
    amount_due: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    fine_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    total_amount_due: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[BillStatus] = mapped_column(
        enum_column(BillStatus), default=BillStatus.ISSUED, server_default=BillStatus.ISSUED.value
    )

    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
