"""Admin system configuration — GET/PATCH the SystemConfiguration key/value
store (rate, fine, OTP settings, regex patterns, auto-period durations)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_db
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.admin_user import AdminUser
from backend.schemas.system_config import SystemConfigResponse, SystemConfigUpdateRequest
from backend.services import system_config_service

router = APIRouter(
    prefix="/api/v1/admin/system-config", tags=["admin-system-config"], dependencies=[Depends(get_current_admin)]
)


@router.get("", response_model=list[SystemConfigResponse])
def list_config(db: Session = Depends(get_db)) -> list[SystemConfigResponse]:
    return [SystemConfigResponse.model_validate(c) for c in system_config_service.list_config(db)]


@router.patch("/{key}", response_model=SystemConfigResponse)
def update_config(
    key: str,
    payload: SystemConfigUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> SystemConfigResponse:
    try:
        config = system_config_service.update_config(db, admin, key, payload.value)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return SystemConfigResponse.model_validate(config)
