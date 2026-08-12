"""Aggregates every ORM model so Base.metadata (and Alembic autogenerate)
sees the full schema. Import this module — not individual model files —
whenever you need Base.metadata to be complete."""

from backend.db.models.admin_user import AdminUser
from backend.db.models.audit_log import AuditLog
from backend.db.models.bill import Bill
from backend.db.models.billing_period import BillingPeriod
from backend.db.models.community import Community
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

__all__ = [
    "AdminUser",
    "AuditLog",
    "Bill",
    "BillingPeriod",
    "Community",
    "Fine",
    "ImportJob",
    "ImportRow",
    "Meter",
    "MeterReading",
    "Notification",
    "OtpRequest",
    "Payment",
    "RefreshToken",
    "Resident",
    "SystemConfiguration",
]
