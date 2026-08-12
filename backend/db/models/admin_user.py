from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import AdminRole
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class AdminUser(Base, TimestampMixin):
    """Fully separate identity table from Resident — structurally
    enforces "admin auth never shares a table with resident auth"."""

    __tablename__ = "admin_users"

    admin_id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.community_id"), nullable=False)

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[AdminRole] = mapped_column(
        enum_column(AdminRole), default=AdminRole.ADMIN, server_default=AdminRole.ADMIN.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
