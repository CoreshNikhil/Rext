"""Tests for the three endpoint groups that were in the approved plan but
had fallen through every phase's file list: PATCH /resident/me, the admin
dashboard, and admin system-config."""

from __future__ import annotations

from decimal import Decimal

from backend.db.models.enums import BillingPeriodStatus
from backend.services import auth_service, billing_service
from backend.tests.conftest import (
    seed_admin,
    seed_billing_period,
    seed_finalized_reading,
    seed_meter,
    seed_resident,
    seed_system_config,
)


def _admin_auth_header(db) -> dict:
    seed_admin(db, email="owner@example.com", password="AdminPass123!")
    pair = auth_service.login_admin(db, "owner@example.com", "AdminPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


def _resident_auth_header(db, resident) -> dict:
    pair = auth_service.login_resident(db, resident.house_number, "OldPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


# --- PATCH /resident/me --------------------------------------------------


def test_resident_can_update_own_email(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="G-1", mobile="9700000001")
    headers = _resident_auth_header(db, resident)

    resp = client.patch("/api/v1/resident/me", headers=headers, json={"email": "resident@example.com"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "resident@example.com"

    resp = client.get("/api/v1/resident/me", headers=headers)
    assert resp.json()["email"] == "resident@example.com"


def test_resident_me_includes_assigned_meter(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="G-2", mobile="9700000002")
    seed_meter(db, resident, serial="MTR-G2")
    headers = _resident_auth_header(db, resident)

    resp = client.get("/api/v1/resident/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["meters"][0]["meter_serial_number"] == "MTR-G2"


def test_admin_cannot_access_resident_me(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    resp = client.get("/api/v1/resident/me", headers=headers)
    assert resp.status_code == 401


# --- Admin dashboard -----------------------------------------------------


def test_dashboard_overview_reflects_real_billing_state(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="owner2@example.com", password="pw")  # ensures community exists via helper reuse
    resident_a = seed_resident(db, house_number="H-1", mobile="9800000001")
    resident_b = seed_resident(db, house_number="H-2", mobile="9800000002")
    meter_a = seed_meter(db, resident_a, serial="MTR-H1")
    seed_meter(db, resident_b, serial="MTR-H2")  # resident_b never submits a reading

    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident_a, meter_a, period, previous=Decimal("100.000"), final=Decimal("115.197"))
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)

    resp = client.get("/api/v1/admin/dashboard/overview", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["bills_generated"] == 1
    assert body["bills_unpaid"] == 1
    assert body["total_billed"] == "759.85"
    assert body["total_collected"] == "0.00"
    assert body["outstanding"] == "759.85"
    # 2 residents active for this billing period, only 1 submitted.
    assert body["readings_submitted"] == 1
    assert body["readings_pending"] >= 1


def test_dashboard_collections_computes_rate(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="owner3@example.com", password="pw")
    resident = seed_resident(db, house_number="H-3", mobile="9800000003")
    meter = seed_meter(db, resident, serial="MTR-H3")

    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED, period_label="collections-test")
    seed_finalized_reading(db, resident, meter, period, previous=Decimal("0.000"), final=Decimal("10.000"))
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]
    billing_service.get_bill(db, bill.bill_id)  # sanity — bill exists

    resp = client.get("/api/v1/admin/dashboard/collections", headers=headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["billing_period_id"] == period.billing_period_id)
    assert row["total_billed"] == "500.00"
    assert row["collection_rate_percent"] == "0.00"  # nothing paid yet


def test_resident_cannot_access_admin_dashboard(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="H-4", mobile="9800000004")
    headers = _resident_auth_header(db, resident)

    resp = client.get("/api/v1/admin/dashboard/overview", headers=headers)
    assert resp.status_code == 401


# --- Admin system config ------------------------------------------------


def test_list_system_config_includes_seeded_keys(client_and_session):
    client, db = client_and_session
    seed_system_config(db)
    headers = _admin_auth_header(db)

    resp = client.get("/api/v1/admin/system-config", headers=headers)
    assert resp.status_code == 200
    keys = {c["key"] for c in resp.json()}
    assert "default_rate_per_unit" in keys
    assert "otp_expiry_minutes" in keys


def test_update_system_config_float_value(client_and_session):
    client, db = client_and_session
    seed_system_config(db)
    headers = _admin_auth_header(db)

    resp = client.patch("/api/v1/admin/system-config/default_rate_per_unit", headers=headers, json={"value": "55.00"})
    assert resp.status_code == 200
    assert resp.json()["value"] == "55.00"


def test_update_system_config_rejects_wrong_type(client_and_session):
    client, db = client_and_session
    seed_system_config(db)
    headers = _admin_auth_header(db)

    resp = client.patch("/api/v1/admin/system-config/otp_expiry_minutes", headers=headers, json={"value": "not-a-number"})
    assert resp.status_code == 409


def test_update_unknown_system_config_key_is_not_found(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    resp = client.patch("/api/v1/admin/system-config/does_not_exist", headers=headers, json={"value": "x"})
    assert resp.status_code == 404


def test_resident_cannot_access_system_config(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="H-5", mobile="9800000005")
    headers = _resident_auth_header(db, resident)

    resp = client.get("/api/v1/admin/system-config", headers=headers)
    assert resp.status_code == 401
