"""Notification creation/listing.

Called both from request-time services (rarely) and, mostly, from the
background jobs in jobs/definitions.py. Admin notifications are broadcast
(admin_id left null) — reasonable at this prototype's single-community,
small-admin-count scale; a future multi-admin/multi-community version
would target a specific admin_id instead.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.core.domain_exceptions import NotFoundError
from backend.db.models.enums import NotificationChannel, NotificationType, RecipientType
from backend.db.models.notification import Notification
from backend.db.models.resident import Resident


def _now() -> datetime:
    return datetime.now(timezone.utc)


def notify_resident(
    db: Session,
    resident_id: int,
    type: NotificationType,
    title: str,
    message: str,
    *,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
) -> Notification:
    notification = Notification(
        recipient_type=RecipientType.RESIDENT,
        resident_id=resident_id,
        type=type,
        channel=NotificationChannel.IN_APP,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        sent_at=_now(),
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def notify_admin(
    db: Session,
    type: NotificationType,
    title: str,
    message: str,
    *,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
) -> Notification:
    notification = Notification(
        recipient_type=RecipientType.ADMIN,
        admin_id=None,
        type=type,
        channel=NotificationChannel.IN_APP,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        sent_at=_now(),
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def resident_notification_already_sent_today(
    db: Session, resident_id: int, type: NotificationType, related_entity_id: int | None
) -> bool:
    """Idempotency check for daily jobs — prevents duplicate reminders if
    a job is re-run or double-fires on the same day."""
    today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)
    existing = (
        db.query(Notification)
        .filter(
            Notification.resident_id == resident_id,
            Notification.type == type,
            Notification.related_entity_id == related_entity_id,
            Notification.created_at >= today_start,
        )
        .first()
    )
    return existing is not None


def get_own_notification_or_404(db: Session, resident: Resident, notification_id: int) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.resident_id != resident.resident_id:
        raise NotFoundError(f"Notification {notification_id} not found.")
    return notification


def get_admin_notification_or_404(db: Session, notification_id: int) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.recipient_type != RecipientType.ADMIN:
        raise NotFoundError(f"Notification {notification_id} not found.")
    return notification


def list_own_notifications(db: Session, resident: Resident) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.resident_id == resident.resident_id)
        .order_by(Notification.created_at.desc())
        .all()
    )


def list_admin_notifications(db: Session) -> list[Notification]:
    return db.query(Notification).filter(Notification.recipient_type == RecipientType.ADMIN).order_by(Notification.created_at.desc()).all()


def mark_read(db: Session, notification: Notification) -> Notification:
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification
