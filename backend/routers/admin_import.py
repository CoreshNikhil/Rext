"""Admin spreadsheet import: upload -> columns -> mapping -> validate ->
preview -> confirm -> history. Admin-scoped only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.core.deps import get_current_admin, get_db
from backend.core.domain_exceptions import DomainError, domain_error_status_code
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import ImportRowValidationStatus, ImportSourceType
from backend.schemas.import_job import (
    ImportColumnsResponse,
    ImportJobResponse,
    ImportMappingRequest,
    ImportRowResponse,
)
from backend.services import import_service

router = APIRouter(
    prefix="/api/v1/admin/imports", tags=["admin-import"], dependencies=[Depends(get_current_admin)]
)


def _detect_source_type(filename: str) -> ImportSourceType:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return ImportSourceType.CSV
    if lower.endswith((".xlsx", ".xls")):
        return ImportSourceType.EXCEL
    raise HTTPException(status_code=400, detail="Unsupported file type. Upload a .xlsx or .csv file.")


@router.post("/upload", response_model=ImportJobResponse, status_code=201)
async def upload_import(
    file: UploadFile = File(...),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    source_type = _detect_source_type(file.filename or "upload")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    job = import_service.create_import_job(db, admin, source_type, file.filename or "upload", file_bytes)
    return ImportJobResponse.model_validate(job)


@router.get("/{import_job_id}/columns", response_model=ImportColumnsResponse)
def get_columns(import_job_id: int, db: Session = Depends(get_db)) -> ImportColumnsResponse:
    try:
        columns, suggestion = import_service.get_columns_and_suggestion(db, import_job_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ImportColumnsResponse(columns=columns, suggested_mapping=suggestion)


@router.post("/{import_job_id}/mapping", response_model=ImportJobResponse)
def confirm_mapping(
    import_job_id: int, payload: ImportMappingRequest, db: Session = Depends(get_db)
) -> ImportJobResponse:
    try:
        job = import_service.confirm_mapping(db, import_job_id, payload.mapping)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ImportJobResponse.model_validate(job)


@router.post("/{import_job_id}/validate", response_model=ImportJobResponse)
def validate_import(import_job_id: int, db: Session = Depends(get_db)) -> ImportJobResponse:
    try:
        job = import_service.validate_import(db, import_job_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ImportJobResponse.model_validate(job)


@router.get("/{import_job_id}/preview", response_model=list[ImportRowResponse])
def preview_import(
    import_job_id: int,
    status: ImportRowValidationStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[ImportRowResponse]:
    try:
        rows = import_service.get_import_rows(db, import_job_id, status=status, limit=limit, offset=offset)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return [ImportRowResponse.model_validate(r) for r in rows]


@router.post("/{import_job_id}/confirm", response_model=ImportJobResponse)
def confirm_import(
    import_job_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    try:
        job = import_service.confirm_import(db, admin, import_job_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ImportJobResponse.model_validate(job)


@router.get("", response_model=list[ImportJobResponse])
def list_imports(db: Session = Depends(get_db)) -> list[ImportJobResponse]:
    jobs = import_service.list_import_jobs(db)
    return [ImportJobResponse.model_validate(j) for j in jobs]


@router.get("/{import_job_id}", response_model=ImportJobResponse)
def get_import(import_job_id: int, db: Session = Depends(get_db)) -> ImportJobResponse:
    try:
        job = import_service.get_import_job(db, import_job_id)
    except DomainError as exc:
        raise HTTPException(status_code=domain_error_status_code(exc), detail=str(exc)) from exc
    return ImportJobResponse.model_validate(job)
