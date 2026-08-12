"""Auth-domain exceptions.

Kept separate from HTTP concerns: services raise these, routers catch them
and map to the appropriate HTTPException/status code. Business logic never
lives in the router layer, only the HTTP mapping does.
"""

from __future__ import annotations


class AuthError(Exception):
    """Base class for all authentication/authorization failures."""


class RegisteredRecordMismatchError(AuthError):
    """House number / mobile number combination doesn't match any resident.

    Deliberately generic — never reveals which field was wrong."""


class AlreadyOnboardedError(AuthError):
    """Resident has already completed signup (password already set)."""


class NotOnboardedError(AuthError):
    """Resident exists but hasn't completed signup yet (no password set)."""


class InvalidCredentialsError(AuthError):
    """Wrong house_number/password or email/password at login."""


class OtpInvalidError(AuthError):
    """Submitted OTP does not match the stored hash."""


class OtpExpiredError(AuthError):
    """OTP record found but past its expires_at."""


class OtpMaxAttemptsExceededError(AuthError):
    """Too many failed verification attempts for this OTP request."""


class OtpNotFoundError(AuthError):
    """No pending OTP request exists for this resident/purpose."""


class InvalidTokenError(AuthError):
    """Signup/password-reset access token is invalid, expired, or the
    wrong scope for the endpoint that received it."""


class InvalidRefreshTokenError(AuthError):
    """Refresh token not found, expired, or already revoked."""


class RefreshTokenReuseDetectedError(AuthError):
    """A previously-rotated (revoked) refresh token was presented again —
    signals possible token theft; the whole token family is revoked."""


class AccountInactiveError(AuthError):
    """Resident or admin account has been deactivated."""


# --- HTTP mapping ------------------------------------------------------
# Centralized here so every router maps AuthError -> HTTPException the same
# way, instead of each router re-deciding status codes.

_STATUS_MAP: dict[type[AuthError], int] = {
    RegisteredRecordMismatchError: 400,
    AlreadyOnboardedError: 409,
    NotOnboardedError: 400,
    InvalidCredentialsError: 401,
    OtpNotFoundError: 400,
    OtpExpiredError: 400,
    OtpInvalidError: 400,
    OtpMaxAttemptsExceededError: 429,
    InvalidTokenError: 401,
    InvalidRefreshTokenError: 401,
    RefreshTokenReuseDetectedError: 401,
    AccountInactiveError: 403,
}


def auth_error_status_code(exc: AuthError) -> int:
    return _STATUS_MAP.get(type(exc), 400)
