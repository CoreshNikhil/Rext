"""Python enums backing the billing system's status/type columns.

`models.meter_result.ReviewStatus` (MeterVision's AI assessment enum) is
deliberately NOT redefined here — `MeterReading.ai_status` imports and
reuses it directly, so there is one canonical source of truth for those
three values.
"""

from __future__ import annotations

import enum


class AdminRole(str, enum.Enum):
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class BillingPeriodStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN_FOR_READINGS = "open_for_readings"
    READINGS_CLOSED = "readings_closed"
    BILLED = "billed"
    CLOSED = "closed"


class MeterReadingStatus(str, enum.Enum):
    """The resident-submission workflow state — distinct from ai_status
    (models.meter_result.ReviewStatus), which is the AI's raw assessment."""

    SUBMITTED = "submitted"
    AI_ACCEPTED = "ai_accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    RESIDENT_CONFIRMED = "resident_confirmed"
    ADMIN_OVERRIDDEN = "admin_overridden"


class SubmittedBy(str, enum.Enum):
    RESIDENT = "resident"
    ADMIN = "admin"


class BillStatus(str, enum.Enum):
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    WAIVED = "waived"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    INITIATED = "initiated"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecipientType(str, enum.Enum):
    RESIDENT = "resident"
    ADMIN = "admin"


class NotificationType(str, enum.Enum):
    READING_REMINDER = "reading_reminder"
    READING_NEEDS_REVIEW = "reading_needs_review"
    READING_MISSING = "reading_missing"
    BILL_GENERATED = "bill_generated"
    BILL_OVERDUE = "bill_overdue"
    PAYMENT_REMINDER = "payment_reminder"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_FAILED = "payment_failed"
    FINE_APPLIED = "fine_applied"
    IMPORT_COMPLETED = "import_completed"
    BILLING_CYCLE_OPENED = "billing_cycle_opened"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    SMS_MOCK = "sms_mock"
    EMAIL_MOCK = "email_mock"


class ImportSourceType(str, enum.Enum):
    EXCEL = "excel"
    CSV = "csv"
    GOOGLE_SHEETS = "google_sheets"  # reserved, unimplemented in v1


class ImportJobStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    MAPPED = "mapped"
    VALIDATED = "validated"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportRowValidationStatus(str, enum.Enum):
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


class ImportRowAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"


class ActorType(str, enum.Enum):
    RESIDENT = "resident"
    ADMIN = "admin"
    SYSTEM = "system"


class ConfigValueType(str, enum.Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"


class OtpPurpose(str, enum.Enum):
    SIGNUP = "signup"
    LOGIN = "login"
    PASSWORD_RESET = "password_reset"


class TokenSubjectType(str, enum.Enum):
    RESIDENT = "resident"
    ADMIN = "admin"
