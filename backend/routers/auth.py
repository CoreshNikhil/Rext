"""Shared/public auth endpoints: resident signup, login, password reset,
token refresh, logout. Admin login lives in routers/admin_auth.py.

Routers stay thin: each endpoint calls into services/auth_service.py and
maps AuthError subclasses to HTTP responses via
core.exceptions.auth_error_status_code — no business logic here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.deps import get_db, get_otp_provider
from backend.core.exceptions import AuthError, auth_error_status_code
from backend.core.rate_limit import limiter, mobile_number_key
from backend.providers.otp.base import OTPProvider
from backend.schemas.auth import (
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequestOtpRequest,
    PasswordResetVerifyOtpRequest,
    PasswordResetVerifyOtpResponse,
    RefreshRequest,
    ResidentLoginRequest,
    SignupRequestOtpRequest,
    SignupRequestOtpResponse,
    SignupSetPasswordRequest,
    SignupVerifyOtpRequest,
    SignupVerifyOtpResponse,
    TokenPairResponse,
)
from backend.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _dev_otp(raw_otp: str) -> str | None:
    return raw_otp if settings.ENVIRONMENT == "development" else None


@router.post("/resident/signup/request-otp", response_model=SignupRequestOtpResponse)
@limiter.limit("10/hour")
@limiter.limit("3/hour", key_func=mobile_number_key)
def signup_request_otp(
    request: Request,
    payload: SignupRequestOtpRequest,
    db: Session = Depends(get_db),
    otp_provider: OTPProvider = Depends(get_otp_provider),
) -> SignupRequestOtpResponse:
    try:
        raw_otp = auth_service.request_signup_otp(db, payload.house_number, payload.mobile_number, otp_provider)
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc

    return SignupRequestOtpResponse(message="A verification code has been sent.", dev_otp=_dev_otp(raw_otp))


@router.post("/resident/signup/verify-otp", response_model=SignupVerifyOtpResponse)
def signup_verify_otp(payload: SignupVerifyOtpRequest, db: Session = Depends(get_db)) -> SignupVerifyOtpResponse:
    try:
        signup_token = auth_service.verify_signup_otp(
            db, payload.house_number, payload.mobile_number, payload.otp_code
        )
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc

    return SignupVerifyOtpResponse(signup_token=signup_token)


@router.post("/resident/signup/set-password", response_model=TokenPairResponse)
def signup_set_password(payload: SignupSetPasswordRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    try:
        return auth_service.set_signup_password(db, payload.signup_token, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc


@router.post("/resident/login", response_model=TokenPairResponse)
@limiter.limit("5/minute")
def resident_login(request: Request, payload: ResidentLoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    try:
        return auth_service.login_resident(db, payload.house_number, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc


@router.post("/resident/password-reset/request-otp", response_model=SignupRequestOtpResponse)
@limiter.limit("10/hour")
@limiter.limit("3/hour", key_func=mobile_number_key)
def password_reset_request_otp(
    request: Request,
    payload: PasswordResetRequestOtpRequest,
    db: Session = Depends(get_db),
    otp_provider: OTPProvider = Depends(get_otp_provider),
) -> SignupRequestOtpResponse:
    try:
        raw_otp = auth_service.request_password_reset_otp(
            db, payload.house_number, payload.mobile_number, otp_provider
        )
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc

    return SignupRequestOtpResponse(message="A verification code has been sent.", dev_otp=_dev_otp(raw_otp))


@router.post("/resident/password-reset/verify-otp", response_model=PasswordResetVerifyOtpResponse)
def password_reset_verify_otp(
    payload: PasswordResetVerifyOtpRequest, db: Session = Depends(get_db)
) -> PasswordResetVerifyOtpResponse:
    try:
        reset_token = auth_service.verify_password_reset_otp(
            db, payload.house_number, payload.mobile_number, payload.otp_code
        )
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc

    return PasswordResetVerifyOtpResponse(reset_token=reset_token)


@router.post("/resident/password-reset/confirm", response_model=MessageResponse)
def password_reset_confirm(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)) -> MessageResponse:
    try:
        auth_service.confirm_password_reset(db, payload.reset_token, payload.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc

    return MessageResponse(message="Your password has been reset. Please log in with your new password.")


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    try:
        return auth_service.refresh_tokens(db, payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=auth_error_status_code(exc), detail=str(exc)) from exc


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    auth_service.logout(db, payload.refresh_token)
    return MessageResponse(message="Logged out.")
