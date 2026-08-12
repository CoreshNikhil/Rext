"""Billing engine: BillingPeriod lifecycle transitions, Bill generation,
and admin bill actions (waive/cancel).

Consumption and amount are always computed here, server-side, from
finalized MeterReading rows — never accepted from a client, never
recalculated in a router or (later) the Flutter app.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.admin_user import AdminUser
from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.enums import ActorType, BillingPeriodStatus, BillStatus, MeterReadingStatus
from backend.db.models.meter_reading import MeterReading
from backend.db.models.resident import Resident
from backend.schemas.billing import BillingPeriodCreateRequest, BillingPeriodUpdateRequest
from backend.services import audit_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- BillingPeriod CRUD --------------------------------------------------


def create_billing_period(db: Session, admin: AdminUser, payload: BillingPeriodCreateRequest) -> BillingPeriod:
    existing = (
        db.query(BillingPeriod)
        .filter(BillingPeriod.community_id == admin.community_id, BillingPeriod.period_label == payload.period_label)
        .first()
    )
    if existing is not None:
        raise ConflictError(f"A billing period labeled '{payload.period_label}' already exists.")

    period = BillingPeriod(
        community_id=admin.community_id,
        period_label=payload.period_label,
        reading_window_start=payload.reading_window_start,
        reading_window_end=payload.reading_window_end,
        payment_due_date=payload.payment_due_date,
        rate_per_unit=payload.rate_per_unit,
        fine_per_day_overdue=payload.fine_per_day_overdue,
        status=BillingPeriodStatus.DRAFT,
    )
    db.add(period)
    db.commit()
    db.refresh(period)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="billing_period.create",
        entity_type="billing_period",
        entity_id=period.billing_period_id,
        after_state={"period_label": payload.period_label, "rate_per_unit": str(payload.rate_per_unit)},
    )
    return period


def get_billing_period(db: Session, billing_period_id: int) -> BillingPeriod:
    period = db.get(BillingPeriod, billing_period_id)
    if period is None:
        raise NotFoundError(f"Billing period {billing_period_id} not found.")
    return period


def list_billing_periods(db: Session) -> list[BillingPeriod]:
    return db.query(BillingPeriod).order_by(BillingPeriod.reading_window_start.desc()).all()


def update_billing_period(
    db: Session, admin: AdminUser, billing_period_id: int, payload: BillingPeriodUpdateRequest
) -> BillingPeriod:
    period = get_billing_period(db, billing_period_id)
    if period.status != BillingPeriodStatus.DRAFT:
        raise ConflictError("Only a DRAFT billing period can be edited.")

    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    before_state = {key: str(getattr(period, key)) for key in updates}

    for key, value in updates.items():
        setattr(period, key, value)

    db.commit()
    db.refresh(period)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="billing_period.update",
        entity_type="billing_period",
        entity_id=period.billing_period_id,
        before_state=before_state,
        after_state={key: str(value) for key, value in updates.items()},
    )
    return period


# --- Lifecycle transitions ------------------------------------------------


def _transition(
    db: Session,
    admin: AdminUser,
    period: BillingPeriod,
    from_status: BillingPeriodStatus,
    to_status: BillingPeriodStatus,
    action: str,
) -> BillingPeriod:
    if period.status != from_status:
        raise ConflictError(
            f"Billing period must be {from_status.value} to {action.replace('_', ' ')} "
            f"(currently {period.status.value})."
        )
    period.status = to_status
    if to_status == BillingPeriodStatus.CLOSED:
        period.closed_at = _now()
    db.commit()
    db.refresh(period)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action=f"billing_period.{action}",
        entity_type="billing_period",
        entity_id=period.billing_period_id,
        before_state={"status": from_status.value},
        after_state={"status": to_status.value},
    )
    return period


def open_billing_period(db: Session, admin: AdminUser, billing_period_id: int) -> BillingPeriod:
    period = get_billing_period(db, billing_period_id)
    return _transition(db, admin, period, BillingPeriodStatus.DRAFT, BillingPeriodStatus.OPEN_FOR_READINGS, "open")


def close_readings(db: Session, admin: AdminUser, billing_period_id: int) -> BillingPeriod:
    period = get_billing_period(db, billing_period_id)
    return _transition(
        db, admin, period, BillingPeriodStatus.OPEN_FOR_READINGS, BillingPeriodStatus.READINGS_CLOSED, "close_readings"
    )


def close_billing_period(db: Session, admin: AdminUser, billing_period_id: int) -> BillingPeriod:
    period = get_billing_period(db, billing_period_id)
    return _transition(db, admin, period, BillingPeriodStatus.BILLED, BillingPeriodStatus.CLOSED, "close")


# --- Bill generation -------------------------------------------------------


def generate_bills_for_period(db: Session, admin: AdminUser, billing_period_id: int) -> dict:
    """Idempotent/incremental: only bills residents with a finalized
    reading and no existing bill yet in this period. Safe to call more
    than once (e.g. after a late admin override adds a new finalized
    reading) — already-billed residents are simply skipped, never
    re-billed or double-charged."""
    period = get_billing_period(db, billing_period_id)
    if period.status not in (BillingPeriodStatus.READINGS_CLOSED, BillingPeriodStatus.BILLED):
        raise ConflictError("Readings must be closed before bills can be generated.")

    finalized_readings = (
        db.query(MeterReading)
        .filter(
            MeterReading.billing_period_id == billing_period_id,
            MeterReading.status.in_([MeterReadingStatus.RESIDENT_CONFIRMED, MeterReadingStatus.ADMIN_OVERRIDDEN]),
        )
        .all()
    )

    already_billed_resident_ids = {
        bill.resident_id for bill in db.query(Bill).filter(Bill.billing_period_id == billing_period_id).all()
    }

    created = 0
    for reading in finalized_readings:
        if reading.resident_id in already_billed_resident_ids:
            continue
        if reading.final_reading_value is None or reading.previous_reading_value is None:
            continue

        # Server-computed, never trusted from a client: consumption is the
        # difference between the finalized reading and its snapshot of the
        # previous one; amount is consumption * the period's rate,
        # snapshotted onto the bill so a later admin rate change never
        # retroactively alters an already-issued bill.
        consumption = reading.final_reading_value - reading.previous_reading_value
        amount_due = (consumption * period.rate_per_unit).quantize(Decimal("0.01"))

        bill = Bill(
            billing_period_id=period.billing_period_id,
            resident_id=reading.resident_id,
            meter_reading_id=reading.meter_reading_id,
            previous_reading_value=reading.previous_reading_value,
            current_reading_value=reading.final_reading_value,
            consumption_units=consumption,
            rate_per_unit=period.rate_per_unit,
            amount_due=amount_due,
            fine_amount=Decimal("0.00"),
            total_amount_due=amount_due,
            due_date=period.payment_due_date,
            status=BillStatus.ISSUED,
            generated_at=_now(),
        )
        db.add(bill)
        already_billed_resident_ids.add(reading.resident_id)
        created += 1

    # BILLED means "generation has run at least once", not "everyone is
    # billed" — residents without a finalized reading are simply skipped
    # and re-checked on the next run.
    if period.status == BillingPeriodStatus.READINGS_CLOSED:
        period.status = BillingPeriodStatus.BILLED

    db.commit()

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="billing_period.generate_bills",
        entity_type="billing_period",
        entity_id=period.billing_period_id,
        after_state={"bills_created": created},
    )
    return {"bills_created": created, "total_finalized_readings": len(finalized_readings)}


# --- Bills ---------------------------------------------------------------


def get_bill(db: Session, bill_id: int) -> Bill:
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise NotFoundError(f"Bill {bill_id} not found.")
    return bill


def get_own_bill_or_404(db: Session, resident: Resident, bill_id: int) -> Bill:
    bill = db.get(Bill, bill_id)
    if bill is None or bill.resident_id != resident.resident_id:
        raise NotFoundError(f"Bill {bill_id} not found.")
    return bill


def list_own_bills(db: Session, resident: Resident) -> list[Bill]:
    return db.query(Bill).filter(Bill.resident_id == resident.resident_id).order_by(Bill.created_at.desc()).all()


def get_current_bill_for_resident(db: Session, resident: Resident) -> Bill | None:
    return (
        db.query(Bill)
        .filter(Bill.resident_id == resident.resident_id)
        .order_by(Bill.created_at.desc())
        .first()
    )


def list_bills_admin(
    db: Session,
    *,
    billing_period_id: int | None = None,
    status: BillStatus | None = None,
    resident_id: int | None = None,
) -> list[Bill]:
    query = db.query(Bill)
    if billing_period_id is not None:
        query = query.filter(Bill.billing_period_id == billing_period_id)
    if status is not None:
        query = query.filter(Bill.status == status)
    if resident_id is not None:
        query = query.filter(Bill.resident_id == resident_id)
    return query.order_by(Bill.created_at.desc()).all()


def waive_bill(db: Session, admin: AdminUser, bill_id: int, reason: str) -> Bill:
    bill = get_bill(db, bill_id)
    if bill.status not in (BillStatus.ISSUED, BillStatus.OVERDUE):
        raise ConflictError(f"Only an issued or overdue bill can be waived (currently {bill.status.value}).")

    bill.status = BillStatus.WAIVED
    db.commit()
    db.refresh(bill)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="bill.waive",
        entity_type="bill",
        entity_id=bill.bill_id,
        after_state={"reason": reason},
    )
    return bill


def cancel_bill(db: Session, admin: AdminUser, bill_id: int, reason: str) -> Bill:
    bill = get_bill(db, bill_id)
    if bill.status not in (BillStatus.ISSUED, BillStatus.OVERDUE):
        raise ConflictError(f"Only an issued or overdue bill can be cancelled (currently {bill.status.value}).")

    bill.status = BillStatus.CANCELLED
    db.commit()
    db.refresh(bill)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="bill.cancel",
        entity_type="bill",
        entity_id=bill.bill_id,
        after_state={"reason": reason},
    )
    return bill
