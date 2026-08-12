"""Admin billing: BillingPeriod CRUD + lifecycle transitions, and Bill
list/detail/waive/cancel. Admin-scoped only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_db
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import BillStatus
from backend.schemas.billing import (
    BillActionRequest,
    BillingPeriodCreateRequest,
    BillingPeriodResponse,
    BillingPeriodUpdateRequest,
    BillResponse,
    GenerateBillsResponse,
)
from backend.services import billing_service

billing_period_router = APIRouter(
    prefix="/api/v1/admin/billing-periods", tags=["admin-billing-periods"], dependencies=[Depends(get_current_admin)]
)
bill_router = APIRouter(prefix="/api/v1/admin/bills", tags=["admin-bills"], dependencies=[Depends(get_current_admin)])


@billing_period_router.post("", response_model=BillingPeriodResponse, status_code=201)
def create_billing_period(
    payload: BillingPeriodCreateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BillingPeriodResponse:
    try:
        period = billing_service.create_billing_period(db, admin, payload)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillingPeriodResponse.model_validate(period)


@billing_period_router.get("", response_model=list[BillingPeriodResponse])
def list_billing_periods(db: Session = Depends(get_db)) -> list[BillingPeriodResponse]:
    periods = billing_service.list_billing_periods(db)
    return [BillingPeriodResponse.model_validate(p) for p in periods]


@billing_period_router.get("/{billing_period_id}", response_model=BillingPeriodResponse)
def get_billing_period(billing_period_id: int, db: Session = Depends(get_db)) -> BillingPeriodResponse:
    try:
        period = billing_service.get_billing_period(db, billing_period_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillingPeriodResponse.model_validate(period)


@billing_period_router.patch("/{billing_period_id}", response_model=BillingPeriodResponse)
def update_billing_period(
    billing_period_id: int,
    payload: BillingPeriodUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BillingPeriodResponse:
    try:
        period = billing_service.update_billing_period(db, admin, billing_period_id, payload)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillingPeriodResponse.model_validate(period)


@billing_period_router.post("/{billing_period_id}/open", response_model=BillingPeriodResponse)
def open_billing_period(
    billing_period_id: int, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
) -> BillingPeriodResponse:
    try:
        period = billing_service.open_billing_period(db, admin, billing_period_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillingPeriodResponse.model_validate(period)


@billing_period_router.post("/{billing_period_id}/close-readings", response_model=BillingPeriodResponse)
def close_readings(
    billing_period_id: int, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
) -> BillingPeriodResponse:
    try:
        period = billing_service.close_readings(db, admin, billing_period_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillingPeriodResponse.model_validate(period)


@billing_period_router.post("/{billing_period_id}/generate-bills", response_model=GenerateBillsResponse)
def generate_bills(
    billing_period_id: int, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
) -> GenerateBillsResponse:
    try:
        result = billing_service.generate_bills_for_period(db, admin, billing_period_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return GenerateBillsResponse(**result)


@billing_period_router.post("/{billing_period_id}/close", response_model=BillingPeriodResponse)
def close_billing_period(
    billing_period_id: int, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
) -> BillingPeriodResponse:
    try:
        period = billing_service.close_billing_period(db, admin, billing_period_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillingPeriodResponse.model_validate(period)


@bill_router.get("", response_model=list[BillResponse])
def list_bills(
    billing_period_id: int | None = None,
    status: BillStatus | None = None,
    resident_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[BillResponse]:
    bills = billing_service.list_bills_admin(db, billing_period_id=billing_period_id, status=status, resident_id=resident_id)
    return [BillResponse.model_validate(b) for b in bills]


@bill_router.get("/{bill_id}", response_model=BillResponse)
def get_bill(bill_id: int, db: Session = Depends(get_db)) -> BillResponse:
    try:
        bill = billing_service.get_bill(db, bill_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillResponse.model_validate(bill)


@bill_router.post("/{bill_id}/waive", response_model=BillResponse)
def waive_bill(
    bill_id: int,
    payload: BillActionRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BillResponse:
    try:
        bill = billing_service.waive_bill(db, admin, bill_id, payload.reason)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillResponse.model_validate(bill)


@bill_router.post("/{bill_id}/cancel", response_model=BillResponse)
def cancel_bill(
    bill_id: int,
    payload: BillActionRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BillResponse:
    try:
        bill = billing_service.cancel_bill(db, admin, bill_id, payload.reason)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return BillResponse.model_validate(bill)
