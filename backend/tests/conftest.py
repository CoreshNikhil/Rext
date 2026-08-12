"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from datetime import date, timedelta
from decimal import Decimal

from backend.core import deps, security
from backend.core.rate_limit import limiter
from backend.db import models  # noqa: F401 - registers every table on Base.metadata
from backend.db.base import Base
from backend.db.models.admin_user import AdminUser
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.community import Community
from backend.db.models.enums import BillingPeriodStatus, ConfigValueType, MeterReadingStatus, SubmittedBy
from backend.db.models.meter import Meter
from backend.db.models.meter_reading import MeterReading
from backend.db.models.resident import Resident
from backend.db.models.system_configuration import SystemConfiguration
from models.meter_result import ReviewStatus
from providers.base import VisionProvider


def _new_test_engine():
    # In-memory SQLite + StaticPool: one connection shared across the whole
    # test (plain in-memory SQLite is per-connection and would otherwise
    # lose all tables between statements).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _new_test_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client_and_session():
    """A TestClient wired against the real app, with get_db overridden to
    use an isolated in-memory DB, plus a raw session for test setup/
    assertions against that same DB."""
    from fastapi.testclient import TestClient

    from backend.main import app

    engine = _new_test_engine()
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    client = TestClient(app)

    # slowapi's default in-memory storage is a module-level singleton keyed
    # by client IP, and Starlette's TestClient reports the same fake IP for
    # every request. Without a reset, rate-limit counters would accumulate
    # across every test in the run (all sharing one process) instead of
    # resetting per test — reset here so each test starts with a clean quota.
    limiter.reset()

    setup_session = test_session_factory()
    try:
        yield client, setup_session
    finally:
        setup_session.close()
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture()
def jobs_db(monkeypatch):
    """Scheduled jobs open their own DB session via backend.jobs.definitions'
    module-level SessionLocal (there's no request-scoped Depends(get_db)
    outside an HTTP request), so this monkeypatches that name to point at an
    isolated in-memory test DB — the standard pattern for testing background
    jobs that don't go through FastAPI's DI."""
    from backend.jobs import definitions

    engine = _new_test_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(definitions, "SessionLocal", session_factory)

    setup_session = session_factory()
    try:
        yield setup_session
    finally:
        setup_session.close()
        engine.dispose()


def seed_resident(
    db, *, onboarded: bool = False, house_number: str = "A-204", mobile: str = "9876543210"
) -> Resident:
    community = db.query(Community).first()
    if community is None:
        community = Community(name="Test Community")
        db.add(community)
        db.flush()

    resident = Resident(
        community_id=community.community_id,
        house_number=house_number,
        full_name="Test Resident",
        mobile_number=mobile,
        password_hash=security.hash_password("OldPass123!") if onboarded else None,
    )
    db.add(resident)
    db.commit()
    db.refresh(resident)
    return resident


def seed_admin(db, *, email: str = "admin@example.com", password: str = "AdminPass123!") -> AdminUser:
    community = db.query(Community).first()
    if community is None:
        community = Community(name="Test Community")
        db.add(community)
        db.flush()

    admin = AdminUser(
        community_id=community.community_id,
        email=email,
        full_name="Test Admin",
        password_hash=security.hash_password(password),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def seed_meter(db, resident: Resident, *, serial: str = "MTR-TEST-001") -> Meter:
    meter = Meter(resident_id=resident.resident_id, meter_serial_number=serial)
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def close_billing_period(db, period: BillingPeriod) -> None:
    period.status = BillingPeriodStatus.READINGS_CLOSED
    db.commit()


def seed_billing_period(
    db, community_id: int, *, status: BillingPeriodStatus = BillingPeriodStatus.OPEN_FOR_READINGS, period_label: str = "2026-08"
) -> BillingPeriod:
    period = BillingPeriod(
        community_id=community_id,
        period_label=period_label,
        reading_window_start=date.today() - timedelta(days=1),
        reading_window_end=date.today() + timedelta(days=14),
        payment_due_date=date.today() + timedelta(days=21),
        rate_per_unit=Decimal("50.00"),
        fine_per_day_overdue=Decimal("10.00"),
        status=status,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


def seed_finalized_reading(
    db,
    resident: Resident,
    meter: Meter,
    billing_period: BillingPeriod,
    *,
    previous: Decimal = Decimal("100.000"),
    final: Decimal = Decimal("115.197"),
    admin_overridden: bool = False,
) -> MeterReading:
    """A reading already in a finalized (billable) state, bypassing the
    real AI call — for tests that only care about downstream billing
    behavior, not the extraction pipeline itself."""
    reading = MeterReading(
        billing_period_id=billing_period.billing_period_id,
        meter_id=meter.meter_id,
        resident_id=resident.resident_id,
        image_path="backend/storage/meter_images/test/test.jpg",
        previous_reading_value=previous,
        submitted_reading_value=final,
        raw_digits=str(final).replace(".", ""),
        unit="m3",
        ai_confidence=Decimal("0.950"),
        ai_status=ReviewStatus.ACCEPTED,
        status=MeterReadingStatus.ADMIN_OVERRIDDEN if admin_overridden else MeterReadingStatus.RESIDENT_CONFIRMED,
        submitted_by=SubmittedBy.RESIDENT,
        final_reading_value=final,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


class FakeVisionProvider(VisionProvider):
    """Deterministic test double for VisionProvider — avoids real network
    calls/cost for tests that don't specifically need to prove the live
    Gemini integration works (that's covered separately by a dedicated
    real-API test)."""

    def __init__(self, response: dict):
        self.response = response
        self.call_count = 0

    def extract_reading(self, request) -> dict:
        self.call_count += 1
        return self.response


def accepted_vision_response(
    *, raw_digits: str = "00115197", reading: str = "00115.197", confidence: float = 0.95, unit: str = "m3"
) -> dict:
    return {
        "meter_detected": True,
        "display_detected": True,
        "raw_digits": raw_digits,
        "reading": reading,
        "unit": unit,
        "serial_number": None,
        "confidence": confidence,
        "image_quality": "acceptable",
        "needs_retake": False,
        "reason": "",
    }


def needs_review_vision_response(reason: str = "Glare obscures several digits.") -> dict:
    return {
        "meter_detected": True,
        "display_detected": True,
        "raw_digits": None,
        "reading": None,
        "unit": None,
        "serial_number": None,
        "confidence": 0.3,
        "image_quality": "poor",
        "needs_retake": True,
        "reason": reason,
    }


def seed_system_config(db) -> None:
    """Populates the same default keys backend/db/seed.py seeds in the
    real dev DB — the isolated test DB starts empty, since the seed
    script only ever runs against the real one."""
    defaults = [
        ("default_rate_per_unit", "50.00", ConfigValueType.FLOAT),
        ("default_fine_per_day_overdue", "10.00", ConfigValueType.FLOAT),
        ("otp_expiry_minutes", "5", ConfigValueType.INT),
        ("otp_max_attempts", "5", ConfigValueType.INT),
        ("mobile_number_regex", r"^[6-9]\d{9}$", ConfigValueType.STRING),
        ("house_number_regex", r"^[A-Za-z0-9\-/]{1,20}$", ConfigValueType.STRING),
        ("reading_window_duration_days", "15", ConfigValueType.INT),
        ("payment_window_duration_days", "10", ConfigValueType.INT),
    ]
    for key, value, value_type in defaults:
        if db.get(SystemConfiguration, key) is None:
            db.add(SystemConfiguration(key=key, value=value, value_type=value_type))
    db.commit()
