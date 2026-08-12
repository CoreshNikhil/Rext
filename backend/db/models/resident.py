from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class Resident(Base, TimestampMixin):
    """resident_id is the real primary key / FK target everywhere.
    house_number is the resident-facing login identifier — unique, but
    never used as a foreign key, so a future house-numbering-format change
    never requires touching any other table."""

    __tablename__ = "residents"

    resident_id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.community_id"), nullable=False)

    house_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    mobile_number: Mapped[str] = mapped_column(String(15), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)

    # Null until the resident completes signup (OTP-verified + password set).
    password_hash: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
