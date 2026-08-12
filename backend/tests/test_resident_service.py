"""End-to-end tests for admin resident CRUD via FastAPI's TestClient —
covers create/list/get/update/soft-delete, meter assignment, admin-only
access enforcement, and that reset-password actually revokes sessions.
"""

from __future__ import annotations

from backend.core import security
from backend.db.models.refresh_token import RefreshToken
from backend.services import auth_service
from backend.tests.conftest import seed_admin, seed_resident


def _admin_auth_header(db) -> dict:
    admin = seed_admin(db, email="owner@example.com", password="AdminPass123!")
    pair = auth_service.login_admin(db, "owner@example.com", "AdminPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}, admin


def test_create_and_get_resident(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)

    resp = client.post(
        "/api/v1/admin/residents",
        headers=headers,
        json={
            "house_number": "B-101",
            "full_name": "New Resident",
            "mobile_number": "9123456789",
            "meter_serial_number": "MTR-001",
        },
    )
    assert resp.status_code == 201
    resident_id = resp.json()["resident_id"]

    resp = client.get(f"/api/v1/admin/residents/{resident_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["house_number"] == "B-101"
    assert len(body["meters"]) == 1
    assert body["meters"][0]["meter_serial_number"] == "MTR-001"


def test_create_resident_duplicate_house_number_is_rejected(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    seed_resident(db, house_number="C-1", mobile="9111111111")

    resp = client.post(
        "/api/v1/admin/residents",
        headers=headers,
        json={"house_number": "C-1", "full_name": "Duplicate", "mobile_number": "9222222222"},
    )
    assert resp.status_code == 409


def test_create_resident_duplicate_mobile_is_rejected(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    seed_resident(db, house_number="C-1", mobile="9111111111")

    resp = client.post(
        "/api/v1/admin/residents",
        headers=headers,
        json={"house_number": "C-2", "full_name": "Duplicate Mobile", "mobile_number": "9111111111"},
    )
    assert resp.status_code == 409


def test_list_residents_supports_search(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    seed_resident(db, house_number="A-1", mobile="9000000001")
    seed_resident(db, house_number="A-2", mobile="9000000002")

    resp = client.get("/api/v1/admin/residents?search=A-1", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["house_number"] == "A-1"


def test_update_resident(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    resident = seed_resident(db, house_number="D-1", mobile="9333333333")

    resp = client.patch(
        f"/api/v1/admin/residents/{resident.resident_id}", headers=headers, json={"full_name": "Updated Name"}
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


def test_deactivate_resident_is_soft_delete_and_revokes_sessions(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    resident = seed_resident(db, onboarded=True, house_number="E-1", mobile="9444444444")

    login = auth_service.login_resident(db, "E-1", "OldPass123!")
    assert (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == security.hash_refresh_token(login.refresh_token))
        .first()
        .revoked_at
        is None
    )

    resp = client.delete(f"/api/v1/admin/residents/{resident.resident_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Soft-delete: the row still exists, just deactivated.
    still_exists = client.get(f"/api/v1/admin/residents/{resident.resident_id}", headers=headers)
    assert still_exists.status_code == 200

    # And every active session was revoked as a side effect.
    token_row = (
        db.query(RefreshToken).filter(RefreshToken.token_hash == security.hash_refresh_token(login.refresh_token)).first()
    )
    assert token_row.revoked_at is not None


def test_reset_resident_password_invalidates_old_password_and_sessions(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    resident = seed_resident(db, onboarded=True, house_number="F-1", mobile="9555555555")

    login = auth_service.login_resident(db, "F-1", "OldPass123!")

    resp = client.post(f"/api/v1/admin/residents/{resident.resident_id}/reset-password", headers=headers)
    assert resp.status_code == 204

    # Old password no longer works.
    old_login_attempt = client.post("/api/v1/auth/resident/login", json={"house_number": "F-1", "password": "OldPass123!"})
    assert old_login_attempt.status_code == 401

    # And the previously-issued session is dead too.
    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": login.refresh_token})
    assert refresh_resp.status_code == 401


def test_assign_meter_duplicate_serial_is_rejected(client_and_session):
    client, db = client_and_session
    headers, _admin = _admin_auth_header(db)
    resident_a = seed_resident(db, house_number="G-1", mobile="9666666666")
    resident_b = seed_resident(db, house_number="G-2", mobile="9777777777")

    resp = client.post(
        f"/api/v1/admin/residents/{resident_a.resident_id}/meters",
        headers=headers,
        json={"meter_serial_number": "SHARED-METER"},
    )
    assert resp.status_code == 201

    resp = client.post(
        f"/api/v1/admin/residents/{resident_b.resident_id}/meters",
        headers=headers,
        json={"meter_serial_number": "SHARED-METER"},
    )
    assert resp.status_code == 409


def test_resident_token_cannot_access_admin_resident_endpoints(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="H-1", mobile="9888888888")
    login = auth_service.login_resident(db, "H-1", "OldPass123!")

    resp = client.get(
        "/api/v1/admin/residents", headers={"Authorization": f"Bearer {login.access_token}"}
    )
    assert resp.status_code == 401


def test_no_token_cannot_access_admin_resident_endpoints(client_and_session):
    client, _db = client_and_session
    resp = client.get("/api/v1/admin/residents")
    assert resp.status_code in (401, 403)  # HTTPBearer auto_error returns 403 when no header at all
