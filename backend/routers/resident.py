"""Resident's own profile and home dashboard — distinct from
admin_residents.py, which is the admin-facing CRUD surface over the same
Resident table."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_current_resident, get_db
from backend.db.models.resident import Resident
from backend.schemas.resident import MeterResponse, ResidentDetailResponse, ResidentHomeResponse
from backend.services import resident_service

router = APIRouter(prefix="/api/v1/resident", tags=["resident-profile"], dependencies=[Depends(get_current_resident)])


@router.get("/me", response_model=ResidentDetailResponse)
def get_own_profile(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> ResidentDetailResponse:
    detail = ResidentDetailResponse.model_validate(resident)
    detail.meters = [MeterResponse.model_validate(m) for m in resident_service.list_meters(db, resident.resident_id)]
    return detail


@router.get("/home", response_model=ResidentHomeResponse)
def get_home(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> ResidentHomeResponse:
    return resident_service.get_home_summary(db, resident)
