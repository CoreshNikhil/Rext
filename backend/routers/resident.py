"""Resident's own profile and home dashboard — distinct from
admin_residents.py, which is the admin-facing CRUD surface over the same
Resident table."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_current_resident, get_db
from backend.db.models.resident import Resident
from backend.schemas.resident import MeterResponse, ResidentDetailResponse, ResidentHomeResponse, ResidentSelfUpdateRequest
from backend.services import resident_service

router = APIRouter(prefix="/api/v1/resident", tags=["resident-profile"], dependencies=[Depends(get_current_resident)])


def _to_detail_response(db: Session, resident: Resident) -> ResidentDetailResponse:
    detail = ResidentDetailResponse.model_validate(resident)
    detail.meters = [MeterResponse.model_validate(m) for m in resident_service.list_meters(db, resident.resident_id)]
    return detail


@router.get("/me", response_model=ResidentDetailResponse)
def get_own_profile(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> ResidentDetailResponse:
    return _to_detail_response(db, resident)


@router.patch("/me", response_model=ResidentDetailResponse)
def update_own_profile(
    payload: ResidentSelfUpdateRequest,
    resident: Resident = Depends(get_current_resident),
    db: Session = Depends(get_db),
) -> ResidentDetailResponse:
    updated = resident_service.update_own_email(db, resident, payload.email)
    return _to_detail_response(db, updated)


@router.get("/home", response_model=ResidentHomeResponse)
def get_home(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> ResidentHomeResponse:
    return resident_service.get_home_summary(db, resident)
