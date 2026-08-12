from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import OtpPurpose
from backend.db.types import UTCDateTime


class OtpRequest(Base):
    __tablename__ = "otp_requests"

    otp_id: Mapped[int] = mapped_column(primary_key=True)

    purpose: Mapped[OtpPurpose] = mapped_column(enum_column(OtpPurpose), nullable=False)
    # Set once the house_number+mobile combination is matched at signup;
    # null is possible only in the brief window before that match resolves.
    resident_id: Mapped[int | None] = mapped_column(ForeignKey("residents.resident_id"))
    mobile_number: Mapped[str] = mapped_column(String(15), nullable=False)

    # bcrypt-hashed — the raw OTP is never persisted.
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
