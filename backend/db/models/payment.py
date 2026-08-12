from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import PaymentStatus
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    payment_id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.bill_id"), nullable=False)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.resident_id"), nullable=False)

    # Always copied from Bill.total_amount_due server-side — never accepted
    # from a client request body.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(30), nullable=False)  # "mock" today
    provider_reference_id: Mapped[str | None] = mapped_column(String(100))

    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus), default=PaymentStatus.INITIATED, server_default=PaymentStatus.INITIATED.value
    )

    initiated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    failure_reason: Mapped[str | None] = mapped_column(Text)
