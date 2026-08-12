"""Admin login — deliberately a separate router/prefix from resident auth,
never sharing a code path with routers/auth.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_db
from backend.core.exceptions import AuthError, auth_error_status_code
from backend.schemas.auth import AdminLoginRequest, TokenPairResponse
from backend.services import auth_service

router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=TokenPairResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    try:
        return auth_service.login_admin(db, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc
