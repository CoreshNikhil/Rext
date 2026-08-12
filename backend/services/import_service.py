"""Spreadsheet import pipeline: upload -> column mapping -> validation ->
preview -> confirm (upsert) -> history.

Decoupled from Excel/CSV specifics via the SourceAdapter interface —
everything downstream of `SourceAdapter.parse()` (mapping, the canonical
field schema, validation rules, confirm/upsert) is adapter-agnostic. A
future Google Sheets adapter only needs to implement `parse()`.
"""

from __future__ import annotations

import io
import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import (
    ActorType,
    ImportJobStatus,
    ImportRowAction,
    ImportRowValidationStatus,
    ImportSourceType,
)
from backend.db.models.import_job import ImportJob, ImportRow
from backend.db.models.meter import Meter
from backend.db.models.resident import Resident
from backend.db.models.system_configuration import SystemConfiguration
from backend.services import audit_service

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORTS_STORAGE_DIR = REPO_ROOT / "backend" / "storage" / "imports"

# The canonical model every source (Excel, CSV, and later Google Sheets)
# gets mapped into. Nothing downstream of this ever needs to know what the
# original spreadsheet's column names were.
CANONICAL_FIELDS = ["house_number", "full_name", "mobile_number", "meter_serial_number", "email", "install_date"]
REQUIRED_FIELDS = ["house_number", "full_name", "mobile_number", "meter_serial_number"]

COLUMN_ALIASES: dict[str, list[str]] = {
    "house_number": ["house number", "house no", "house", "flat no", "flat number", "unit", "unit number"],
    "full_name": ["name", "resident name", "resident", "full name"],
    "mobile_number": ["mobile", "mobile number", "phone", "contact", "phone number"],
    "meter_serial_number": ["meter id", "meter", "gas meter", "meter serial", "meter number", "meter serial number"],
    "email": ["email", "email address"],
    "install_date": ["install date", "installation date", "meter install date"],
}


class SourceAdapter(ABC):
    @abstractmethod
    def parse(self, file_bytes: bytes) -> list[dict]:
        raise NotImplementedError


class ExcelSourceAdapter(SourceAdapter):
    def parse(self, file_bytes: bytes) -> list[dict]:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
        return _dataframe_to_rows(df)


class CsvSourceAdapter(SourceAdapter):
    def parse(self, file_bytes: bytes) -> list[dict]:
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
        return _dataframe_to_rows(df)


def _dataframe_to_rows(df: pd.DataFrame) -> list[dict]:
    # plain `df.where(pd.notnull(df), None)` silently leaves NaN in place
    # on pandas 3.x for object/string-dtype columns — astype(object) first
    # is required for the replacement to actually take effect.
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def get_source_adapter(source_type: ImportSourceType) -> SourceAdapter:
    if source_type == ImportSourceType.EXCEL:
        return ExcelSourceAdapter()
    if source_type == ImportSourceType.CSV:
        return CsvSourceAdapter()
    raise NotImplementedError(f"No source adapter implemented for '{source_type.value}' yet.")


def suggest_column_mapping(source_columns: list[str]) -> dict[str, str | None]:
    """canonical_field -> best-guess source_column_name, or None if no
    alias matched. The admin confirms/overrides this, it's never final."""
    normalized = {col: str(col).strip().lower() for col in source_columns}
    mapping: dict[str, str | None] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        match = next((col for col, norm in normalized.items() if norm in aliases), None)
        mapping[canonical] = match
    return mapping


def _apply_mapping(raw_row: dict, column_mapping: dict[str, str | None]) -> dict[str, str | None]:
    mapped: dict[str, str | None] = {}
    for canonical_field, source_column in column_mapping.items():
        if not source_column:
            mapped[canonical_field] = None
            continue
        value = raw_row.get(source_column)
        mapped[canonical_field] = str(value).strip() if value not in (None, "") else None
    return mapped


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _get_config_value(db: Session, key: str, default: str) -> str:
    config = db.get(SystemConfiguration, key)
    return config.value if config is not None else default


# --- Upload / job lifecycle ------------------------------------------------


def create_import_job(
    db: Session, admin: AdminUser, source_type: ImportSourceType, filename: str, file_bytes: bytes
) -> ImportJob:
    job = ImportJob(
        community_id=admin.community_id,
        admin_id=admin.admin_id,
        source_type=source_type,
        original_filename=filename,
        file_path="",  # filled in below once we know the job's id
        status=ImportJobStatus.UPLOADED,
    )
    db.add(job)
    db.flush()

    job_dir = IMPORTS_STORAGE_DIR / str(job.import_job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    extension = "xlsx" if source_type == ImportSourceType.EXCEL else "csv"
    file_path = job_dir / f"original.{extension}"
    file_path.write_bytes(file_bytes)
    job.file_path = str(file_path)

    db.commit()
    db.refresh(job)
    return job


def get_import_job(db: Session, import_job_id: int) -> ImportJob:
    job = db.get(ImportJob, import_job_id)
    if job is None:
        raise NotFoundError(f"Import job {import_job_id} not found.")
    return job


def list_import_jobs(db: Session) -> list[ImportJob]:
    return db.query(ImportJob).order_by(ImportJob.created_at.desc()).all()


def get_columns_and_suggestion(db: Session, import_job_id: int) -> tuple[list[str], dict[str, str | None]]:
    job = get_import_job(db, import_job_id)
    adapter = get_source_adapter(job.source_type)
    rows = adapter.parse(Path(job.file_path).read_bytes())
    columns = list(rows[0].keys()) if rows else []
    return columns, suggest_column_mapping(columns)


def confirm_mapping(db: Session, import_job_id: int, mapping: dict[str, str | None]) -> ImportJob:
    job = get_import_job(db, import_job_id)

    missing_required = [field for field in REQUIRED_FIELDS if not mapping.get(field)]
    if missing_required:
        raise ConflictError(f"Mapping is missing required field(s): {', '.join(missing_required)}.")

    job.column_mapping = mapping
    job.status = ImportJobStatus.MAPPED
    db.commit()
    db.refresh(job)
    return job


# --- Validation --------------------------------------------------------


def validate_import(db: Session, import_job_id: int) -> ImportJob:
    job = get_import_job(db, import_job_id)
    if not job.column_mapping:
        raise ConflictError("Column mapping must be confirmed before validation.")

    # Re-validating (e.g. after the admin fixes the source file and
    # re-confirms mapping) replaces the previous row-level results.
    db.query(ImportRow).filter(ImportRow.import_job_id == import_job_id).delete()

    adapter = get_source_adapter(job.source_type)
    raw_rows = adapter.parse(Path(job.file_path).read_bytes())

    mobile_pattern = re.compile(_get_config_value(db, "mobile_number_regex", r"^[6-9]\d{9}$"))
    house_pattern = re.compile(_get_config_value(db, "house_number_regex", r"^[A-Za-z0-9\-/]{1,20}$"))

    seen_house_numbers: set[str] = set()
    seen_mobile_numbers: set[str] = set()
    seen_meter_serials: set[str] = set()

    rows_to_add: list[ImportRow] = []
    valid_count = 0
    error_count = 0

    for row_number, raw_row in enumerate(raw_rows, start=1):
        mapped = _apply_mapping(raw_row, job.column_mapping)

        if all(v in (None, "") for v in mapped.values()):
            rows_to_add.append(
                ImportRow(
                    import_job_id=job.import_job_id,
                    row_number=row_number,
                    raw_data=raw_row,
                    mapped_data=mapped,
                    validation_status=ImportRowValidationStatus.ERROR,
                    validation_errors=["Row is empty or malformed."],
                    action=ImportRowAction.SKIP,
                )
            )
            error_count += 1
            continue

        errors: list[str] = []
        for field in REQUIRED_FIELDS:
            if not mapped.get(field):
                errors.append(f"Missing required value for '{field}'.")

        house_number = mapped.get("house_number") or ""
        mobile_number = mapped.get("mobile_number") or ""
        meter_serial = mapped.get("meter_serial_number") or ""

        if house_number and not house_pattern.match(house_number):
            errors.append(f"'{house_number}' is not a valid house number format.")
        if mobile_number and not mobile_pattern.match(mobile_number):
            errors.append(f"'{mobile_number}' is not a valid mobile number format.")

        if house_number:
            if house_number in seen_house_numbers:
                errors.append(f"Duplicate house number '{house_number}' within this file.")
            seen_house_numbers.add(house_number)
        if mobile_number:
            if mobile_number in seen_mobile_numbers:
                errors.append(f"Duplicate mobile number '{mobile_number}' within this file.")
            seen_mobile_numbers.add(mobile_number)
        if meter_serial:
            if meter_serial in seen_meter_serials:
                errors.append(f"Duplicate meter serial number '{meter_serial}' within this file.")
            seen_meter_serials.add(meter_serial)

        action = ImportRowAction.CREATE
        status = ImportRowValidationStatus.VALID
        existing_resident = None

        if not errors:
            existing_resident = (
                db.query(Resident).filter(Resident.house_number == house_number).first() if house_number else None
            )
            if existing_resident is not None:
                action = ImportRowAction.UPDATE
                status = ImportRowValidationStatus.WARNING

            if mobile_number:
                mobile_owner = db.query(Resident).filter(Resident.mobile_number == mobile_number).first()
                if mobile_owner is not None and (
                    existing_resident is None or mobile_owner.resident_id != existing_resident.resident_id
                ):
                    errors.append(f"Mobile number '{mobile_number}' is already registered to a different house.")

            if meter_serial:
                meter_owner = db.query(Meter).filter(Meter.meter_serial_number == meter_serial).first()
                if meter_owner is not None and (
                    existing_resident is None or meter_owner.resident_id != existing_resident.resident_id
                ):
                    errors.append(f"Meter serial number '{meter_serial}' is already assigned elsewhere.")

        if errors:
            status = ImportRowValidationStatus.ERROR
            action = ImportRowAction.SKIP
            error_count += 1
        else:
            valid_count += 1

        rows_to_add.append(
            ImportRow(
                import_job_id=job.import_job_id,
                row_number=row_number,
                raw_data=raw_row,
                mapped_data=mapped,
                validation_status=status,
                validation_errors=errors or None,
                action=action,
                resident_id=existing_resident.resident_id if existing_resident else None,
            )
        )

    db.add_all(rows_to_add)
    job.total_rows = len(raw_rows)
    job.valid_rows = valid_count
    job.error_rows = error_count
    job.status = ImportJobStatus.VALIDATED
    db.commit()
    db.refresh(job)
    return job


def get_import_rows(
    db: Session, import_job_id: int, *, status: ImportRowValidationStatus | None = None, limit: int = 100, offset: int = 0
) -> list[ImportRow]:
    get_import_job(db, import_job_id)  # 404 if missing
    query = db.query(ImportRow).filter(ImportRow.import_job_id == import_job_id)
    if status is not None:
        query = query.filter(ImportRow.validation_status == status)
    return query.order_by(ImportRow.row_number).offset(offset).limit(limit).all()


# --- Confirm (upsert) --------------------------------------------------


def confirm_import(db: Session, admin: AdminUser, import_job_id: int) -> ImportJob:
    job = get_import_job(db, import_job_id)
    if job.status != ImportJobStatus.VALIDATED:
        raise ConflictError("Import must be validated before it can be confirmed.")

    importable_rows = (
        db.query(ImportRow)
        .filter(ImportRow.import_job_id == import_job_id, ImportRow.validation_status != ImportRowValidationStatus.ERROR)
        .all()
    )

    created = 0
    updated = 0

    for row in importable_rows:
        mapped = row.mapped_data or {}

        if row.action == ImportRowAction.UPDATE and row.resident_id is not None:
            resident = db.get(Resident, row.resident_id)
            resident.full_name = mapped.get("full_name") or resident.full_name
            resident.mobile_number = mapped.get("mobile_number") or resident.mobile_number
            if mapped.get("email"):
                resident.email = mapped["email"]
            updated += 1
        else:
            resident = Resident(
                community_id=admin.community_id,
                house_number=mapped["house_number"],
                full_name=mapped["full_name"],
                mobile_number=mapped["mobile_number"],
                email=mapped.get("email"),
            )
            db.add(resident)
            db.flush()
            row.resident_id = resident.resident_id
            created += 1

        meter_serial = mapped.get("meter_serial_number")
        if meter_serial:
            existing_meter = db.query(Meter).filter(Meter.meter_serial_number == meter_serial).first()
            if existing_meter is None:
                db.add(
                    Meter(
                        resident_id=resident.resident_id,
                        meter_serial_number=meter_serial,
                        install_date=_parse_date(mapped.get("install_date")),
                    )
                )

    job.status = ImportJobStatus.CONFIRMED
    job.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="import.confirm",
        entity_type="import_job",
        entity_id=job.import_job_id,
        after_state={"residents_created": created, "residents_updated": updated},
    )

    db.refresh(job)
    return job
