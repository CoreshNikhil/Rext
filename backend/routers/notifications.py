"""Resident and admin notification inbox endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_current_resident, get_db
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.resident import Resident
from backend.schemas.notification import NotificationResponse
from backend.services import notification_service

resident_router = APIRouter(
    prefix="/api/v1/resident/notifications", tags=["resident-notifications"], dependencies=[Depends(get_current_resident)]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/notifications", tags=["admin-notifications"], dependencies=[Depends(get_current_admin)]
)


@resident_router.get("", response_model=list[NotificationResponse])
def list_own_notifications(
    resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> list[NotificationResponse]:
    notifications = notification_service.list_own_notifications(db, resident)
    return [NotificationResponse.model_validate(n) for n in notifications]


@resident_router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_own_notification_read(
    notification_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> NotificationResponse:
    try:
        notification = notification_service.get_own_notification_or_404(db, resident, notification_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return NotificationResponse.model_validate(notification_service.mark_read(db, notification))


@admin_router.get("", response_model=list[NotificationResponse])
def list_admin_notifications(db: Session = Depends(get_db)) -> list[NotificationResponse]:
    notifications = notification_service.list_admin_notifications(db)
    return [NotificationResponse.model_validate(n) for n in notifications]


@admin_router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_admin_notification_read(notification_id: int, db: Session = Depends(get_db)) -> NotificationResponse:
    try:
        notification = notification_service.get_admin_notification_or_404(db, notification_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return NotificationResponse.model_validate(notification_service.mark_read(db, notification))
