from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import NotificationChannel, NotificationType, RecipientType
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(primary_key=True)

    recipient_type: Mapped[RecipientType] = mapped_column(enum_column(RecipientType), nullable=False)
    resident_id: Mapped[int | None] = mapped_column(ForeignKey("residents.resident_id"))
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.admin_id"))

    type: Mapped[NotificationType] = mapped_column(enum_column(NotificationType), nullable=False)
    # Only IN_APP is actually delivered today; SMS_MOCK/EMAIL_MOCK are
    # logged-only mock sends (see backend/providers/).
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_column(NotificationChannel), default=NotificationChannel.IN_APP, server_default=NotificationChannel.IN_APP.value
    )

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    related_entity_type: Mapped[str | None] = mapped_column(String(30))
    related_entity_id: Mapped[int | None] = mapped_column(Integer)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
