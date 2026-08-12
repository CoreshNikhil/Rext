"""Meter reading submission (resident) and review (admin).

Two separate routers in one file, matching the design's grouping of
"meter reading" as one domain — but each still gets its own auth
dependency at the router level, never shared, per the same role-
separation pattern as every other router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_current_resident, get_db, get_vision_provider
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import MeterReadingStatus
from backend.db.models.resident import Resident
from backend.schemas.meter_reading import MeterReadingOverrideRequest, MeterReadingRejectRequest, MeterReadingResponse
from backend.services import meter_reading_service
from providers.base import ProviderError

resident_router = APIRouter(
    prefix="/api/v1/resident/meter-readings", tags=["resident-meter-readings"], dependencies=[Depends(get_current_resident)]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/meter-readings", tags=["admin-meter-readings"], dependencies=[Depends(get_current_admin)]
)


@resident_router.post("", response_model=MeterReadingResponse, status_code=201)
async def submit_meter_reading(
    file: UploadFile = File(...),
    resident: Resident = Depends(get_current_resident),
    db: Session = Depends(get_db),
) -> MeterReadingResponse:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        vision_provider = get_vision_provider()
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=f"Vision provider is not available: {exc}") from exc

    try:
        reading = meter_reading_service.submit_meter_reading(db, resident, image_bytes, vision_provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"The vision provider failed to process this image: {exc}") from exc
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc

    return MeterReadingResponse.model_validate(reading)


@resident_router.get("", response_model=list[MeterReadingResponse])
def list_own_readings(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> list[MeterReadingResponse]:
    readings = meter_reading_service.list_own_readings(db, resident)
    return [MeterReadingResponse.model_validate(r) for r in readings]


@resident_router.get("/{meter_reading_id}", response_model=MeterReadingResponse)
def get_own_reading(
    meter_reading_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> MeterReadingResponse:
    try:
        reading = meter_reading_service.get_own_reading_or_404(db, resident, meter_reading_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterReadingResponse.model_validate(reading)


@resident_router.get("/{meter_reading_id}/image")
def get_own_reading_image(
    meter_reading_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> FileResponse:
    try:
        reading = meter_reading_service.get_own_reading_or_404(db, resident, meter_reading_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return FileResponse(reading.image_path, media_type="image/jpeg")


@resident_router.post("/{meter_reading_id}/confirm", response_model=MeterReadingResponse)
def confirm_reading(
    meter_reading_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> MeterReadingResponse:
    try:
        reading = meter_reading_service.confirm_meter_reading(db, resident, meter_reading_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterReadingResponse.model_validate(reading)


@resident_router.post("/{meter_reading_id}/retake", response_model=MeterReadingResponse)
def retake_reading(
    meter_reading_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> MeterReadingResponse:
    try:
        reading = meter_reading_service.retake_meter_reading(db, resident, meter_reading_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterReadingResponse.model_validate(reading)


@admin_router.get("", response_model=list[MeterReadingResponse])
def list_readings_admin(
    billing_period_id: int | None = None,
    status: MeterReadingStatus | None = None,
    resident_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[MeterReadingResponse]:
    readings = meter_reading_service.list_readings_admin(
        db, billing_period_id=billing_period_id, status=status, resident_id=resident_id
    )
    return [MeterReadingResponse.model_validate(r) for r in readings]


@admin_router.get("/{meter_reading_id}", response_model=MeterReadingResponse)
def get_reading_admin(meter_reading_id: int, db: Session = Depends(get_db)) -> MeterReadingResponse:
    try:
        reading = meter_reading_service.get_reading_or_404(db, meter_reading_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterReadingResponse.model_validate(reading)


@admin_router.get("/{meter_reading_id}/image")
def get_reading_image_admin(meter_reading_id: int, db: Session = Depends(get_db)) -> FileResponse:
    try:
        reading = meter_reading_service.get_reading_or_404(db, meter_reading_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return FileResponse(reading.image_path, media_type="image/jpeg")


@admin_router.post("/{meter_reading_id}/override", response_model=MeterReadingResponse)
def override_reading(
    meter_reading_id: int,
    payload: MeterReadingOverrideRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MeterReadingResponse:
    try:
        reading = meter_reading_service.admin_override_reading(
            db, admin, meter_reading_id, payload.final_reading_value, payload.reason
        )
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterReadingResponse.model_validate(reading)


@admin_router.post("/{meter_reading_id}/reject", response_model=MeterReadingResponse)
def reject_reading(
    meter_reading_id: int,
    payload: MeterReadingRejectRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> MeterReadingResponse:
    try:
        reading = meter_reading_service.admin_reject_reading(db, admin, meter_reading_id, payload.reason)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return MeterReadingResponse.model_validate(reading)
