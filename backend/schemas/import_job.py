"""Pydantic v2 request/response DTOs for the admin spreadsheet import flow."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_job_id: int
    source_type: str
    original_filename: str
    status: str
    total_rows: int
    valid_rows: int
    error_rows: int
    created_at: datetime
    confirmed_at: datetime | None


class ImportColumnsResponse(BaseModel):
    columns: list[str]
    suggested_mapping: dict[str, str | None]


class ImportMappingRequest(BaseModel):
    # canonical_field -> source_column_name, or None for an unmapped
    # optional field (e.g. email/install_date with no matching column)
    mapping: dict[str, str | None]


class ImportRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_row_id: int
    row_number: int
    raw_data: dict
    mapped_data: dict | None
    validation_status: str
    validation_errors: list[str] | None
    action: str | None
    resident_id: int | None
