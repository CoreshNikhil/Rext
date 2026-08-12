"""FastAPI dependencies for DB access and role-scoped authentication.

get_current_resident and get_current_admin are two SEPARATE functions,
each hard-checking the JWT `scope` claim, rather than one shared
"get_current_user" that branches on role. This is deliberate: a
resident-scoped token is structurally incapable of satisfying
get_current_admin (and vice versa) because there is no code path where
one function's logic can accidentally accept the other's scope.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core import security
from backend.db.models.admin_user import AdminUser
from backend.db.models.resident import Resident
from backend.db.session import SessionLocal
from backend.providers.otp.base import OTPProvider
from backend.providers.otp.mock_otp_provider import MockOTPProvider

bearer_scheme = HTTPBearer(auto_error=True)

# Single shared instance — MockOTPProvider is stateless, so one instance
# per process is fine. Swapping to a real provider later is a one-line
# change here, nothing else in the codebase depends on which one is used.
_otp_provider = MockOTPProvider()


def get_otp_provider() -> OTPProvider:
    return _otp_provider


# Constructed lazily on first use, not at import/startup time — mirrors
# app.py's st.cache_resource pattern for the same GeminiProvider class.
# Lazy construction means a missing GEMINI_API_KEY only breaks meter-
# reading submission, not the entire backend (auth/residents/import don't
# need the vision provider at all).
_vision_provider = None


def get_vision_provider():
    global _vision_provider
    if _vision_provider is None:
        from providers.gemini_provider import GeminiProvider

        _vision_provider = GeminiProvider()
    return _vision_provider


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_resident(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Resident:
    try:
        claims = security.decode_access_token(credentials.credentials)
    except security.TokenError as exc:
        raise _unauthorized(str(exc)) from exc

    if claims.get("scope") != "resident":
        raise _unauthorized("This endpoint requires a resident login.")

    resident = db.get(Resident, int(claims["sub"]))
    if resident is None or not resident.is_active:
        raise _unauthorized("Resident account not found or inactive.")

    return resident


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    try:
        claims = security.decode_access_token(credentials.credentials)
    except security.TokenError as exc:
        raise _unauthorized(str(exc)) from exc

    if claims.get("scope") != "admin":
        raise _unauthorized("This endpoint requires an admin login.")

    admin = db.get(AdminUser, int(claims["sub"]))
    if admin is None or not admin.is_active:
        raise _unauthorized("Admin account not found or inactive.")

    return admin
