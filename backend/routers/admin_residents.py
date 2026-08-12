"""Admin resident CRUD — every route requires an admin-scoped token via
get_current_admin, applied at the router level as defense-in-depth."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_db
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.admin_user import AdminUser
from backend.schemas.resident import (
    MeterCreateRequest,
    MeterResponse,
    ResidentCreateRequest,
    ResidentDetailResponse,
    ResidentResponse,
    ResidentUpdateRequest,
)
from backend.services import resident_service

router = APIRouter(
    prefix="/api/v1/admin/residents", tags=["admin-residents"], dependencies=[Depends(get_current_admin)]
)


@router.get("", response_model=list[ResidentResponse])
def list_residents(
    active_only: bool = False,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> list[ResidentResponse]:
    residents = resident_service.list_residents(db, active_only=active_only, search=search)
    return [ResidentResponse.model_validate(r) for r in residents]


@router.post("", response_model=ResidentResponse, status_code=201)
def create_resident(
    payload: ResidentCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ResidentResponse:
    try:
        resident = resident_service.create_resident(db, admin, payload)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ResidentResponse.model_validate(resident)


@router.get("/{resident_id}", response_model=ResidentDetailResponse)
def get_resident(resident_id: int, db: Session = Depends(get_db)) -> ResidentDetailResponse:
    try:
        resident = resident_service.get_resident(db, resident_id)
        meters = resident_service.list_meters(db, resident_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc

    detail = ResidentDetailResponse.model_validate(resident)
    detail.meters = [MeterResponse.model_validate(m) for m in meters]
    return detail


@router.patch("/{resident_id}", response_model=ResidentResponse)
def update_resident(
    resident_id: int,
    payload: ResidentUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ResidentResponse:
    try:
        resident = resident_service.update_resident(db, admin, resident_id, payload)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ResidentResponse.model_validate(resident)


@router.delete("/{resident_id}", response_model=ResidentResponse)
def deactivate_resident(
    resident_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ResidentResponse:
    """Soft-delete: sets is_active=False. Never a hard delete."""
    try:
        resident = resident_service.deactivate_resident(db, admin, resident_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ResidentResponse.model_validate(resident)


@router.post("/{resident_id}/reset-password", status_code=204)
def reset_resident_password(
    resident_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> None:
    try:
        resident_service.reset_resident_password(db, admin, resident_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc


@router.get("/{resident_id}/meters", response_model=list[MeterResponse])
def list_meters(resident_id: int, db: Session = Depends(get_db)) -> list[MeterResponse]:
    try:
        meters = resident_service.list_meters(db, resident_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return [MeterResponse.model_validate(m) for m in meters]


@router.post("/{resident_id}/meters", response_model=MeterResponse, status_code=201)
def assign_meter(
    resident_id: int,
    payload: MeterCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MeterResponse:
    try:
        meter = resident_service.assign_meter(
            db, admin, resident_id, payload.meter_serial_number, payload.install_date
        )
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterResponse.model_validate(meter)
