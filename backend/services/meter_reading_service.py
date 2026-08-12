"""The MeterVision integration point.

This is the one place in the billing system that calls into the existing,
already-working AI pipeline — as a plain in-process function call, not a
network hop. Nothing in vision/, providers/, or models/ is modified.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.admin_user import AdminUser
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.enums import ActorType, BillingPeriodStatus, MeterReadingStatus, SubmittedBy
from backend.db.models.meter import Meter
from backend.db.models.meter_reading import MeterReading
from backend.db.models.resident import Resident
from backend.services import audit_service
from models.meter_result import ReviewStatus
from providers.base import ProviderError, VisionProvider
from vision.detection import analyze_meter_image
from vision.preprocessing import validate_image_upload

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGES_STORAGE_DIR = REPO_ROOT / "backend" / "storage" / "meter_images"

_AI_STATUS_TO_READING_STATUS = {
    ReviewStatus.ACCEPTED: MeterReadingStatus.AI_ACCEPTED,
    ReviewStatus.NEEDS_REVIEW: MeterReadingStatus.NEEDS_REVIEW,
    ReviewStatus.REJECTED: MeterReadingStatus.REJECTED,
}

# A resident may only resubmit while their existing row for this billing
# period is in one of these states — once finalized, only an admin can
# reopen it. Enforced here (backend), not just by hiding a frontend button.
_RESUBMITTABLE_STATUSES = {
    MeterReadingStatus.SUBMITTED,
    MeterReadingStatus.AI_ACCEPTED,
    MeterReadingStatus.NEEDS_REVIEW,
    MeterReadingStatus.REJECTED,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_open_billing_period(db: Session, community_id: int) -> BillingPeriod:
    period = (
        db.query(BillingPeriod)
        .filter(BillingPeriod.community_id == community_id, BillingPeriod.status == BillingPeriodStatus.OPEN_FOR_READINGS)
        # Ties on reading_window_start (shouldn't happen once Phase 5's
        # lifecycle enforces one open period at a time, but stay
        # deterministic regardless) break by the most recently created row.
        .order_by(BillingPeriod.reading_window_start.desc(), BillingPeriod.billing_period_id.desc())
        .first()
    )
    if period is None:
        raise ConflictError("No billing period is currently open for meter reading submissions.")
    return period


def _get_active_meter(db: Session, resident: Resident) -> Meter:
    meter = db.query(Meter).filter(Meter.resident_id == resident.resident_id, Meter.is_active.is_(True)).first()
    if meter is None:
        raise ConflictError("No active meter is assigned to this resident. Please contact your administrator.")
    return meter


def _get_previous_reading_value(db: Session, resident: Resident) -> Decimal:
    """Most recent finalized reading for this resident, across all past
    billing periods — independent of Bill (which doesn't exist until
    Phase 5's billing engine runs). Defaults to 0 for a brand-new meter."""
    last_finalized = (
        db.query(MeterReading)
        .filter(
            MeterReading.resident_id == resident.resident_id,
            MeterReading.status.in_([MeterReadingStatus.RESIDENT_CONFIRMED, MeterReadingStatus.ADMIN_OVERRIDDEN]),
        )
        .order_by(MeterReading.created_at.desc())
        .first()
    )
    if last_finalized is not None and last_finalized.final_reading_value is not None:
        return last_finalized.final_reading_value
    return Decimal("0.000")


def _save_image(meter_reading_id: int, resident_id: int, community_id: int, image_bytes: bytes) -> str:
    directory = IMAGES_STORAGE_DIR / str(community_id) / str(resident_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{meter_reading_id}.jpg"
    path.write_bytes(image_bytes)
    return str(path)


def get_own_reading_or_404(db: Session, resident: Resident, meter_reading_id: int) -> MeterReading:
    reading = db.get(MeterReading, meter_reading_id)
    # "Not yours" is treated identically to "doesn't exist" — never reveal
    # that another resident's reading ID is valid.
    if reading is None or reading.resident_id != resident.resident_id:
        raise NotFoundError(f"Meter reading {meter_reading_id} not found.")
    return reading


def get_reading_or_404(db: Session, meter_reading_id: int) -> MeterReading:
    reading = db.get(MeterReading, meter_reading_id)
    if reading is None:
        raise NotFoundError(f"Meter reading {meter_reading_id} not found.")
    return reading


def submit_meter_reading(
    db: Session, resident: Resident, image_bytes: bytes, vision_provider: VisionProvider
) -> MeterReading:
    billing_period = _get_open_billing_period(db, resident.community_id)
    meter = _get_active_meter(db, resident)

    existing = (
        db.query(MeterReading)
        .filter(
            MeterReading.billing_period_id == billing_period.billing_period_id,
            MeterReading.resident_id == resident.resident_id,
        )
        .first()
    )
    if existing is not None and existing.status not in _RESUBMITTABLE_STATUSES:
        raise ConflictError(
            "A reading has already been accepted for this billing period. "
            "Contact your administrator if you need to resubmit."
        )

    # validate_image_upload raises ValueError on a bad file — left
    # uncaught here so the router maps it to 422, matching how app.py
    # (the existing Streamlit prototype) handles the same exception.
    validate_image_upload(image_bytes)

    # analyze_meter_image never raises on a bad *photo* (it returns a
    # conservative needs_retake result instead) — it can raise
    # ProviderError on a transport/auth failure, left uncaught here so the
    # router maps it to 502.
    result = analyze_meter_image(image_bytes, vision_provider)

    previous_reading_value = _get_previous_reading_value(db, resident)
    submitted_reading_value = Decimal(result.reading) if result.reading else None
    reading_status = _AI_STATUS_TO_READING_STATUS[result.status]

    if existing is not None:
        reading = existing
    else:
        reading = MeterReading(
            billing_period_id=billing_period.billing_period_id,
            meter_id=meter.meter_id,
            resident_id=resident.resident_id,
            image_path="",  # filled in below once we know the row's id
        )
        db.add(reading)
        db.flush()

    reading.image_path = _save_image(reading.meter_reading_id, resident.resident_id, resident.community_id, image_bytes)
    reading.previous_reading_value = previous_reading_value
    reading.submitted_reading_value = submitted_reading_value
    reading.raw_digits = result.raw_digits
    reading.unit = result.unit
    reading.ai_confidence = Decimal(str(round(result.confidence, 3)))
    reading.ai_status = result.status
    reading.ai_reason = result.reason
    reading.ai_validation_notes = result.validation_notes or None
    reading.status = reading_status
    reading.submitted_by = SubmittedBy.RESIDENT
    # A fresh AI attempt invalidates any prior admin review of the old attempt.
    reading.final_reading_value = None
    reading.resident_confirmed_at = None
    reading.reviewed_by_admin_id = None
    reading.admin_reviewed_at = None

    db.commit()
    db.refresh(reading)

    audit_service.record(
        db,
        actor_type=ActorType.RESIDENT,
        actor_id=resident.resident_id,
        action="reading.submit",
        entity_type="meter_reading",
        entity_id=reading.meter_reading_id,
        after_state={"ai_status": result.status.value, "confidence": result.confidence},
    )
    return reading


def confirm_meter_reading(db: Session, resident: Resident, meter_reading_id: int) -> MeterReading:
    reading = get_own_reading_or_404(db, resident, meter_reading_id)

    if reading.status != MeterReadingStatus.AI_ACCEPTED:
        raise ConflictError("Only an AI-accepted reading can be confirmed.")
    if reading.submitted_reading_value is None:
        raise ConflictError("This reading has no value to confirm.")

    current = reading.submitted_reading_value
    previous = reading.previous_reading_value or Decimal("0.000")

    if current == previous:
        raise ConflictError(
            "The new reading is the same as the previous reading. Please verify the meter and submit the correct reading."
        )
    if current < previous:
        raise ConflictError(
            "The new reading cannot be lower than the previous accepted reading. Please verify the reading and try again."
        )

    reading.final_reading_value = current
    reading.status = MeterReadingStatus.RESIDENT_CONFIRMED
    reading.resident_confirmed_at = _now()
    db.commit()
    db.refresh(reading)

    audit_service.record(
        db,
        actor_type=ActorType.RESIDENT,
        actor_id=resident.resident_id,
        action="reading.confirm",
        entity_type="meter_reading",
        entity_id=reading.meter_reading_id,
        after_state={"final_reading_value": str(current)},
    )
    return reading


def retake_meter_reading(db: Session, resident: Resident, meter_reading_id: int) -> MeterReading:
    """Confirms the resident may discard this attempt and re-upload. The
    actual reset happens naturally on the next submit_meter_reading call
    (which overwrites every AI-derived field on the same row) — this just
    gates eligibility so a finalized reading can't be silently reopened."""
    reading = get_own_reading_or_404(db, resident, meter_reading_id)
    if reading.status not in _RESUBMITTABLE_STATUSES:
        raise ConflictError("This reading has already been finalized and can no longer be retaken.")
    return reading


def list_own_readings(db: Session, resident: Resident) -> list[MeterReading]:
    return (
        db.query(MeterReading)
        .filter(MeterReading.resident_id == resident.resident_id)
        .order_by(MeterReading.created_at.desc())
        .all()
    )


def list_readings_admin(
    db: Session, *, billing_period_id: int | None = None, status: MeterReadingStatus | None = None, resident_id: int | None = None
) -> list[MeterReading]:
    query = db.query(MeterReading)
    if billing_period_id is not None:
        query = query.filter(MeterReading.billing_period_id == billing_period_id)
    if status is not None:
        query = query.filter(MeterReading.status == status)
    if resident_id is not None:
        query = query.filter(MeterReading.resident_id == resident_id)
    return query.order_by(MeterReading.created_at.desc()).all()


def admin_override_reading(
    db: Session, admin: AdminUser, meter_reading_id: int, final_reading_value: Decimal, reason: str
) -> MeterReading:
    reading = get_reading_or_404(db, meter_reading_id)

    before_state = {"status": reading.status.value, "final_reading_value": str(reading.final_reading_value)}

    reading.final_reading_value = final_reading_value
    reading.status = MeterReadingStatus.ADMIN_OVERRIDDEN
    reading.reviewed_by_admin_id = admin.admin_id
    reading.admin_reviewed_at = _now()
    db.commit()
    db.refresh(reading)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="reading.override",
        entity_type="meter_reading",
        entity_id=reading.meter_reading_id,
        before_state=before_state,
        after_state={"final_reading_value": str(final_reading_value), "reason": reason},
    )
    return reading


def admin_reject_reading(db: Session, admin: AdminUser, meter_reading_id: int, reason: str) -> MeterReading:
    reading = get_reading_or_404(db, meter_reading_id)

    before_state = {"status": reading.status.value}

    reading.status = MeterReadingStatus.REJECTED
    reading.reviewed_by_admin_id = admin.admin_id
    reading.admin_reviewed_at = _now()
    db.commit()
    db.refresh(reading)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="reading.reject",
        entity_type="meter_reading",
        entity_id=reading.meter_reading_id,
        before_state=before_state,
        after_state={"reason": reason},
    )
    return reading
