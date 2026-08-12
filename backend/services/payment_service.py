"""Payment business logic: initiate, confirm (mock gateway callback),
admin mark-offline. Bill -> PAID wiring happens here, nowhere else.

Payment.amount is always copied from Bill.total_amount_due server-side —
never accepted from a client request body, matching the same "never
client-trusted" rule applied to consumption/amount in billing_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.admin_user import AdminUser
from backend.db.models.bill import Bill
from backend.db.models.enums import ActorType, BillStatus, PaymentStatus
from backend.db.models.payment import Payment
from backend.db.models.resident import Resident
from backend.providers.payment.base import PaymentProvider
from backend.services import audit_service
from backend.services.billing_service import get_bill, get_own_bill_or_404

PAYABLE_STATUSES = (BillStatus.ISSUED, BillStatus.OVERDUE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mark_bill_paid(db: Session, bill: Bill) -> None:
    bill.status = BillStatus.PAID
    bill.paid_at = _now()


def initiate_payment(db: Session, resident: Resident, bill_id: int, payment_provider: PaymentProvider) -> Payment:
    bill = get_own_bill_or_404(db, resident, bill_id)
    if bill.status not in PAYABLE_STATUSES:
        raise ConflictError(f"This bill cannot be paid (status: {bill.status.value}).")

    provider_reference_id = payment_provider.initiate(bill.total_amount_due, bill.bill_id)

    payment = Payment(
        bill_id=bill.bill_id,
        resident_id=resident.resident_id,
        amount=bill.total_amount_due,
        provider_name="mock",
        provider_reference_id=provider_reference_id,
        status=PaymentStatus.INITIATED,
        initiated_at=_now(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    audit_service.record(
        db,
        actor_type=ActorType.RESIDENT,
        actor_id=resident.resident_id,
        action="payment.initiate",
        entity_type="payment",
        entity_id=payment.payment_id,
        after_state={"bill_id": bill.bill_id, "amount": str(payment.amount)},
    )
    return payment


def get_own_payment_or_404(db: Session, resident: Resident, payment_id: int) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.resident_id != resident.resident_id:
        raise NotFoundError(f"Payment {payment_id} not found.")
    return payment


def get_payment(db: Session, payment_id: int) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError(f"Payment {payment_id} not found.")
    return payment


def confirm_payment(
    db: Session, resident: Resident, payment_id: int, payment_provider: PaymentProvider, *, simulate_success: bool
) -> Payment:
    payment = get_own_payment_or_404(db, resident, payment_id)
    if payment.status != PaymentStatus.INITIATED:
        raise ConflictError(f"Only an initiated payment can be confirmed (currently {payment.status.value}).")

    success = payment_provider.confirm(payment.provider_reference_id, simulate_success=simulate_success)
    payment.completed_at = _now()

    if success:
        payment.status = PaymentStatus.SUCCESS
        bill = db.get(Bill, payment.bill_id)
        _mark_bill_paid(db, bill)
    else:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Payment was not completed by the provider."

    db.commit()
    db.refresh(payment)

    audit_service.record(
        db,
        actor_type=ActorType.RESIDENT,
        actor_id=resident.resident_id,
        action="payment.confirm",
        entity_type="payment",
        entity_id=payment.payment_id,
        after_state={"status": payment.status.value},
    )
    return payment


def list_own_payments(db: Session, resident: Resident) -> list[Payment]:
    return db.query(Payment).filter(Payment.resident_id == resident.resident_id).order_by(Payment.created_at.desc()).all()


def list_payments_admin(
    db: Session, *, bill_id: int | None = None, status: PaymentStatus | None = None, resident_id: int | None = None
) -> list[Payment]:
    query = db.query(Payment)
    if bill_id is not None:
        query = query.filter(Payment.bill_id == bill_id)
    if status is not None:
        query = query.filter(Payment.status == status)
    if resident_id is not None:
        query = query.filter(Payment.resident_id == resident_id)
    return query.order_by(Payment.created_at.desc()).all()


def mark_bill_paid_offline(db: Session, admin: AdminUser, bill_id: int, reference_note: str) -> Payment:
    bill = get_bill(db, bill_id)
    if bill.status not in PAYABLE_STATUSES:
        raise ConflictError(f"This bill cannot be marked paid (status: {bill.status.value}).")

    payment = Payment(
        bill_id=bill.bill_id,
        resident_id=bill.resident_id,
        amount=bill.total_amount_due,
        provider_name="offline",
        provider_reference_id=reference_note,
        status=PaymentStatus.SUCCESS,
        initiated_at=_now(),
        completed_at=_now(),
    )
    db.add(payment)
    _mark_bill_paid(db, bill)
    db.commit()
    db.refresh(payment)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="payment.mark_offline",
        entity_type="bill",
        entity_id=bill.bill_id,
        after_state={"amount": str(payment.amount), "reference_note": reference_note},
    )
    return payment
