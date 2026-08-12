from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import MeterReadingStatus, SubmittedBy
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime
from models.meter_result import ReviewStatus


class MeterReading(Base, TimestampMixin):
    """The integration point with MeterVision. ai_status reuses
    models.meter_result.ReviewStatus directly (not a redefinition) — one
    canonical source of truth for the AI's own accepted/needs_review/
    rejected assessment. `status` is a separate column tracking this
    system's own resident-submission workflow (see MeterReadingStatus)."""

    __tablename__ = "meter_readings"
    __table_args__ = (UniqueConstraint("billing_period_id", "resident_id"),)

    meter_reading_id: Mapped[int] = mapped_column(primary_key=True)
    billing_period_id: Mapped[int] = mapped_column(ForeignKey("billing_periods.billing_period_id"), nullable=False)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.meter_id"), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.resident_id"), nullable=False)

    image_path: Mapped[str] = mapped_column(String(500), nullable=False)

    previous_reading_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    submitted_reading_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    raw_digits: Mapped[str | None] = mapped_column(String(20))
    unit: Mapped[str | None] = mapped_column(String(20))

    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    ai_status: Mapped[ReviewStatus | None] = mapped_column(enum_column(ReviewStatus))
    ai_reason: Mapped[str | None] = mapped_column(Text)
    ai_validation_notes: Mapped[list | None] = mapped_column(JSON)

    status: Mapped[MeterReadingStatus] = mapped_column(
        enum_column(MeterReadingStatus),
        default=MeterReadingStatus.SUBMITTED,
        server_default=MeterReadingStatus.SUBMITTED.value,
    )
    submitted_by: Mapped[SubmittedBy] = mapped_column(
        enum_column(SubmittedBy), default=SubmittedBy.RESIDENT, server_default=SubmittedBy.RESIDENT.value
    )
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.admin_id"))

    final_reading_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

    resident_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    admin_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
