"""End-to-end auth flow tests via FastAPI's TestClient — exercises the full
HTTP stack (routers -> auth_service -> DB), not just the service layer, so
router-level status-code mapping is covered too.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core import deps, security
from backend.db import models  # noqa: F401 - registers every table on Base.metadata
from backend.db.base import Base
from backend.db.models.admin_user import AdminUser
from backend.db.models.community import Community
from backend.db.models.resident import Resident
from backend.main import app


@pytest.fixture()
def client_and_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    client = TestClient(app)

    setup_session = test_session_factory()
    try:
        yield client, setup_session
    finally:
        setup_session.close()
        app.dependency_overrides.clear()
        engine.dispose()


def _seed_resident(db, *, onboarded: bool = False, house_number: str = "A-204", mobile: str = "9876543210") -> Resident:
    community = db.query(Community).first()
    if community is None:
        community = Community(name="Test Community")
        db.add(community)
        db.flush()

    resident = Resident(
        community_id=community.community_id,
        house_number=house_number,
        full_name="Test Resident",
        mobile_number=mobile,
        password_hash=security.hash_password("OldPass123!") if onboarded else None,
    )
    db.add(resident)
    db.commit()
    db.refresh(resident)
    return resident


def _seed_admin(db, *, email: str = "admin@example.com", password: str = "AdminPass123!") -> AdminUser:
    community = db.query(Community).first()
    if community is None:
        community = Community(name="Test Community")
        db.add(community)
        db.flush()

    admin = AdminUser(
        community_id=community.community_id, email=email, full_name="Test Admin", password_hash=security.hash_password(password)
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


# --- Signup --------------------------------------------------------------


def test_signup_happy_path(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=False)

    resp = client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210"},
    )
    assert resp.status_code == 200
    otp = resp.json()["dev_otp"]
    assert otp is not None and len(otp) == 6

    resp = client.post(
        "/api/v1/auth/resident/signup/verify-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210", "otp_code": otp},
    )
    assert resp.status_code == 200
    signup_token = resp.json()["signup_token"]

    resp = client.post(
        "/api/v1/auth/resident/signup/set-password",
        json={"signup_token": signup_token, "password": "NewPass123!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "NewPass123!"})
    assert resp.status_code == 200


def test_signup_wrong_mobile_number_is_rejected_generically(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=False, mobile="9876543210")

    resp = client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "A-204", "mobile_number": "1111111111"},
    )
    assert resp.status_code == 400
    assert "do not match" in resp.json()["detail"]


def test_signup_nonexistent_house_number_is_rejected_generically(client_and_session):
    client, _db = client_and_session

    resp = client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "Z-999", "mobile_number": "9876543210"},
    )
    assert resp.status_code == 400
    assert "do not match" in resp.json()["detail"]


def test_duplicate_signup_is_rejected(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=True)

    resp = client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210"},
    )
    assert resp.status_code == 409
    assert "already been set up" in resp.json()["detail"]


def test_signup_otp_wrong_code_is_rejected(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=False)

    client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210"},
    )
    resp = client.post(
        "/api/v1/auth/resident/signup/verify-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210", "otp_code": "000000"},
    )
    assert resp.status_code == 400


# --- Login -----------------------------------------------------------------


def test_login_happy_path(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=True)

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "OldPass123!"})
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_login_wrong_password_is_rejected(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=True)

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "WrongPass!"})
    assert resp.status_code == 401


def test_login_before_signup_completed_is_rejected(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=False)

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "anything"})
    assert resp.status_code == 400
    assert "hasn't completed signup" in resp.json()["detail"]


# --- Admin login ---------------------------------------------------------


def test_admin_login_happy_path(client_and_session):
    client, db = client_and_session
    _seed_admin(db)

    resp = client.post("/api/v1/admin/auth/login", json={"email": "admin@example.com", "password": "AdminPass123!"})
    assert resp.status_code == 200


def test_admin_login_wrong_password_is_rejected(client_and_session):
    client, db = client_and_session
    _seed_admin(db)

    resp = client.post("/api/v1/admin/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert resp.status_code == 401


# --- Refresh / logout --------------------------------------------------


def test_refresh_rotates_token_and_old_one_becomes_unusable(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=True)

    login_resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "OldPass123!"})
    old_refresh = login_resp.json()["refresh_token"]

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Reusing the now-rotated-out token must fail...
    reuse_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_resp.status_code == 401

    # ...and per the reuse-detection design, the whole family — including
    # the token issued by the legitimate refresh — is revoked too.
    new_refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert new_refresh_resp.status_code == 401


def test_logout_revokes_refresh_token(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=True)

    login_resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "OldPass123!"})
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 200

    refresh_after_logout = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after_logout.status_code == 401


# --- Password reset ------------------------------------------------------


def test_password_reset_happy_path(client_and_session):
    client, db = client_and_session
    _seed_resident(db, onboarded=True)

    resp = client.post(
        "/api/v1/auth/resident/password-reset/request-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210"},
    )
    assert resp.status_code == 200
    otp = resp.json()["dev_otp"]

    resp = client.post(
        "/api/v1/auth/resident/password-reset/verify-otp",
        json={"house_number": "A-204", "mobile_number": "9876543210", "otp_code": otp},
    )
    assert resp.status_code == 200
    reset_token = resp.json()["reset_token"]

    resp = client.post(
        "/api/v1/auth/resident/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": "BrandNewPass1!"},
    )
    assert resp.status_code == 200

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "BrandNewPass1!"})
    assert resp.status_code == 200

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-204", "password": "OldPass123!"})
    assert resp.status_code == 401


# --- Role separation (dependency-level, since no protected business ---
# --- routes exist yet in this phase) ------------------------------------


def test_resident_scoped_token_cannot_satisfy_admin_dependency(client_and_session):
    _client, db = client_and_session
    resident = _seed_resident(db, onboarded=True)

    token = security.create_access_token(resident.resident_id, "resident", timedelta(minutes=5))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    result = deps.get_current_resident(credentials=credentials, db=db)
    assert result.resident_id == resident.resident_id

    with pytest.raises(Exception) as exc_info:
        deps.get_current_admin(credentials=credentials, db=db)
    assert exc_info.value.status_code == 401


def test_admin_scoped_token_cannot_satisfy_resident_dependency(client_and_session):
    _client, db = client_and_session
    admin = _seed_admin(db)

    token = security.create_access_token(admin.admin_id, "admin", timedelta(minutes=5))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    result = deps.get_current_admin(credentials=credentials, db=db)
    assert result.admin_id == admin.admin_id

    with pytest.raises(Exception) as exc_info:
        deps.get_current_resident(credentials=credentials, db=db)
    assert exc_info.value.status_code == 401
