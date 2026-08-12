"""Shared column mixins for ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.types import UTCDateTime


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), onupdate=func.now())
