"""Scheduled job definitions.

Each function is a complete unit of work: it opens its own DB session
(there's no request-scoped Depends(get_db) outside an HTTP request) and is
safe to run more than once. APScheduler here runs in-process — a second
worker process would double-fire every job — so every job is designed to
be a no-op on a repeat run rather than relying on the scheduler itself to
guarantee single execution.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.community import Community
from backend.db.models.enums import (
    ActorType,
    BillingPeriodStatus,
    BillStatus,
    ImportJobStatus,
    MeterReadingStatus,
    NotificationType,
)
from backend.db.models.fine import Fine
from backend.db.models.import_job import ImportJob
from backend.db.models.meter_reading import MeterReading
from backend.db.models.resident import Resident
from backend.db.models.system_configuration import SystemConfiguration
from backend.db.session import SessionLocal
from backend.services import audit_service, billing_service, notification_service

logger = logging.getLogger("backend.jobs")


def _get_config_value(db, key: str, default: str) -> str:
    config = db.get(SystemConfiguration, key)
    return config.value if config is not None else default


def _active_residents(db, community_id: int) -> list[Resident]:
    return db.query(Resident).filter(Resident.community_id == community_id, Resident.is_active.is_(True)).all()


# --- billing_cycle_kickoff: daily 00:15 -----------------------------------


def billing_cycle_kickoff() -> None:
    db = SessionLocal()
    try:
        today = date.today()

        draft_periods_to_open = (
            db.query(BillingPeriod)
            .filter(BillingPeriod.status == BillingPeriodStatus.DRAFT, BillingPeriod.reading_window_start <= today)
            .all()
        )
        for period in draft_periods_to_open:
            billing_service.system_open_billing_period(db, period.billing_period_id)

            for resident in _active_residents(db, period.community_id):
                notification_service.notify_resident(
                    db,
                    resident.resident_id,
                    NotificationType.BILLING_CYCLE_OPENED,
                    title=f"Meter reading period {period.period_label} has started",
                    message=(
                        f"Your gas meter reading period for {period.period_label} has started. "
                        f"Please submit your reading before {period.reading_window_end}. "
                        f"Gas rate: Rs {period.rate_per_unit}/m3."
                    ),
                    related_entity_type="billing_period",
                    related_entity_id=period.billing_period_id,
                )

        # Not just for communities whose period just opened — a community
        # with zero periods at all (first-ever use) needs one queued too.
        for community in db.query(Community).all():
            _auto_create_next_draft_period_if_needed(db, community.community_id)
    finally:
        db.close()


def _auto_create_next_draft_period_if_needed(db, community_id: int) -> BillingPeriod | None:
    has_pending = (
        db.query(BillingPeriod)
        .filter(
            BillingPeriod.community_id == community_id,
            BillingPeriod.status.in_([BillingPeriodStatus.DRAFT, BillingPeriodStatus.OPEN_FOR_READINGS]),
        )
        .first()
    )
    if has_pending is not None:
        return None

    today = date.today()
    period_label = today.strftime("%Y-%m")
    if (
        db.query(BillingPeriod)
        .filter(BillingPeriod.community_id == community_id, BillingPeriod.period_label == period_label)
        .first()
        is not None
    ):
        return None

    reading_days = int(_get_config_value(db, "reading_window_duration_days", "15"))
    payment_days = int(_get_config_value(db, "payment_window_duration_days", "10"))
    rate = Decimal(_get_config_value(db, "default_rate_per_unit", "50.00"))
    fine = Decimal(_get_config_value(db, "default_fine_per_day_overdue", "10.00"))

    reading_window_end = today + timedelta(days=reading_days)
    period = BillingPeriod(
        community_id=community_id,
        period_label=period_label,
        reading_window_start=today,
        reading_window_end=reading_window_end,
        payment_due_date=reading_window_end + timedelta(days=payment_days),
        rate_per_unit=rate,
        fine_per_day_overdue=fine,
        status=BillingPeriodStatus.DRAFT,
    )
    db.add(period)
    db.commit()
    db.refresh(period)

    audit_service.record(
        db,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="billing_period.auto_create",
        entity_type="billing_period",
        entity_id=period.billing_period_id,
        after_state={"period_label": period_label},
    )
    return period


# --- reading_window_deadline_check: daily 00:30 -----------------------------


def reading_window_deadline_check() -> None:
    db = SessionLocal()
    try:
        today = date.today()
        periods = (
            db.query(BillingPeriod)
            .filter(BillingPeriod.status == BillingPeriodStatus.OPEN_FOR_READINGS, BillingPeriod.reading_window_end < today)
            .all()
        )
        for period in periods:
            billing_service.system_close_readings(db, period.billing_period_id)

            finalized_resident_ids = {
                reading.resident_id
                for reading in db.query(MeterReading)
                .filter(
                    MeterReading.billing_period_id == period.billing_period_id,
                    MeterReading.status.in_([MeterReadingStatus.RESIDENT_CONFIRMED, MeterReadingStatus.ADMIN_OVERRIDDEN]),
                )
                .all()
            }

            for resident in _active_residents(db, period.community_id):
                if resident.resident_id in finalized_resident_ids:
                    continue

                notification_service.notify_resident(
                    db,
                    resident.resident_id,
                    NotificationType.READING_MISSING,
                    title=f"No meter reading submitted for {period.period_label}",
                    message=(
                        f"You haven't submitted a meter reading for {period.period_label} and the reading "
                        "window has closed. Please contact your administrator."
                    ),
                    related_entity_type="billing_period",
                    related_entity_id=period.billing_period_id,
                )
                notification_service.notify_admin(
                    db,
                    NotificationType.READING_MISSING,
                    title=f"Missing reading: {resident.house_number} ({period.period_label})",
                    message=f"Resident {resident.house_number} did not submit a meter reading for {period.period_label}.",
                    related_entity_type="resident",
                    related_entity_id=resident.resident_id,
                )

            # Bill generation is itself idempotent/incremental — safe to
            # call unconditionally here.
            billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    finally:
        db.close()


# --- bill_due_date_check: daily 01:00 ---------------------------------------


def bill_due_date_check() -> None:
    db = SessionLocal()
    try:
        today = date.today()
        overdue_bills = db.query(Bill).filter(Bill.status == BillStatus.ISSUED, Bill.due_date < today).all()
        for bill in overdue_bills:
            bill.status = BillStatus.OVERDUE
            db.commit()

            audit_service.record(
                db,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                action="bill.auto_overdue",
                entity_type="bill",
                entity_id=bill.bill_id,
                after_state={"status": "overdue"},
            )

            notification_service.notify_resident(
                db,
                bill.resident_id,
                NotificationType.BILL_OVERDUE,
                title="Your gas bill is overdue",
                message=(
                    f"Your gas bill of Rs {bill.total_amount_due} was due on {bill.due_date} and is now overdue. "
                    "Please pay as soon as possible to avoid additional fines."
                ),
                related_entity_type="bill",
                related_entity_id=bill.bill_id,
            )
            notification_service.notify_admin(
                db,
                NotificationType.BILL_OVERDUE,
                title=f"Bill overdue: bill_id={bill.bill_id}",
                message=f"Bill {bill.bill_id} (Rs {bill.total_amount_due}) became overdue on {today}.",
                related_entity_type="bill",
                related_entity_id=bill.bill_id,
            )
    finally:
        db.close()


# --- fine_accrual: daily 01:15 ----------------------------------------------


def fine_accrual() -> None:
    db = SessionLocal()
    try:
        today = date.today()
        overdue_bills = db.query(Bill).filter(Bill.status == BillStatus.OVERDUE).all()

        for bill in overdue_bills:
            # UNIQUE(bill_id, accrual_date) backs this at the DB level too
            # — this check just avoids the extra insert/rollback churn.
            already_accrued_today = (
                db.query(Fine).filter(Fine.bill_id == bill.bill_id, Fine.accrual_date == today).first()
            )
            if already_accrued_today is not None:
                continue

            period = db.get(BillingPeriod, bill.billing_period_id)
            fine_amount = period.fine_per_day_overdue
            days_overdue = (today - bill.due_date).days

            fine = Fine(
                bill_id=bill.bill_id,
                amount=fine_amount,
                reason=f"Overdue by {days_overdue} day(s)",
                accrual_date=today,
            )
            db.add(fine)

            # The original gas consumption calculation (amount_due) is
            # never touched — fines accumulate in a separate column.
            bill.fine_amount = (bill.fine_amount or Decimal("0.00")) + fine_amount
            bill.total_amount_due = bill.amount_due + bill.fine_amount
            db.commit()

            audit_service.record(
                db,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                action="bill.fine_accrued",
                entity_type="bill",
                entity_id=bill.bill_id,
                after_state={"fine_amount": str(fine_amount), "total_amount_due": str(bill.total_amount_due)},
            )

            notification_service.notify_resident(
                db,
                bill.resident_id,
                NotificationType.FINE_APPLIED,
                title="A late fine has been added to your bill",
                message=f"A late fine of Rs {fine_amount} has been added to your bill. New total: Rs {bill.total_amount_due}.",
                related_entity_type="bill",
                related_entity_id=bill.bill_id,
            )
    finally:
        db.close()


# --- late_payment_reminder: daily 09:00 -------------------------------------


def late_payment_reminder() -> None:
    db = SessionLocal()
    try:
        overdue_bills = db.query(Bill).filter(Bill.status == BillStatus.OVERDUE).all()
        for bill in overdue_bills:
            if notification_service.resident_notification_already_sent_today(
                db, bill.resident_id, NotificationType.PAYMENT_REMINDER, bill.bill_id
            ):
                continue

            notification_service.notify_resident(
                db,
                bill.resident_id,
                NotificationType.PAYMENT_REMINDER,
                title="Reminder: your gas bill is overdue",
                message=(
                    f"Your gas bill of Rs {bill.total_amount_due} is overdue. "
                    "Please pay as soon as possible to avoid further fines."
                ),
                related_entity_type="bill",
                related_entity_id=bill.bill_id,
            )
    finally:
        db.close()


# --- import_job_cleanup: weekly (housekeeping) ------------------------------

_TERMINAL_IMPORT_STATUSES = (ImportJobStatus.CONFIRMED, ImportJobStatus.FAILED, ImportJobStatus.CANCELLED)


def import_job_cleanup() -> None:
    """Deletes stored import files older than 90 days for terminal-status
    jobs. Keeps the DB rows (history/audit trail), only removes the disk
    copy of the original spreadsheet."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        old_jobs = (
            db.query(ImportJob)
            .filter(ImportJob.status.in_(_TERMINAL_IMPORT_STATUSES), ImportJob.created_at < cutoff)
            .all()
        )

        deleted = 0
        for job in old_jobs:
            path = Path(job.file_path)
            if path.exists():
                path.unlink()
                deleted += 1

        logger.info("import_job_cleanup: removed %d stored file(s) (DB rows kept)", deleted)
    finally:
        db.close()
