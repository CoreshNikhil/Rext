from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.models.mixins import TimestampMixin


class Meter(Base, TimestampMixin):
    __tablename__ = "meters"

    meter_id: Mapped[int] = mapped_column(primary_key=True)
    # "One active meter per resident" is enforced in the service layer, not
    # a DB constraint — deliberate prototype-stage simplification.
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.resident_id"), nullable=False)

    meter_serial_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    install_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
