from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import ActorType
from backend.db.types import UTCDateTime


class AuditLog(Base):
    """Written through one backend/services/audit_service.py::record()
    helper called from the service layer, not scattered per-router — so
    coverage doesn't depend on remembering it at every call site."""

    __tablename__ = "audit_logs"

    audit_log_id: Mapped[int] = mapped_column(primary_key=True)

    actor_type: Mapped[ActorType] = mapped_column(enum_column(ActorType), nullable=False)
    # resident_id / admin_id / null(system) — meaning depends on actor_type.
    actor_id: Mapped[int | None] = mapped_column(Integer)

    action: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "reading.override"
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)

    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)

    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
