"""Create+query round-trip coverage for all 16 ORM models, plus targeted
checks that the constraints the design relies on actually hold: FK
enforcement (SQLite doesn't enforce by default), the unique constraints
that back several "one row per X" invariants, and that MeterReading.ai_status
correctly round-trips through the reused models.meter_result.ReviewStatus
enum rather than a redefinition of it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models.admin_user import AdminUser
from backend.db.models.audit_log import AuditLog
from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.community import Community
from backend.db.models.enums import (
    ActorType,
    BillingPeriodStatus,
    BillStatus,
    ConfigValueType,
    ImportRowValidationStatus,
    ImportSourceType,
    MeterReadingStatus,
    NotificationType,
    OtpPurpose,
    PaymentStatus,
    RecipientType,
    SubmittedBy,
    TokenSubjectType,
)
from backend.db.models.fine import Fine
from backend.db.models.import_job import ImportJob, ImportRow
from backend.db.models.meter import Meter
from backend.db.models.meter_reading import MeterReading
from backend.db.models.notification import Notification
from backend.db.models.otp_request import OtpRequest
from backend.db.models.payment import Payment
from backend.db.models.refresh_token import RefreshToken
from backend.db.models.resident import Resident
from backend.db.models.system_configuration import SystemConfiguration
from models.meter_result import ReviewStatus

NOW = datetime.now(timezone.utc)


def _build_full_graph(db):
    """Builds one connected row per table, matching real FK relationships,
    and returns them keyed by table name for assertions."""
    community = Community(name="Sample Community", timezone="Asia/Kolkata")
    db.add(community)
    db.flush()

    admin = AdminUser(
        community_id=community.community_id,
        email="admin@example.com",
        full_name="Test Admin",
        password_hash="bcrypt$stub",
    )
    db.add(admin)
    db.flush()

    resident = Resident(
        community_id=community.community_id,
        house_number="A-204",
        full_name="Test Resident",
        mobile_number="9876543210",
        password_hash="bcrypt$stub",
    )
    db.add(resident)
    db.flush()

    meter = Meter(resident_id=resident.resident_id, meter_serial_number="16710009")
    db.add(meter)
    db.flush()

    billing_period = BillingPeriod(
        community_id=community.community_id,
        period_label="2026-08",
        reading_window_start=date(2026, 8, 1),
        reading_window_end=date(2026, 8, 15),
        payment_due_date=date(2026, 8, 25),
        rate_per_unit=Decimal("50.00"),
        fine_per_day_overdue=Decimal("10.00"),
        status=BillingPeriodStatus.OPEN_FOR_READINGS,
    )
    db.add(billing_period)
    db.flush()

    meter_reading = MeterReading(
        billing_period_id=billing_period.billing_period_id,
        meter_id=meter.meter_id,
        resident_id=resident.resident_id,
        image_path="backend/storage/meter_images/1/1/1.jpg",
        previous_reading_value=Decimal("100.000"),
        submitted_reading_value=Decimal("115.197"),
        raw_digits="00115197",
        unit="m3",
        ai_confidence=Decimal("0.950"),
        ai_status=ReviewStatus.ACCEPTED,
        status=MeterReadingStatus.RESIDENT_CONFIRMED,
        submitted_by=SubmittedBy.RESIDENT,
        final_reading_value=Decimal("115.197"),
        resident_confirmed_at=NOW,
    )
    db.add(meter_reading)
    db.flush()

    bill = Bill(
        billing_period_id=billing_period.billing_period_id,
        resident_id=resident.resident_id,
        meter_reading_id=meter_reading.meter_reading_id,
        previous_reading_value=Decimal("100.000"),
        current_reading_value=Decimal("115.197"),
        consumption_units=Decimal("15.197"),
        rate_per_unit=Decimal("50.00"),
        amount_due=Decimal("759.85"),
        total_amount_due=Decimal("759.85"),
        due_date=date(2026, 8, 25),
        status=BillStatus.ISSUED,
    )
    db.add(bill)
    db.flush()

    payment = Payment(
        bill_id=bill.bill_id,
        resident_id=resident.resident_id,
        amount=Decimal("759.85"),
        provider_name="mock",
        status=PaymentStatus.SUCCESS,
    )
    db.add(payment)

    fine = Fine(
        bill_id=bill.bill_id, amount=Decimal("10.00"), reason="Overdue by 1 day", accrual_date=date(2026, 8, 26)
    )
    db.add(fine)

    notification = Notification(
        recipient_type=RecipientType.RESIDENT,
        resident_id=resident.resident_id,
        type=NotificationType.BILL_GENERATED,
        title="Your bill is ready",
        message="Your gas bill for 2026-08 has been generated.",
        sent_at=NOW,
    )
    db.add(notification)

    import_job = ImportJob(
        community_id=community.community_id,
        admin_id=admin.admin_id,
        source_type=ImportSourceType.EXCEL,
        original_filename="residents.xlsx",
        file_path="backend/storage/imports/1/original.xlsx",
        column_mapping={"House Number": "house_number", "Mobile": "mobile_number"},
    )
    db.add(import_job)
    db.flush()

    import_row = ImportRow(
        import_job_id=import_job.import_job_id,
        row_number=1,
        raw_data={"House Number": "A-204", "Mobile": "9876543210"},
        mapped_data={"house_number": "A-204", "mobile_number": "9876543210"},
        validation_status=ImportRowValidationStatus.VALID,
        resident_id=resident.resident_id,
    )
    db.add(import_row)

    audit_log = AuditLog(
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="reading.override",
        entity_type="meter_reading",
        entity_id=meter_reading.meter_reading_id,
        before_state={"status": "needs_review"},
        after_state={"status": "admin_overridden"},
    )
    db.add(audit_log)

    system_configuration = SystemConfiguration(
        key="default_rate_per_unit", value="50.00", value_type=ConfigValueType.FLOAT
    )
    db.add(system_configuration)

    otp_request = OtpRequest(
        purpose=OtpPurpose.SIGNUP,
        resident_id=resident.resident_id,
        mobile_number="9876543210",
        otp_hash="bcrypt$stub",
        expires_at=NOW,
    )
    db.add(otp_request)

    refresh_token = RefreshToken(
        subject_type=TokenSubjectType.RESIDENT,
        subject_id=resident.resident_id,
        token_hash="sha256$stub",
        expires_at=NOW,
    )
    db.add(refresh_token)

    db.commit()

    return {
        "community": community,
        "admin": admin,
        "resident": resident,
        "meter": meter,
        "billing_period": billing_period,
        "meter_reading": meter_reading,
        "bill": bill,
        "payment": payment,
        "fine": fine,
        "notification": notification,
        "import_job": import_job,
        "import_row": import_row,
        "audit_log": audit_log,
        "system_configuration": system_configuration,
        "otp_request": otp_request,
        "refresh_token": refresh_token,
    }


def test_full_graph_round_trips_every_table(db_session):
    created = _build_full_graph(db_session)
    db_session.expire_all()  # force a fresh read from the DB, not the identity map

    community = db_session.get(Community, created["community"].community_id)
    assert community is not None and community.name == "Sample Community"

    admin = db_session.get(AdminUser, created["admin"].admin_id)
    assert admin is not None and admin.email == "admin@example.com"
    assert admin.is_active is True

    resident = db_session.get(Resident, created["resident"].resident_id)
    assert resident is not None
    assert resident.house_number == "A-204"
    # house_number is a login identifier, never the PK — resident_id is.
    assert resident.resident_id != resident.house_number

    meter = db_session.get(Meter, created["meter"].meter_id)
    assert meter is not None and meter.meter_serial_number == "16710009"

    billing_period = db_session.get(BillingPeriod, created["billing_period"].billing_period_id)
    assert billing_period is not None and billing_period.rate_per_unit == Decimal("50.00")

    meter_reading = db_session.get(MeterReading, created["meter_reading"].meter_reading_id)
    assert meter_reading is not None
    # The whole point of reusing ReviewStatus: it must round-trip as the
    # exact same enum type MeterVision itself produces.
    assert meter_reading.ai_status == ReviewStatus.ACCEPTED
    assert isinstance(meter_reading.ai_status, ReviewStatus)
    assert meter_reading.status == MeterReadingStatus.RESIDENT_CONFIRMED
    assert meter_reading.final_reading_value == Decimal("115.197")

    bill = db_session.get(Bill, created["bill"].bill_id)
    assert bill is not None
    assert bill.consumption_units == Decimal("15.197")
    assert bill.total_amount_due == Decimal("759.85")

    payment = db_session.get(Payment, created["payment"].payment_id)
    assert payment is not None and payment.status == PaymentStatus.SUCCESS

    fine = db_session.get(Fine, created["fine"].fine_id)
    assert fine is not None and fine.amount == Decimal("10.00")

    notification = db_session.get(Notification, created["notification"].notification_id)
    assert notification is not None and notification.is_read is False

    import_job = db_session.get(ImportJob, created["import_job"].import_job_id)
    assert import_job is not None and import_job.column_mapping["House Number"] == "house_number"

    import_row = db_session.get(ImportRow, created["import_row"].import_row_id)
    assert import_row is not None and import_row.validation_status == ImportRowValidationStatus.VALID

    audit_log = db_session.get(AuditLog, created["audit_log"].audit_log_id)
    assert audit_log is not None and audit_log.action == "reading.override"

    system_configuration = db_session.get(SystemConfiguration, "default_rate_per_unit")
    assert system_configuration is not None and system_configuration.value == "50.00"

    otp_request = db_session.get(OtpRequest, created["otp_request"].otp_id)
    assert otp_request is not None and otp_request.is_used is False

    refresh_token = db_session.get(RefreshToken, created["refresh_token"].refresh_token_id)
    assert refresh_token is not None and refresh_token.revoked_at is None


def test_duplicate_house_number_violates_unique_constraint(db_session):
    community = Community(name="C1")
    db_session.add(community)
    db_session.flush()

    db_session.add(
        Resident(
            community_id=community.community_id,
            house_number="A-204",
            full_name="First",
            mobile_number="9876543210",
        )
    )
    db_session.commit()

    db_session.add(
        Resident(
            community_id=community.community_id,
            house_number="A-204",
            full_name="Second",
            mobile_number="9999999999",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_foreign_key_enforcement_rejects_dangling_reference(db_session):
    # No Resident with resident_id=9999 exists — SQLite ignores FKs unless
    # PRAGMA foreign_keys=ON is active per-connection, which is exactly
    # what backend/db/session.py's connect-event listener (mirrored in the
    # db_session fixture) is responsible for.
    db_session.add(Meter(resident_id=9999, meter_serial_number="DOES-NOT-EXIST"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_meter_reading_per_billing_period_and_resident(db_session):
    created = _build_full_graph(db_session)

    duplicate = MeterReading(
        billing_period_id=created["billing_period"].billing_period_id,
        meter_id=created["meter"].meter_id,
        resident_id=created["resident"].resident_id,
        image_path="backend/storage/meter_images/1/1/2.jpg",
        ai_status=ReviewStatus.NEEDS_REVIEW,
        status=MeterReadingStatus.SUBMITTED,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_fine_accrual_idempotency_constraint(db_session):
    created = _build_full_graph(db_session)

    duplicate_fine = Fine(
        bill_id=created["bill"].bill_id,
        amount=Decimal("10.00"),
        reason="Overdue by 1 day (duplicate job run)",
        accrual_date=created["fine"].accrual_date,
    )
    db_session.add(duplicate_fine)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
