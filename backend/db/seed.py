"""Idempotent local-dev seed script: one Community + default
SystemConfiguration rows. Safe to run more than once.

Run with: .venv/bin/python3 backend/db/seed.py
"""

from __future__ import annotations

from backend.core.config import settings
from backend.db import models  # noqa: F401 - registers every table on Base.metadata
from backend.db.base import Base
from backend.db.models.community import Community
from backend.db.models.enums import ConfigValueType
from backend.db.models.system_configuration import SystemConfiguration
from backend.db.session import SessionLocal, engine

DEFAULT_CONFIG = [
    ("default_rate_per_unit", "50.00", ConfigValueType.FLOAT, "Default gas rate (currency/m3) for new billing periods"),
    (
        "default_fine_per_day_overdue",
        "10.00",
        ConfigValueType.FLOAT,
        "Default daily late-payment fine for new billing periods",
    ),
    ("otp_expiry_minutes", str(settings.OTP_EXPIRY_MINUTES), ConfigValueType.INT, "Minutes before an OTP expires"),
    ("otp_max_attempts", str(settings.OTP_MAX_ATTEMPTS), ConfigValueType.INT, "Max verification attempts per OTP"),
    ("mobile_number_regex", r"^[6-9]\d{9}$", ConfigValueType.STRING, "Validation pattern for resident mobile numbers"),
    ("house_number_regex", r"^[A-Za-z0-9\-/]{1,20}$", ConfigValueType.STRING, "Validation pattern for house numbers"),
    (
        "reading_window_duration_days",
        "15",
        ConfigValueType.INT,
        "Days a billing period stays open for reading submissions, used when auto-creating the next DRAFT period",
    ),
    (
        "payment_window_duration_days",
        "10",
        ConfigValueType.INT,
        "Days after the reading window ends before payment is due, used when auto-creating the next DRAFT period",
    ),
]


def seed() -> None:
    # Safety net only — Alembic (`alembic upgrade head`) is the source of
    # truth for schema creation; this is a no-op once migrations have run.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        community = db.query(Community).first()
        if community is None:
            community = Community(name="Sample Community", timezone="Asia/Kolkata")
            db.add(community)
            db.flush()
            print(f"Created Community(community_id={community.community_id}, name={community.name!r})")
        else:
            print(f"Community already exists (community_id={community.community_id}, name={community.name!r})")

        for key, value, value_type, description in DEFAULT_CONFIG:
            existing = db.get(SystemConfiguration, key)
            if existing is None:
                db.add(SystemConfiguration(key=key, value=value, value_type=value_type, description=description))
                print(f"Seeded SystemConfiguration[{key!r}] = {value!r}")
            else:
                print(f"SystemConfiguration[{key!r}] already exists, skipping")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
