from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.models.mixins import TimestampMixin


class Community(Base, TimestampMixin):
    """Modeled now purely so no foreign key ever needs retrofitting for
    multi-tenancy later. Today there is exactly one row."""

    __tablename__ = "communities"

    community_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", server_default="Asia/Kolkata")
