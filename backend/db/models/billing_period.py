from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import BillingPeriodStatus
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class BillingPeriod(Base, TimestampMixin):
    __tablename__ = "billing_periods"
    __table_args__ = (UniqueConstraint("community_id", "period_label"),)

    billing_period_id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.community_id"), nullable=False)

    period_label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2026-08"

    reading_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    reading_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    payment_due_date: Mapped[date] = mapped_column(Date, nullable=False)

    rate_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fine_per_day_overdue: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[BillingPeriodStatus] = mapped_column(
        enum_column(BillingPeriodStatus),
        default=BillingPeriodStatus.DRAFT,
        server_default=BillingPeriodStatus.DRAFT.value,
    )
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
