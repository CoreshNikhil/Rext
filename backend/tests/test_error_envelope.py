"""Phase 8: uniform JSON error envelope. Every error response — a domain
error mapped to an HTTPException, a Pydantic validation failure, a
rate-limit rejection, or a genuinely unhandled exception — must come back
as {"detail": ..., "error_type": ..., "status_code": ...}, not whatever
shape happened to be closest to the code that raised it.
"""

from __future__ import annotations

from backend.services import dashboard_service
from backend.tests.conftest import seed_admin, seed_resident


def _admin_auth_header(client, db) -> dict:
    from backend.services import auth_service

    seed_admin(db, email="envelope-admin@example.com", password="AdminPass123!")
    pair = auth_service.login_admin(db, "envelope-admin@example.com", "AdminPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


def test_http_exception_uses_uniform_envelope(client_and_session):
    """A domain error (NotFoundError -> 404 HTTPException) from an
    existing endpoint — proves the envelope wraps ordinary router-raised
    HTTPExceptions, not just new Phase 8 code."""
    client, db = client_and_session
    headers = _admin_auth_header(client, db)

    resp = client.get("/api/v1/admin/residents/999999", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["status_code"] == 404
    assert body["error_type"] == "not_found"
    assert isinstance(body["detail"], str)


def test_validation_error_uses_uniform_envelope(client_and_session):
    client, db = client_and_session

    # Missing required fields entirely -> Pydantic RequestValidationError.
    resp = client.post("/api/v1/auth/resident/login", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["status_code"] == 422
    assert body["error_type"] == "validation_error"
    assert isinstance(body["detail"], list)
    assert body["detail"]  # at least one field error


def test_rate_limit_exceeded_uses_uniform_envelope_not_slowapi_default(client_and_session):
    """slowapi's own default handler returns {"error": "..."} — this
    confirms the app-wide envelope wins instead, which requires an
    explicit registration since SlowAPIMiddleware bypasses Starlette's
    normal exception dispatch (see core/error_handlers.py)."""
    client, db = client_and_session
    seed_resident(db, onboarded=True, house_number="EV-1", mobile="9700000010")

    for _ in range(5):
        client.post("/api/v1/auth/resident/login", json={"house_number": "EV-1", "password": "wrong"})

    resp = client.post("/api/v1/auth/resident/login", json={"house_number": "EV-1", "password": "wrong"})
    assert resp.status_code == 429
    body = resp.json()
    assert "error" not in body
    assert body["status_code"] == 429
    assert body["error_type"] == "rate_limited"
    assert isinstance(body["detail"], str)


def test_unhandled_exception_uses_uniform_envelope_and_hides_internals(client_and_session, monkeypatch):
    """A real client only ever sees the JSON envelope built by
    ServerErrorMiddleware's registered handler — but that middleware also
    always re-raises the original exception afterwards (so ASGI servers
    can log it), and TestClient's default raise_server_exceptions=True
    surfaces that re-raise in tests. Build a client with that off, since
    what we're checking here is exactly what a real client receives."""
    from fastapi.testclient import TestClient

    client, db = client_and_session
    headers = _admin_auth_header(client, db)
    no_raise_client = TestClient(client.app, raise_server_exceptions=False)

    def _boom(db, community_id):
        raise RuntimeError("db connection pool exhausted at host 10.0.0.5")

    monkeypatch.setattr(dashboard_service, "get_overview", _boom)

    resp = no_raise_client.get("/api/v1/admin/dashboard/overview", headers=headers)
    assert resp.status_code == 500
    body = resp.json()
    assert body["status_code"] == 500
    assert body["error_type"] == "internal_error"
    assert body["detail"] == "An unexpected error occurred."
    assert "10.0.0.5" not in resp.text
    assert "RuntimeError" not in resp.text
