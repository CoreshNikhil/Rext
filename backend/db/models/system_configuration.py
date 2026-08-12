from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import ConfigValueType
from backend.db.types import UTCDateTime


class SystemConfiguration(Base):
    """Simple key/value store, string-serialized with a type tag driving
    parsing. Keyed by a human-readable string, not a surrogate ID —
    config keys are referenced by name throughout the codebase."""

    __tablename__ = "system_configuration"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[ConfigValueType] = mapped_column(
        enum_column(ConfigValueType), default=ConfigValueType.STRING, server_default=ConfigValueType.STRING.value
    )
    description: Mapped[str | None] = mapped_column(String(255))

    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), onupdate=func.now())
    updated_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.admin_id"))
