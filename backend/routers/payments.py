"""Payments: resident initiate/confirm/history, admin list/detail/mark-
offline, and a public webhook stub reserved for a future real gateway.

Three routers because the paths don't share one clean prefix
(/resident/bills/{id}/payments, /resident/payments, /payments/{id}/mock-
confirm, /payments/webhook) even though the first three share resident
auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_current_resident, get_db, get_payment_provider
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import PaymentStatus
from backend.db.models.resident import Resident
from backend.providers.payment.base import PaymentProvider
from backend.schemas.payment import MarkOfflineRequest, MockConfirmRequest, PaymentResponse
from backend.services import payment_service

resident_router = APIRouter(
    prefix="/api/v1", tags=["resident-payments"], dependencies=[Depends(get_current_resident)]
)
admin_router = APIRouter(prefix="/api/v1/admin/payments", tags=["admin-payments"], dependencies=[Depends(get_current_admin)])
public_router = APIRouter(prefix="/api/v1/payments", tags=["payments-webhook"])


@resident_router.post("/resident/bills/{bill_id}/payments", response_model=PaymentResponse, status_code=201)
def initiate_payment(
    bill_id: int,
    resident: Resident = Depends(get_current_resident),
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
) -> PaymentResponse:
    try:
        payment = payment_service.initiate_payment(db, resident, bill_id, payment_provider)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return PaymentResponse.model_validate(payment)


@resident_router.post("/payments/{payment_id}/mock-confirm", response_model=PaymentResponse)
def mock_confirm_payment(
    payment_id: int,
    payload: MockConfirmRequest,
    resident: Resident = Depends(get_current_resident),
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
) -> PaymentResponse:
    try:
        payment = payment_service.confirm_payment(
            db, resident, payment_id, payment_provider, simulate_success=payload.simulate_success
        )
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return PaymentResponse.model_validate(payment)


@resident_router.get("/resident/payments", response_model=list[PaymentResponse])
def list_own_payments(resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)) -> list[PaymentResponse]:
    payments = payment_service.list_own_payments(db, resident)
    return [PaymentResponse.model_validate(p) for p in payments]


@resident_router.get("/resident/payments/{payment_id}", response_model=PaymentResponse)
def get_own_payment(
    payment_id: int, resident: Resident = Depends(get_current_resident), db: Session = Depends(get_db)
) -> PaymentResponse:
    try:
        payment = payment_service.get_own_payment_or_404(db, resident, payment_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return PaymentResponse.model_validate(payment)


@admin_router.get("", response_model=list[PaymentResponse])
def list_payments_admin(
    bill_id: int | None = None,
    status: PaymentStatus | None = None,
    resident_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[PaymentResponse]:
    payments = payment_service.list_payments_admin(db, bill_id=bill_id, status=status, resident_id=resident_id)
    return [PaymentResponse.model_validate(p) for p in payments]


@admin_router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment_admin(payment_id: int, db: Session = Depends(get_db)) -> PaymentResponse:
    try:
        payment = payment_service.get_payment(db, payment_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return PaymentResponse.model_validate(payment)


@admin_router.post("/mark-offline/{bill_id}", response_model=PaymentResponse)
def mark_bill_paid_offline(
    bill_id: int,
    payload: MarkOfflineRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    try:
        payment = payment_service.mark_bill_paid_offline(db, admin, bill_id, payload.reference_note)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return PaymentResponse.model_validate(payment)


@public_router.post("/webhook", status_code=501)
def payment_webhook() -> dict:
    """Reserved contract for a future real payment gateway's webhook
    callback. No real provider is configured yet, so this deliberately
    does nothing but acknowledge the shape exists — implementing
    signature verification now would be security theater with no real
    secret to check against."""
    return {
        "detail": "No real payment gateway is configured yet. This endpoint is a reserved contract for future use."
    }
