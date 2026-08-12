"""Tests for the payment flow: initiate (amount always server-side from
Bill), mock-confirm success/failure -> Bill PAID wiring, admin mark-
offline, and ownership/access enforcement."""

from __future__ import annotations

import pytest

from backend.core.domain_exceptions import ConflictError
from backend.db.models.enums import BillingPeriodStatus, BillStatus, PaymentStatus
from backend.services import auth_service, billing_service, payment_service
from backend.tests.conftest import (
    seed_admin,
    seed_billing_period,
    seed_finalized_reading,
    seed_meter,
    seed_resident,
)


def _admin_auth_header(db) -> dict:
    seed_admin(db, email="owner@example.com", password="AdminPass123!")
    pair = auth_service.login_admin(db, "owner@example.com", "AdminPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


def _resident_auth_header(db, resident) -> dict:
    pair = auth_service.login_resident(db, resident.house_number, "OldPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


def _seed_bill(db, *, house_number="P-1", mobile="9500000001", serial="MTR-P1"):
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True, house_number=house_number, mobile=mobile)
    meter = seed_meter(db, resident, serial=serial)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]
    return admin, resident, bill


# --- Initiate ------------------------------------------------------------


def test_initiate_payment_amount_is_always_from_bill(client_and_session):
    client, db = client_and_session
    _admin, resident, bill = _seed_bill(db)
    headers = _resident_auth_header(db, resident)

    resp = client.post(f"/api/v1/resident/bills/{bill.bill_id}/payments", headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount"] == str(bill.total_amount_due)
    assert body["status"] == "initiated"
    assert body["provider_name"] == "mock"


def test_initiate_payment_blocked_on_already_paid_bill(client_and_session):
    client, db = client_and_session
    _admin, resident, bill = _seed_bill(db)
    headers = _resident_auth_header(db, resident)

    # Pay it once.
    resp = client.post(f"/api/v1/resident/bills/{bill.bill_id}/payments", headers=headers)
    payment_id = resp.json()["payment_id"]
    client.post(f"/api/v1/payments/{payment_id}/mock-confirm", headers=headers, json={"simulate_success": True})

    # Second attempt should be rejected — the bill is already PAID.
    resp = client.post(f"/api/v1/resident/bills/{bill.bill_id}/payments", headers=headers)
    assert resp.status_code == 409


def test_initiate_payment_for_other_residents_bill_is_not_found(client_and_session):
    client, db = client_and_session
    _admin, _resident, bill = _seed_bill(db)
    other_resident = seed_resident(db, onboarded=True, house_number="P-2", mobile="9500000002")
    headers = _resident_auth_header(db, other_resident)

    resp = client.post(f"/api/v1/resident/bills/{bill.bill_id}/payments", headers=headers)
    assert resp.status_code == 404


# --- Confirm ---------------------------------------------------------------


def test_confirm_success_marks_bill_paid(db_session):
    db = db_session
    _admin, resident, bill = _seed_bill(db)

    from backend.providers.payment.mock_payment_provider import MockPaymentProvider

    payment_provider = MockPaymentProvider()

    payment = payment_service.initiate_payment(db, resident, bill.bill_id, payment_provider)
    confirmed = payment_service.confirm_payment(
        db, resident, payment.payment_id, payment_provider, simulate_success=True
    )

    assert confirmed.status == PaymentStatus.SUCCESS
    db.refresh(bill)
    assert bill.status == BillStatus.PAID
    assert bill.paid_at is not None


def test_confirm_failure_leaves_bill_unpaid_and_allows_fresh_retry(db_session):
    db = db_session
    _admin, resident, bill = _seed_bill(db)

    from backend.providers.payment.mock_payment_provider import MockPaymentProvider

    payment_provider = MockPaymentProvider()

    first_attempt = payment_service.initiate_payment(db, resident, bill.bill_id, payment_provider)
    failed = payment_service.confirm_payment(
        db, resident, first_attempt.payment_id, payment_provider, simulate_success=False
    )
    assert failed.status == PaymentStatus.FAILED
    assert failed.failure_reason is not None

    db.refresh(bill)
    assert bill.status == BillStatus.ISSUED  # not paid

    # A failed payment doesn't retry in place — a fresh row is created.
    second_attempt = payment_service.initiate_payment(db, resident, bill.bill_id, payment_provider)
    assert second_attempt.payment_id != first_attempt.payment_id

    succeeded = payment_service.confirm_payment(
        db, resident, second_attempt.payment_id, payment_provider, simulate_success=True
    )
    assert succeeded.status == PaymentStatus.SUCCESS
    db.refresh(bill)
    assert bill.status == BillStatus.PAID


def test_confirm_already_confirmed_payment_rejected(db_session):
    db = db_session
    _admin, resident, bill = _seed_bill(db)

    from backend.providers.payment.mock_payment_provider import MockPaymentProvider

    payment_provider = MockPaymentProvider()
    payment = payment_service.initiate_payment(db, resident, bill.bill_id, payment_provider)
    payment_service.confirm_payment(db, resident, payment.payment_id, payment_provider, simulate_success=True)

    with pytest.raises(ConflictError, match="Only an initiated payment"):
        payment_service.confirm_payment(db, resident, payment.payment_id, payment_provider, simulate_success=True)


# --- Admin mark-offline ----------------------------------------------------


def test_admin_mark_bill_paid_offline(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    _admin, _resident, bill = _seed_bill(db)

    resp = client.post(
        f"/api/v1/admin/payments/mark-offline/{bill.bill_id}",
        headers=headers,
        json={"reference_note": "Cash received at office, receipt #4521"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["provider_name"] == "offline"

    bill_resp = client.get(f"/api/v1/admin/bills/{bill.bill_id}", headers=headers)
    assert bill_resp.json()["status"] == "paid"


def test_mark_offline_blocked_on_already_paid_bill(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    _admin, _resident, bill = _seed_bill(db)

    client.post(
        f"/api/v1/admin/payments/mark-offline/{bill.bill_id}", headers=headers, json={"reference_note": "First payment"}
    )
    resp = client.post(
        f"/api/v1/admin/payments/mark-offline/{bill.bill_id}", headers=headers, json={"reference_note": "Second attempt"}
    )
    assert resp.status_code == 409


# --- Ownership / access control ------------------------------------------


def test_resident_sees_only_own_payments(client_and_session):
    client, db = client_and_session
    _admin, resident_a, bill = _seed_bill(db, house_number="P-3", mobile="9500000003", serial="MTR-P3")
    resident_b = seed_resident(db, onboarded=True, house_number="P-4", mobile="9500000004")

    headers_a = _resident_auth_header(db, resident_a)
    resp = client.post(f"/api/v1/resident/bills/{bill.bill_id}/payments", headers=headers_a)
    payment_id = resp.json()["payment_id"]

    headers_b = _resident_auth_header(db, resident_b)
    resp = client.get(f"/api/v1/resident/payments/{payment_id}", headers=headers_b)
    assert resp.status_code == 404

    resp = client.get(f"/api/v1/resident/payments/{payment_id}", headers=headers_a)
    assert resp.status_code == 200


def test_resident_cannot_access_admin_payment_endpoints(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="P-5", mobile="9500000005")
    headers = _resident_auth_header(db, resident)

    resp = client.get("/api/v1/admin/payments", headers=headers)
    assert resp.status_code == 401


def test_webhook_stub_returns_not_implemented(client_and_session):
    client, _db = client_and_session
    resp = client.post("/api/v1/payments/webhook")
    assert resp.status_code == 501
