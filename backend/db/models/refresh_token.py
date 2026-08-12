from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import TokenSubjectType
from backend.db.types import UTCDateTime


class RefreshToken(Base):
    """Stored server-side (hashed, never the raw token) so /auth/logout can
    actually revoke — pure-stateless JWTs can't support real logout. Each
    refresh rotates: the old row is marked revoked_at, and the new row's
    replaced_by_token_id links the chain, enabling reuse-detection."""

    __tablename__ = "refresh_tokens"

    refresh_token_id: Mapped[int] = mapped_column(primary_key=True)

    subject_type: Mapped[TokenSubjectType] = mapped_column(enum_column(TokenSubjectType), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)  # resident_id or admin_id

    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    replaced_by_token_id: Mapped[int | None] = mapped_column(ForeignKey("refresh_tokens.refresh_token_id"))
