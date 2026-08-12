"""Admin dashboard aggregate stats — read-only, cross-cutting queries over
residents/readings/bills. Doesn't belong to any single domain service,
matching the spec's "MONTHLY GAS BILLING" overview mockup.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.enums import BillStatus, MeterReadingStatus
from backend.db.models.meter_reading import MeterReading
from backend.db.models.resident import Resident


def get_overview(db: Session, community_id: int) -> dict:
    total_residents = db.query(Resident).filter(Resident.community_id == community_id).count()
    active_residents = (
        db.query(Resident).filter(Resident.community_id == community_id, Resident.is_active.is_(True)).count()
    )

    current_period = (
        db.query(BillingPeriod)
        .filter(BillingPeriod.community_id == community_id)
        .order_by(BillingPeriod.reading_window_start.desc(), BillingPeriod.billing_period_id.desc())
        .first()
    )

    readings_submitted = 0
    readings_pending = 0
    bills_generated = 0
    bills_paid = 0
    bills_unpaid = 0
    bills_overdue = 0
    total_billed = Decimal("0.00")
    total_collected = Decimal("0.00")

    if current_period is not None:
        readings_submitted = (
            db.query(MeterReading)
            .filter(
                MeterReading.billing_period_id == current_period.billing_period_id,
                MeterReading.status.in_([MeterReadingStatus.RESIDENT_CONFIRMED, MeterReadingStatus.ADMIN_OVERRIDDEN]),
            )
            .count()
        )
        readings_pending = max(active_residents - readings_submitted, 0)

        period_bills = db.query(Bill).filter(Bill.billing_period_id == current_period.billing_period_id).all()
        bills_generated = len(period_bills)
        bills_paid = sum(1 for b in period_bills if b.status == BillStatus.PAID)
        bills_overdue = sum(1 for b in period_bills if b.status == BillStatus.OVERDUE)
        bills_unpaid = sum(1 for b in period_bills if b.status in (BillStatus.ISSUED, BillStatus.OVERDUE))
        total_billed = sum((b.total_amount_due for b in period_bills), Decimal("0.00"))
        total_collected = sum((b.total_amount_due for b in period_bills if b.status == BillStatus.PAID), Decimal("0.00"))

    return {
        "total_residents": total_residents,
        "active_residents": active_residents,
        "current_billing_period_id": current_period.billing_period_id if current_period else None,
        "current_billing_period_label": current_period.period_label if current_period else None,
        "readings_submitted": readings_submitted,
        "readings_pending": readings_pending,
        "bills_generated": bills_generated,
        "bills_paid": bills_paid,
        "bills_unpaid": bills_unpaid,
        "bills_overdue": bills_overdue,
        "total_billed": total_billed,
        "total_collected": total_collected,
        "outstanding": total_billed - total_collected,
    }


def get_collections_by_period(db: Session, community_id: int) -> list[dict]:
    periods = (
        db.query(BillingPeriod)
        .filter(BillingPeriod.community_id == community_id)
        .order_by(BillingPeriod.reading_window_start.desc())
        .all()
    )

    results = []
    for period in periods:
        bills = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).all()
        total_billed = sum((b.total_amount_due for b in bills), Decimal("0.00"))
        total_collected = sum((b.total_amount_due for b in bills if b.status == BillStatus.PAID), Decimal("0.00"))
        rate = (total_collected / total_billed * 100).quantize(Decimal("0.01")) if total_billed > 0 else Decimal("0.00")
        results.append(
            {
                "billing_period_id": period.billing_period_id,
                "period_label": period.period_label,
                "total_billed": total_billed,
                "total_collected": total_collected,
                "collection_rate_percent": rate,
            }
        )
    return results
