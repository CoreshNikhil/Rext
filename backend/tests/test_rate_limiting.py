"""Phase 8: slowapi rate limiting on auth and payment-confirm endpoints.

Each test drives an endpoint past its configured limit and checks the
first-over-limit request gets a 429 — proving the @limiter.limit(...)
decorators in routers/auth.py, admin_auth.py, and payments.py are actually
wired up and enforced, not just present as unused decorators.
"""

from __future__ import annotations

from backend.services import auth_service
from backend.tests.conftest import seed_admin, seed_resident


def _resident_auth_header(db, resident) -> dict:
    pair = auth_service.login_resident(db, resident.house_number, "OldPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


# --- Login: 5/minute per IP -------------------------------------------


def test_resident_login_rate_limited_after_five_per_minute(client_and_session):
    client, db = client_and_session
    seed_resident(db, onboarded=True, house_number="A-1", mobile="9000000001")

    for _ in range(5):
        resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-1", "password": "WrongPass!"})
        assert resp.status_code == 401

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "A-1", "password": "WrongPass!"})
    assert resp.status_code == 429


def test_admin_login_rate_limited_after_five_per_minute(client_and_session):
    client, db = client_and_session
    seed_admin(db, email="rl-admin@example.com", password="AdminPass123!")

    for _ in range(5):
        resp = client.post("/api/v1/admin/auth/login", json={"email": "rl-admin@example.com", "password": "wrong"})
        assert resp.status_code == 401

    resp = client.post("/api/v1/admin/auth/login", json={"email": "rl-admin@example.com", "password": "wrong"})
    assert resp.status_code == 429


# --- OTP request: 3/hour per mobile, 10/hour per IP --------------------


def test_signup_otp_request_rate_limited_by_mobile_number(client_and_session):
    client, db = client_and_session
    seed_resident(db, onboarded=False, house_number="B-1", mobile="9000000002")

    for _ in range(3):
        resp = client.post(
            "/api/v1/auth/resident/signup/request-otp",
            json={"house_number": "B-1", "mobile_number": "9000000002"},
        )
        assert resp.status_code == 200

    resp = client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "B-1", "mobile_number": "9000000002"},
    )
    assert resp.status_code == 429


def test_signup_otp_request_rate_limited_by_ip_across_different_mobiles(client_and_session):
    client, db = client_and_session
    for i in range(10):
        seed_resident(db, onboarded=False, house_number=f"C-{i}", mobile=f"90000001{i:02d}")
        resp = client.post(
            "/api/v1/auth/resident/signup/request-otp",
            json={"house_number": f"C-{i}", "mobile_number": f"90000001{i:02d}"},
        )
        # Each mobile number is used only once here, so the per-mobile 3/hour
        # limit never trips — only the per-IP 10/hour limit is in play.
        assert resp.status_code == 200

    seed_resident(db, onboarded=False, house_number="C-10", mobile="9000000199")
    resp = client.post(
        "/api/v1/auth/resident/signup/request-otp",
        json={"house_number": "C-10", "mobile_number": "9000000199"},
    )
    assert resp.status_code == 429


# --- Payment mock-confirm: 10/minute per IP -----------------------------


def test_mock_confirm_payment_rate_limited_after_ten_per_minute(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="D-1", mobile="9000000003")
    headers = _resident_auth_header(db, resident)

    for _ in range(10):
        resp = client.post(
            "/api/v1/payments/999999/mock-confirm", headers=headers, json={"simulate_success": True}
        )
        # No such payment exists — the point is that the rate-limit check
        # runs (and counts) before the 404 from the business logic.
        assert resp.status_code == 404

    resp = client.post("/api/v1/payments/999999/mock-confirm", headers=headers, json={"simulate_success": True})
    assert resp.status_code == 429
