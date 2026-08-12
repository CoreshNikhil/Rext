"""Tests for the scheduled jobs.

Job functions open their own DB session via backend.jobs.definitions'
module-level SessionLocal (there's no request-scoped Depends(get_db)
outside an HTTP request), so tests monkeypatch that name to point at an
isolated in-memory test DB rather than the real one — the standard
pattern for testing background jobs that don't go through FastAPI's DI.

Each job's core design requirement is idempotency (safe to run twice
without duplicating side effects), so every test here explicitly runs the
job a second time and asserts nothing extra happened.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.enums import (
    BillingPeriodStatus,
    BillStatus,
    ImportJobStatus,
    ImportSourceType,
    NotificationType,
    RecipientType,
)
from backend.db.models.fine import Fine
from backend.db.models.import_job import ImportJob
from backend.db.models.notification import Notification
from backend.jobs import definitions
from backend.tests.conftest import seed_admin, seed_billing_period, seed_finalized_reading, seed_meter, seed_resident


# --- billing_cycle_kickoff ------------------------------------------------


def test_kickoff_opens_draft_period_whose_start_has_arrived(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.DRAFT)
    period.reading_window_start = date.today() - timedelta(days=1)
    db.commit()

    definitions.billing_cycle_kickoff()

    db.refresh(period)
    assert period.status == BillingPeriodStatus.OPEN_FOR_READINGS

    notifications = db.query(Notification).filter(Notification.resident_id == resident.resident_id).all()
    assert any(n.type == NotificationType.BILLING_CYCLE_OPENED for n in notifications)


def test_kickoff_does_not_open_future_period(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.DRAFT)
    period.reading_window_start = date.today() + timedelta(days=5)
    db.commit()

    definitions.billing_cycle_kickoff()

    db.refresh(period)
    assert period.status == BillingPeriodStatus.DRAFT


def test_kickoff_is_idempotent(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.DRAFT)
    period.reading_window_start = date.today() - timedelta(days=1)
    db.commit()

    definitions.billing_cycle_kickoff()
    definitions.billing_cycle_kickoff()

    notifications = (
        db.query(Notification)
        .filter(Notification.resident_id == resident.resident_id, Notification.type == NotificationType.BILLING_CYCLE_OPENED)
        .all()
    )
    # Re-running doesn't re-open an already-open period, so it shouldn't
    # send a second "cycle opened" notification either.
    assert len(notifications) == 1


def test_kickoff_auto_creates_next_draft_period_when_none_pending(jobs_db):
    db = jobs_db
    admin = seed_admin(db)

    assert db.query(BillingPeriod).filter(BillingPeriod.community_id == admin.community_id).count() == 0

    definitions.billing_cycle_kickoff()

    periods = db.query(BillingPeriod).filter(BillingPeriod.community_id == admin.community_id).all()
    assert len(periods) == 1
    assert periods[0].status == BillingPeriodStatus.DRAFT


def test_kickoff_does_not_create_duplicate_period_when_one_already_pending(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.DRAFT, period_label="existing-draft")

    definitions.billing_cycle_kickoff()

    periods = db.query(BillingPeriod).filter(BillingPeriod.community_id == admin.community_id).all()
    assert len(periods) == 1


# --- reading_window_deadline_check ------------------------------------


def test_deadline_check_closes_readings_generates_bills_and_notifies_missing(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident_with_reading = seed_resident(db, onboarded=True, house_number="D-1", mobile="9600000001")
    resident_missing = seed_resident(db, onboarded=True, house_number="D-2", mobile="9600000002")
    meter = seed_meter(db, resident_with_reading, serial="MTR-D1")

    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.OPEN_FOR_READINGS)
    period.reading_window_end = date.today() - timedelta(days=1)
    db.commit()
    seed_finalized_reading(db, resident_with_reading, meter, period)

    definitions.reading_window_deadline_check()

    db.refresh(period)
    assert period.status == BillingPeriodStatus.BILLED  # closed, then bills generated

    bills = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).all()
    assert len(bills) == 1
    assert bills[0].resident_id == resident_with_reading.resident_id

    missing_notifications = (
        db.query(Notification)
        .filter(Notification.resident_id == resident_missing.resident_id, Notification.type == NotificationType.READING_MISSING)
        .all()
    )
    assert len(missing_notifications) == 1

    admin_notifications = (
        db.query(Notification)
        .filter(Notification.recipient_type == RecipientType.ADMIN, Notification.type == NotificationType.READING_MISSING)
        .all()
    )
    assert len(admin_notifications) == 1


def test_deadline_check_is_idempotent(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.OPEN_FOR_READINGS)
    period.reading_window_end = date.today() - timedelta(days=1)
    db.commit()

    definitions.reading_window_deadline_check()
    definitions.reading_window_deadline_check()

    missing_notifications = (
        db.query(Notification)
        .filter(Notification.resident_id == resident.resident_id, Notification.type == NotificationType.READING_MISSING)
        .all()
    )
    # State-gated on OPEN_FOR_READINGS — the second run finds nothing left
    # in that state, so no duplicate notification.
    assert len(missing_notifications) == 1


# --- bill_due_date_check -----------------------------------------------


def test_bill_due_date_check_marks_overdue_and_notifies(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    meter = seed_meter(db, resident)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    from backend.services import billing_service

    billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    bill = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).first()
    bill.due_date = date.today() - timedelta(days=1)
    db.commit()

    definitions.bill_due_date_check()

    db.refresh(bill)
    assert bill.status == BillStatus.OVERDUE

    resident_notifications = (
        db.query(Notification)
        .filter(Notification.resident_id == resident.resident_id, Notification.type == NotificationType.BILL_OVERDUE)
        .all()
    )
    assert len(resident_notifications) == 1


def test_bill_due_date_check_ignores_bill_not_yet_due(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    meter = seed_meter(db, resident)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    from backend.services import billing_service

    billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    bill = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).first()
    bill.due_date = date.today() + timedelta(days=5)
    db.commit()

    definitions.bill_due_date_check()

    db.refresh(bill)
    assert bill.status == BillStatus.ISSUED


# --- fine_accrual ---------------------------------------------------------


def test_fine_accrual_creates_fine_and_updates_total(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    meter = seed_meter(db, resident)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    from backend.services import billing_service

    billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    bill = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).first()
    original_amount_due = bill.amount_due
    bill.status = BillStatus.OVERDUE
    bill.due_date = date.today() - timedelta(days=3)
    db.commit()

    definitions.fine_accrual()

    db.refresh(bill)
    assert bill.fine_amount == period.fine_per_day_overdue
    assert bill.total_amount_due == original_amount_due + period.fine_per_day_overdue
    assert bill.amount_due == original_amount_due  # original consumption calc untouched

    fines = db.query(Fine).filter(Fine.bill_id == bill.bill_id).all()
    assert len(fines) == 1


def test_fine_accrual_is_idempotent_within_the_same_day(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    meter = seed_meter(db, resident)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    from backend.services import billing_service

    billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    bill = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).first()
    bill.status = BillStatus.OVERDUE
    bill.due_date = date.today() - timedelta(days=1)
    db.commit()

    definitions.fine_accrual()
    definitions.fine_accrual()

    fines = db.query(Fine).filter(Fine.bill_id == bill.bill_id).all()
    assert len(fines) == 1  # not double-charged on rerun

    db.refresh(bill)
    assert bill.fine_amount == period.fine_per_day_overdue


# --- late_payment_reminder ------------------------------------------------


def test_late_payment_reminder_sends_once_per_day(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    meter = seed_meter(db, resident)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    from backend.services import billing_service

    billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    bill = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).first()
    bill.status = BillStatus.OVERDUE
    db.commit()

    definitions.late_payment_reminder()
    definitions.late_payment_reminder()

    reminders = (
        db.query(Notification)
        .filter(Notification.resident_id == resident.resident_id, Notification.type == NotificationType.PAYMENT_REMINDER)
        .all()
    )
    assert len(reminders) == 1


# --- import_job_cleanup ------------------------------------------------


def test_import_job_cleanup_deletes_old_file_keeps_db_row(jobs_db, tmp_path):
    db = jobs_db
    admin = seed_admin(db)

    old_file = tmp_path / "old_import.csv"
    old_file.write_text("House Number,Name,Mobile,Meter ID\n")

    job = ImportJob(
        community_id=admin.community_id,
        admin_id=admin.admin_id,
        source_type=ImportSourceType.CSV,
        original_filename="old_import.csv",
        file_path=str(old_file),
        status=ImportJobStatus.CONFIRMED,
    )
    db.add(job)
    db.commit()
    # created_at has a server_default of now() — backdate it directly so
    # the job's 90-day cutoff actually applies to this row.
    db.query(ImportJob).filter(ImportJob.import_job_id == job.import_job_id).update(
        {"created_at": datetime.now(timezone.utc) - timedelta(days=100)}
    )
    db.commit()

    assert old_file.exists()

    definitions.import_job_cleanup()

    assert not old_file.exists()
    # The DB row itself is kept — only the stored file is removed.
    assert db.get(ImportJob, job.import_job_id) is not None


def test_import_job_cleanup_ignores_recent_files(jobs_db, tmp_path):
    db = jobs_db
    admin = seed_admin(db)

    recent_file = tmp_path / "recent_import.csv"
    recent_file.write_text("House Number,Name,Mobile,Meter ID\n")

    job = ImportJob(
        community_id=admin.community_id,
        admin_id=admin.admin_id,
        source_type=ImportSourceType.CSV,
        original_filename="recent_import.csv",
        file_path=str(recent_file),
        status=ImportJobStatus.CONFIRMED,
    )
    db.add(job)
    db.commit()

    definitions.import_job_cleanup()

    assert recent_file.exists()
