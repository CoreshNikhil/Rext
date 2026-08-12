"""Resident-facing billing endpoints — read-only, everything here is
computed by billing_service.py, never recalculated in the router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_current_resident, get_db
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.resident import Resident
from backend.schemas.billing import BillResponse
from backend.services import billing_service

router = APIRouter(
    prefix="/api/v1/resident/bills", tags=["resident-billing"], dependencies=[Depends(get_current_resident)]
)


@router.get("", response_model=list[BillResponse])
def list_own_bills(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> list[BillResponse]:
    bills = billing_service.list_own_bills(db, resident)
    return [BillResponse.model_validate(b) for b in bills]


@router.get("/current", response_model=BillResponse | None)
def get_current_bill(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> BillResponse | None:
    bill = billing_service.get_current_bill_for_resident(db, resident)
    return BillResponse.model_validate(bill) if bill else None


@router.get("/{bill_id}", response_model=BillResponse)
def get_own_bill(
    bill_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> BillResponse:
    try:
        bill = billing_service.get_own_bill_or_404(db, resident, bill_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillResponse.model_validate(bill)
