"""Auth business logic: signup, login, password reset, token issuance and
refresh rotation.

No FastAPI/HTTP imports here — routers translate the exceptions below into
HTTP responses. Keeping this layer HTTP-free means it's directly unit
testable and is the actual place authorization/business rules live, not
the router.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core import security
from backend.core.config import settings
from backend.core.exceptions import (
    AccountInactiveError,
    AlreadyOnboardedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidTokenError,
    NotOnboardedError,
    OtpExpiredError,
    OtpInvalidError,
    OtpMaxAttemptsExceededError,
    OtpNotFoundError,
    RefreshTokenReuseDetectedError,
    RegisteredRecordMismatchError,
)
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import OtpPurpose, TokenSubjectType
from backend.db.models.otp_request import OtpRequest
from backend.db.models.refresh_token import RefreshToken
from backend.db.models.resident import Resident
from backend.providers.otp.base import OTPProvider
from backend.schemas.auth import TokenPairResponse

ACCESS_TTL = timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
REFRESH_TTL_RESIDENT = timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS_RESIDENT)
REFRESH_TTL_ADMIN = timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS_ADMIN)
SIGNUP_TOKEN_TTL = timedelta(minutes=15)
PASSWORD_RESET_TOKEN_TTL = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue_token_pair(db: Session, subject_type: TokenSubjectType, subject_id: int) -> TokenPairResponse:
    scope = "resident" if subject_type == TokenSubjectType.RESIDENT else "admin"
    refresh_ttl = REFRESH_TTL_RESIDENT if subject_type == TokenSubjectType.RESIDENT else REFRESH_TTL_ADMIN

    access_token = security.create_access_token(subject_id, scope, ACCESS_TTL)

    raw_refresh = security.generate_refresh_token()
    db.add(
        RefreshToken(
            subject_type=subject_type,
            subject_id=subject_id,
            token_hash=security.hash_refresh_token(raw_refresh),
            expires_at=_now() + refresh_ttl,
        )
    )
    db.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=raw_refresh)


def _find_matching_resident(db: Session, house_number: str, mobile_number: str) -> Resident:
    resident = db.query(Resident).filter(Resident.house_number == house_number).first()
    if resident is None or resident.mobile_number != mobile_number or not resident.is_active:
        # Deliberately generic — never reveals which field was wrong.
        raise RegisteredRecordMismatchError(
            "These details do not match our registered records. Please contact your administrator."
        )
    return resident


def _create_otp(db: Session, purpose: OtpPurpose, resident: Resident) -> str:
    raw_otp = security.generate_otp_code()
    db.add(
        OtpRequest(
            purpose=purpose,
            resident_id=resident.resident_id,
            mobile_number=resident.mobile_number,
            otp_hash=security.hash_otp(raw_otp),
            expires_at=_now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        )
    )
    db.commit()
    return raw_otp


def _verify_and_consume_otp(db: Session, purpose: OtpPurpose, resident: Resident, otp_code: str) -> None:
    otp_request = (
        db.query(OtpRequest)
        .filter(
            OtpRequest.resident_id == resident.resident_id,
            OtpRequest.purpose == purpose,
            OtpRequest.is_used.is_(False),
        )
        .order_by(OtpRequest.otp_id.desc())
        .first()
    )
    if otp_request is None:
        raise OtpNotFoundError("No pending verification code was found. Please request a new one.")

    if otp_request.expires_at < _now():
        raise OtpExpiredError("This verification code has expired. Please request a new one.")

    if otp_request.attempt_count >= otp_request.max_attempts:
        raise OtpMaxAttemptsExceededError("Too many incorrect attempts. Please request a new verification code.")

    if not security.verify_otp(otp_code, otp_request.otp_hash):
        otp_request.attempt_count += 1
        db.commit()
        raise OtpInvalidError("Incorrect verification code.")

    otp_request.is_used = True
    db.commit()


def _decode_scoped_token(token: str, expected_scope: str) -> dict:
    try:
        claims = security.decode_access_token(token)
    except security.TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if claims.get("scope") != expected_scope:
        raise InvalidTokenError(f"Expected a {expected_scope} token.")
    return claims


def _revoke_all_refresh_tokens(db: Session, subject_type: TokenSubjectType, subject_id: int) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.subject_type == subject_type,
        RefreshToken.subject_id == subject_id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": _now()})
    db.commit()


# --- Signup ------------------------------------------------------------


def request_signup_otp(db: Session, house_number: str, mobile_number: str, otp_provider: OTPProvider) -> str:
    resident = _find_matching_resident(db, house_number, mobile_number)
    if resident.password_hash is not None:
        raise AlreadyOnboardedError("This account has already been set up. Please log in instead.")

    raw_otp = _create_otp(db, OtpPurpose.SIGNUP, resident)
    otp_provider.send_otp(mobile_number, raw_otp)
    return raw_otp


def verify_signup_otp(db: Session, house_number: str, mobile_number: str, otp_code: str) -> str:
    resident = _find_matching_resident(db, house_number, mobile_number)
    if resident.password_hash is not None:
        raise AlreadyOnboardedError("This account has already been set up. Please log in instead.")

    _verify_and_consume_otp(db, OtpPurpose.SIGNUP, resident, otp_code)
    return security.create_access_token(resident.resident_id, "resident_signup", SIGNUP_TOKEN_TTL)


def set_signup_password(db: Session, signup_token: str, new_password: str) -> TokenPairResponse:
    claims = _decode_scoped_token(signup_token, "resident_signup")
    resident_id = int(claims["sub"])

    resident = db.get(Resident, resident_id)
    if resident is None or not resident.is_active:
        raise RegisteredRecordMismatchError("This account could not be found.")
    if resident.password_hash is not None:
        raise AlreadyOnboardedError("This account has already been set up. Please log in instead.")

    resident.password_hash = security.hash_password(new_password)
    resident.onboarded_at = _now()
    db.commit()

    # Auto-login immediately after signup completes — matches "Account
    # becomes active" in the spec rather than forcing an extra login step.
    return _issue_token_pair(db, TokenSubjectType.RESIDENT, resident.resident_id)


# --- Login ---------------------------------------------------------------


def login_resident(db: Session, house_number: str, password: str) -> TokenPairResponse:
    resident = db.query(Resident).filter(Resident.house_number == house_number).first()
    if resident is None:
        raise InvalidCredentialsError("Incorrect house number or password.")
    if not resident.is_active:
        raise AccountInactiveError("This account has been deactivated. Please contact your administrator.")
    if resident.password_hash is None:
        raise NotOnboardedError("This account hasn't completed signup yet. Please sign up first.")
    if not security.verify_password(password, resident.password_hash):
        raise InvalidCredentialsError("Incorrect house number or password.")

    return _issue_token_pair(db, TokenSubjectType.RESIDENT, resident.resident_id)


def login_admin(db: Session, email: str, password: str) -> TokenPairResponse:
    admin = db.query(AdminUser).filter(AdminUser.email == email).first()
    if admin is None or not security.verify_password(password, admin.password_hash):
        raise InvalidCredentialsError("Incorrect email or password.")
    if not admin.is_active:
        raise AccountInactiveError("This admin account has been deactivated.")

    admin.last_login_at = _now()
    db.commit()

    return _issue_token_pair(db, TokenSubjectType.ADMIN, admin.admin_id)


# --- Password reset ------------------------------------------------------


def request_password_reset_otp(
    db: Session, house_number: str, mobile_number: str, otp_provider: OTPProvider
) -> str:
    resident = _find_matching_resident(db, house_number, mobile_number)
    if resident.password_hash is None:
        raise NotOnboardedError("This account hasn't completed signup yet. Please sign up first.")

    raw_otp = _create_otp(db, OtpPurpose.PASSWORD_RESET, resident)
    otp_provider.send_otp(mobile_number, raw_otp)
    return raw_otp


def verify_password_reset_otp(db: Session, house_number: str, mobile_number: str, otp_code: str) -> str:
    resident = _find_matching_resident(db, house_number, mobile_number)
    _verify_and_consume_otp(db, OtpPurpose.PASSWORD_RESET, resident, otp_code)
    return security.create_access_token(resident.resident_id, "password_reset", PASSWORD_RESET_TOKEN_TTL)


def confirm_password_reset(db: Session, reset_token: str, new_password: str) -> None:
    claims = _decode_scoped_token(reset_token, "password_reset")
    resident_id = int(claims["sub"])

    resident = db.get(Resident, resident_id)
    if resident is None or not resident.is_active:
        raise RegisteredRecordMismatchError("This account could not be found.")

    resident.password_hash = security.hash_password(new_password)
    db.commit()

    # A password reset invalidates every existing session, not just the
    # one that requested the reset.
    _revoke_all_refresh_tokens(db, TokenSubjectType.RESIDENT, resident.resident_id)


# --- Refresh / logout --------------------------------------------------


def refresh_tokens(db: Session, raw_refresh_token: str) -> TokenPairResponse:
    token_hash = security.hash_refresh_token(raw_refresh_token)
    token_row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if token_row is None:
        raise InvalidRefreshTokenError("Refresh token is invalid.")

    if token_row.revoked_at is not None:
        # This token was already rotated out once — presenting it again
        # may mean it was stolen. Simplified reuse response at this scale:
        # revoke every active refresh token for the subject, rather than
        # precisely walking the replaced_by_token_id chain.
        _revoke_all_refresh_tokens(db, token_row.subject_type, token_row.subject_id)
        raise RefreshTokenReuseDetectedError("This session is no longer valid. Please log in again.")

    if token_row.expires_at < _now():
        raise InvalidRefreshTokenError("Refresh token has expired. Please log in again.")

    new_pair = _issue_token_pair(db, token_row.subject_type, token_row.subject_id)

    new_token_hash = security.hash_refresh_token(new_pair.refresh_token)
    new_row = db.query(RefreshToken).filter(RefreshToken.token_hash == new_token_hash).first()

    token_row.revoked_at = _now()
    token_row.replaced_by_token_id = new_row.refresh_token_id
    db.commit()

    return new_pair


def logout(db: Session, raw_refresh_token: str) -> None:
    token_hash = security.hash_refresh_token(raw_refresh_token)
    token_row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if token_row is not None and token_row.revoked_at is None:
        token_row.revoked_at = _now()
        db.commit()
