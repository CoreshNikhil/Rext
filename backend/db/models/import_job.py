from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, enum_column
from backend.db.models.enums import ImportJobStatus, ImportRowAction, ImportRowValidationStatus, ImportSourceType
from backend.db.models.mixins import TimestampMixin
from backend.db.types import UTCDateTime


class ImportJob(Base, TimestampMixin):
    __tablename__ = "import_jobs"

    import_job_id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.community_id"), nullable=False)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.admin_id"), nullable=False)

    source_type: Mapped[ImportSourceType] = mapped_column(enum_column(ImportSourceType), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # canonical_field -> source_column_name, confirmed by the admin during
    # the mapping step. See vision.detection-style decoupling in §6 of the plan.
    column_mapping: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[ImportJobStatus] = mapped_column(
        enum_column(ImportJobStatus), default=ImportJobStatus.UPLOADED, server_default=ImportJobStatus.UPLOADED.value
    )

    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ImportRow(Base, TimestampMixin):
    __tablename__ = "import_rows"

    import_row_id: Mapped[int] = mapped_column(primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.import_job_id"), nullable=False)

    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    mapped_data: Mapped[dict | None] = mapped_column(JSON)

    validation_status: Mapped[ImportRowValidationStatus] = mapped_column(
        enum_column(ImportRowValidationStatus), nullable=False
    )
    validation_errors: Mapped[list | None] = mapped_column(JSON)
    action: Mapped[ImportRowAction | None] = mapped_column(enum_column(ImportRowAction))

    resident_id: Mapped[int | None] = mapped_column(ForeignKey("residents.resident_id"))
