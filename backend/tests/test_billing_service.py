"""Tests for the billing engine: BillingPeriod lifecycle, Bill generation
(consumption/amount computed server-side), idempotency, and admin bill
actions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.core.domain_exceptions import ConflictError
from backend.db.models.enums import BillingPeriodStatus, BillStatus
from backend.services import auth_service, billing_service
from backend.tests.conftest import (
    close_billing_period,
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


# --- BillingPeriod CRUD + lifecycle --------------------------------------


def test_create_billing_period(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    resp = client.post(
        "/api/v1/admin/billing-periods",
        headers=headers,
        json={
            "period_label": "2026-08",
            "reading_window_start": "2026-08-01",
            "reading_window_end": "2026-08-15",
            "payment_due_date": "2026-08-25",
            "rate_per_unit": "50.00",
            "fine_per_day_overdue": "10.00",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "draft"


def test_create_billing_period_duplicate_label_rejected(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    payload = {
        "period_label": "2026-08",
        "reading_window_start": "2026-08-01",
        "reading_window_end": "2026-08-15",
        "payment_due_date": "2026-08-25",
        "rate_per_unit": "50.00",
        "fine_per_day_overdue": "10.00",
    }
    client.post("/api/v1/admin/billing-periods", headers=headers, json=payload)
    resp = client.post("/api/v1/admin/billing-periods", headers=headers, json=payload)
    assert resp.status_code == 409


def test_update_billing_period_rejected_once_not_draft(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="second@example.com", password="pw")  # unused, ensures community exists
    period = seed_billing_period(db, admin.community_id)  # status defaults to OPEN_FOR_READINGS

    resp = client.patch(
        f"/api/v1/admin/billing-periods/{period.billing_period_id}", headers=headers, json={"rate_per_unit": "60.00"}
    )
    assert resp.status_code == 409


def test_lifecycle_transitions_full_sequence(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="lifecycle@example.com", password="pw")
    resident = seed_resident(db, house_number="L-1", mobile="9100000001")
    meter = seed_meter(db, resident, serial="MTR-L1")

    create_resp = client.post(
        "/api/v1/admin/billing-periods",
        headers=headers,
        json={
            "period_label": "2026-09",
            "reading_window_start": "2026-09-01",
            "reading_window_end": "2026-09-15",
            "payment_due_date": "2026-09-25",
            "rate_per_unit": "50.00",
            "fine_per_day_overdue": "10.00",
        },
    )
    period_id = create_resp.json()["billing_period_id"]

    open_resp = client.post(f"/api/v1/admin/billing-periods/{period_id}/open", headers=headers)
    assert open_resp.status_code == 200
    assert open_resp.json()["status"] == "open_for_readings"

    from backend.db.models.billing_period import BillingPeriod

    period = db.get(BillingPeriod, period_id)
    seed_finalized_reading(db, resident, meter, period)

    close_resp = client.post(f"/api/v1/admin/billing-periods/{period_id}/close-readings", headers=headers)
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "readings_closed"

    generate_resp = client.post(f"/api/v1/admin/billing-periods/{period_id}/generate-bills", headers=headers)
    assert generate_resp.status_code == 200
    assert generate_resp.json()["bills_created"] == 1

    period_after = client.get(f"/api/v1/admin/billing-periods/{period_id}", headers=headers)
    assert period_after.json()["status"] == "billed"

    final_close_resp = client.post(f"/api/v1/admin/billing-periods/{period_id}/close", headers=headers)
    assert final_close_resp.status_code == 200
    assert final_close_resp.json()["status"] == "closed"
    assert final_close_resp.json()["closed_at"] is not None


def test_transition_rejected_in_wrong_state(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="wrongstate@example.com", password="pw")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.DRAFT)

    # DRAFT can't skip straight to close-readings.
    resp = client.post(f"/api/v1/admin/billing-periods/{period.billing_period_id}/close-readings", headers=headers)
    assert resp.status_code == 409


# --- Bill generation: consumption/amount math + idempotency ---------------


def test_generate_bills_computes_correct_consumption_and_amount(db_session):
    """Matches the exact worked example from the spec: 100.000 -> 115.197
    at Rs 50/m3 -> 15.197 m3 -> Rs 759.85."""
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, house_number="M-1", mobile="9200000001")
    meter = seed_meter(db, resident, serial="MTR-M1")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period, previous=Decimal("100.000"), final=Decimal("115.197"))

    result = billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    assert result["bills_created"] == 1

    bills = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)
    assert len(bills) == 1
    bill = bills[0]
    assert bill.consumption_units == Decimal("15.197")
    assert bill.amount_due == Decimal("759.85")
    assert bill.total_amount_due == Decimal("759.85")
    assert bill.fine_amount == Decimal("0.00")
    assert bill.status == BillStatus.ISSUED


def test_generate_bills_is_idempotent(db_session):
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, house_number="M-2", mobile="9200000002")
    meter = seed_meter(db, resident, serial="MTR-M2")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    first = billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    assert first["bills_created"] == 1

    second = billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    assert second["bills_created"] == 0

    bills = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)
    assert len(bills) == 1  # never double-billed


def test_generate_bills_skips_residents_without_finalized_reading(db_session):
    db = db_session
    admin = seed_admin(db)
    resident_with_reading = seed_resident(db, house_number="M-3", mobile="9200000003")
    resident_without_reading = seed_resident(db, house_number="M-4", mobile="9200000004")
    meter = seed_meter(db, resident_with_reading, serial="MTR-M3")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident_with_reading, meter, period)

    result = billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    assert result["bills_created"] == 1

    bills = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)
    assert {b.resident_id for b in bills} == {resident_with_reading.resident_id}


def test_generate_bills_incremental_after_late_finalization(db_session):
    """BILLED means generation has run at least once, not that everyone is
    billed — a late admin override should still pick up a bill on rerun."""
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, house_number="M-5", mobile="9200000005")
    meter = seed_meter(db, resident, serial="MTR-M5")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)

    first = billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    assert first["bills_created"] == 0

    seed_finalized_reading(db, resident, meter, period, admin_overridden=True)

    second = billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    assert second["bills_created"] == 1


def test_generate_bills_requires_readings_closed(db_session):
    db = db_session
    admin = seed_admin(db)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.OPEN_FOR_READINGS)

    with pytest.raises(ConflictError, match="Readings must be closed"):
        billing_service.generate_bills_for_period(db, admin, period.billing_period_id)


# --- Waive / cancel ------------------------------------------------------


def test_waive_bill(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="waiver@example.com", password="pw")
    resident = seed_resident(db, house_number="N-1", mobile="9300000001")
    meter = seed_meter(db, resident, serial="MTR-N1")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]

    resp = client.post(
        f"/api/v1/admin/bills/{bill.bill_id}/waive", headers=headers, json={"reason": "Resident disputed the reading."}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "waived"


def test_cancel_bill(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    admin = seed_admin(db, email="canceller@example.com", password="pw")
    resident = seed_resident(db, house_number="N-2", mobile="9300000002")
    meter = seed_meter(db, resident, serial="MTR-N2")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]

    resp = client.post(
        f"/api/v1/admin/bills/{bill.bill_id}/cancel", headers=headers, json={"reason": "Duplicate bill generated in error."}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_waive_already_waived_bill_rejected(db_session):
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, house_number="N-3", mobile="9300000003")
    meter = seed_meter(db, resident, serial="MTR-N3")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]

    billing_service.waive_bill(db, admin, bill.bill_id, "First waive.")
    with pytest.raises(ConflictError):
        billing_service.waive_bill(db, admin, bill.bill_id, "Second waive attempt.")


# --- Ownership / access control ------------------------------------------


def test_resident_sees_only_own_bills(client_and_session):
    client, db = client_and_session
    admin = seed_admin(db)
    resident_a = seed_resident(db, onboarded=True, house_number="O-1", mobile="9400000001")
    resident_b = seed_resident(db, onboarded=True, house_number="O-2", mobile="9400000002")
    meter_a = seed_meter(db, resident_a, serial="MTR-O1")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident_a, meter_a, period)
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]

    headers_b = _resident_auth_header(db, resident_b)
    resp = client.get(f"/api/v1/resident/bills/{bill.bill_id}", headers=headers_b)
    assert resp.status_code == 404

    headers_a = _resident_auth_header(db, resident_a)
    resp = client.get(f"/api/v1/resident/bills/{bill.bill_id}", headers=headers_a)
    assert resp.status_code == 200


def test_resident_cannot_access_admin_billing_endpoints(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="O-3", mobile="9400000003")
    headers = _resident_auth_header(db, resident)

    resp = client.get("/api/v1/admin/billing-periods", headers=headers)
    assert resp.status_code == 401

    resp = client.get("/api/v1/admin/bills", headers=headers)
    assert resp.status_code == 401
