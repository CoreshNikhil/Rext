"""Resident CRUD business logic — admin-only, backing routers/admin_residents.py.

Soft-delete only: a "deleted" resident is deactivated (is_active=False),
never removed from the table, since MeterReading/Bill/Payment rows must
keep a valid FK back to them.
"""

from __future__ import annotations

import secrets
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.core import security
from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.admin_user import AdminUser
from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.enums import ActorType, BillingPeriodStatus, TokenSubjectType
from backend.db.models.meter import Meter
from backend.db.models.meter_reading import MeterReading
from backend.db.models.notification import Notification
from backend.db.models.resident import Resident
from backend.schemas.resident import ResidentCreateRequest, ResidentHomeResponse, ResidentUpdateRequest
from backend.services import audit_service
from backend.services.auth_service import revoke_all_refresh_tokens
from backend.services.meter_reading_service import get_previous_reading_value


def list_residents(db: Session, *, active_only: bool = False, search: str | None = None) -> list[Resident]:
    query = db.query(Resident)
    if active_only:
        query = query.filter(Resident.is_active.is_(True))
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Resident.house_number.ilike(pattern),
                Resident.full_name.ilike(pattern),
                Resident.mobile_number.ilike(pattern),
            )
        )
    return query.order_by(Resident.house_number).all()


def get_resident(db: Session, resident_id: int) -> Resident:
    resident = db.get(Resident, resident_id)
    if resident is None:
        raise NotFoundError(f"Resident {resident_id} not found.")
    return resident


def _check_unique_house_and_mobile(
    db: Session, *, house_number: str, mobile_number: str, exclude_resident_id: int | None = None
) -> None:
    house_query = db.query(Resident).filter(Resident.house_number == house_number)
    if exclude_resident_id is not None:
        house_query = house_query.filter(Resident.resident_id != exclude_resident_id)
    if house_query.first() is not None:
        raise ConflictError(f"House number '{house_number}' is already registered.")

    mobile_query = db.query(Resident).filter(Resident.mobile_number == mobile_number)
    if exclude_resident_id is not None:
        mobile_query = mobile_query.filter(Resident.resident_id != exclude_resident_id)
    if mobile_query.first() is not None:
        raise ConflictError(f"Mobile number '{mobile_number}' is already registered.")


def _check_unique_meter_serial(db: Session, meter_serial_number: str) -> None:
    if db.query(Meter).filter(Meter.meter_serial_number == meter_serial_number).first() is not None:
        raise ConflictError(f"Meter serial number '{meter_serial_number}' is already assigned.")


def create_resident(db: Session, admin: AdminUser, payload: ResidentCreateRequest) -> Resident:
    _check_unique_house_and_mobile(db, house_number=payload.house_number, mobile_number=payload.mobile_number)
    if payload.meter_serial_number is not None:
        _check_unique_meter_serial(db, payload.meter_serial_number)

    resident = Resident(
        community_id=admin.community_id,
        house_number=payload.house_number,
        full_name=payload.full_name,
        mobile_number=payload.mobile_number,
        email=payload.email,
    )
    db.add(resident)
    db.flush()

    if payload.meter_serial_number is not None:
        db.add(Meter(resident_id=resident.resident_id, meter_serial_number=payload.meter_serial_number))

    db.commit()
    db.refresh(resident)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="resident.create",
        entity_type="resident",
        entity_id=resident.resident_id,
        after_state={"house_number": resident.house_number, "mobile_number": resident.mobile_number},
    )
    return resident


def update_resident(db: Session, admin: AdminUser, resident_id: int, payload: ResidentUpdateRequest) -> Resident:
    resident = get_resident(db, resident_id)

    before_state = {
        "full_name": resident.full_name,
        "mobile_number": resident.mobile_number,
        "email": resident.email,
        "is_active": resident.is_active,
    }

    if payload.mobile_number is not None and payload.mobile_number != resident.mobile_number:
        conflict = (
            db.query(Resident)
            .filter(Resident.mobile_number == payload.mobile_number, Resident.resident_id != resident_id)
            .first()
        )
        if conflict is not None:
            raise ConflictError(f"Mobile number '{payload.mobile_number}' is already registered.")
        resident.mobile_number = payload.mobile_number

    if payload.full_name is not None:
        resident.full_name = payload.full_name
    if payload.email is not None:
        resident.email = payload.email
    if payload.is_active is not None:
        resident.is_active = payload.is_active

    db.commit()
    db.refresh(resident)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="resident.update",
        entity_type="resident",
        entity_id=resident.resident_id,
        before_state=before_state,
        after_state={
            "full_name": resident.full_name,
            "mobile_number": resident.mobile_number,
            "email": resident.email,
            "is_active": resident.is_active,
        },
    )
    return resident


def deactivate_resident(db: Session, admin: AdminUser, resident_id: int) -> Resident:
    """Soft-delete only — never a hard DELETE, per the spec."""
    resident = get_resident(db, resident_id)
    resident.is_active = False
    db.commit()
    db.refresh(resident)

    revoke_all_refresh_tokens(db, TokenSubjectType.RESIDENT, resident_id)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="resident.deactivate",
        entity_type="resident",
        entity_id=resident.resident_id,
    )
    return resident


def reset_resident_password(db: Session, admin: AdminUser, resident_id: int) -> None:
    """Invalidates the resident's current password (replaced with an
    unguessable random value) and revokes every active session, so the
    only way back in is the OTP-based password-reset flow."""
    resident = get_resident(db, resident_id)

    resident.password_hash = security.hash_password(secrets.token_urlsafe(32))
    db.commit()

    revoke_all_refresh_tokens(db, TokenSubjectType.RESIDENT, resident_id)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="resident.reset_password",
        entity_type="resident",
        entity_id=resident.resident_id,
    )


def assign_meter(
    db: Session, admin: AdminUser, resident_id: int, meter_serial_number: str, install_date: date | None = None
) -> Meter:
    resident = get_resident(db, resident_id)
    _check_unique_meter_serial(db, meter_serial_number)

    meter = Meter(resident_id=resident.resident_id, meter_serial_number=meter_serial_number, install_date=install_date)
    db.add(meter)
    db.commit()
    db.refresh(meter)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="meter.assign",
        entity_type="meter",
        entity_id=meter.meter_id,
        after_state={"resident_id": resident_id, "meter_serial_number": meter_serial_number},
    )
    return meter


def list_meters(db: Session, resident_id: int) -> list[Meter]:
    get_resident(db, resident_id)  # raises NotFoundError if the resident doesn't exist
    return db.query(Meter).filter(Meter.resident_id == resident_id).all()


def update_own_email(db: Session, resident: Resident, email: str | None) -> Resident:
    resident.email = email
    db.commit()
    db.refresh(resident)
    return resident


def get_home_summary(db: Session, resident: Resident) -> ResidentHomeResponse:
    """One call for the resident's whole home screen: current billing
    period status, submission/payment state, and unread notification
    count — matching the spec's home-screen mockup directly."""
    period = (
        db.query(BillingPeriod)
        .filter(BillingPeriod.community_id == resident.community_id, BillingPeriod.status == BillingPeriodStatus.OPEN_FOR_READINGS)
        .order_by(BillingPeriod.reading_window_start.desc(), BillingPeriod.billing_period_id.desc())
        .first()
    )
    if period is None:
        # No period currently open — fall back to the most recent one so
        # the resident still sees their last cycle's outcome, not a blank
        # screen, between billing cycles.
        period = (
            db.query(BillingPeriod)
            .filter(BillingPeriod.community_id == resident.community_id)
            .order_by(BillingPeriod.reading_window_start.desc(), BillingPeriod.billing_period_id.desc())
            .first()
        )

    reading = None
    bill = None
    if period is not None:
        reading = (
            db.query(MeterReading)
            .filter(MeterReading.billing_period_id == period.billing_period_id, MeterReading.resident_id == resident.resident_id)
            .first()
        )
        bill = (
            db.query(Bill)
            .filter(Bill.billing_period_id == period.billing_period_id, Bill.resident_id == resident.resident_id)
            .first()
        )

    unread_count = (
        db.query(Notification)
        .filter(Notification.resident_id == resident.resident_id, Notification.is_read.is_(False))
        .count()
    )

    return ResidentHomeResponse(
        resident_id=resident.resident_id,
        house_number=resident.house_number,
        full_name=resident.full_name,
        billing_period_id=period.billing_period_id if period else None,
        period_label=period.period_label if period else None,
        gas_rate_per_unit=period.rate_per_unit if period else None,
        reading_deadline=period.reading_window_end if period else None,
        billing_period_status=period.status.value if period else None,
        reading_status=reading.status.value if reading else None,
        previous_reading_value=(
            reading.previous_reading_value if reading else (get_previous_reading_value(db, resident) if period else None)
        ),
        current_reading_value=reading.submitted_reading_value if reading else None,
        bill_id=bill.bill_id if bill else None,
        amount_due=bill.total_amount_due if bill else None,
        payment_status=bill.status.value if bill else None,
        unread_notification_count=unread_count,
    )
