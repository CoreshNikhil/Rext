"""Phase 8 audit-log-coverage sweep: for every action the spec explicitly
requires to be audit-logged (gas price changes, deadline changes, reading
submit/approve, bill generated, payment completed, fine added, resident
data changes, spreadsheet imported, system-config changes), assert a real
AuditLog row is written — not just that the code path runs.

Every prior test file exercises these actions already, but none of them
ever queried the AuditLog table, so a missing audit_service.record() call
could have shipped silently. This file closes that blind spot; the
`update_own_email` fix in resident_service.py (found by this sweep) is
covered by the first test below.
"""

from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal

from PIL import Image

from backend.db.models.audit_log import AuditLog
from backend.db.models.enums import ActorType, BillingPeriodStatus
from backend.jobs import definitions
from backend.schemas.billing import BillingPeriodUpdateRequest
from backend.services import (
    auth_service,
    billing_service,
    meter_reading_service,
    payment_service,
    resident_service,
    system_config_service,
)
from backend.tests.conftest import (
    FakeVisionProvider,
    accepted_vision_response,
    seed_admin,
    seed_billing_period,
    seed_finalized_reading,
    seed_meter,
    seed_resident,
    seed_system_config,
)
from backend.tests.test_import_service import _admin_auth_header as _import_admin_auth_header
from backend.tests.test_import_service import _csv_bytes, _run_import_flow


def _actions_for(db, *, action: str, entity_type: str) -> list[AuditLog]:
    return db.query(AuditLog).filter(AuditLog.action == action, AuditLog.entity_type == entity_type).all()


def _tiny_valid_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(120, 120, 120)).save(buf, format="JPEG")
    return buf.getvalue()


# --- Resident data changes -------------------------------------------------


def test_resident_self_email_update_is_audit_logged(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="AL-1", mobile="9500000001")
    pair = auth_service.login_resident(db, "AL-1", "OldPass123!")
    headers = {"Authorization": f"Bearer {pair.access_token}"}

    resp = client.patch("/api/v1/resident/me", headers=headers, json={"email": "new@example.com"})
    assert resp.status_code == 200

    rows = _actions_for(db, action="resident.update", entity_type="resident")
    matching = [r for r in rows if r.entity_id == resident.resident_id and r.actor_type == ActorType.RESIDENT]
    assert len(matching) == 1
    assert matching[0].after_state == {"email": "new@example.com"}


def test_admin_resident_update_is_audit_logged(db_session):
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True, house_number="AL-2", mobile="9500000002")

    from backend.schemas.resident import ResidentUpdateRequest

    resident_service.update_resident(db, admin, resident.resident_id, ResidentUpdateRequest(full_name="New Name"))

    rows = _actions_for(db, action="resident.update", entity_type="resident")
    matching = [r for r in rows if r.entity_id == resident.resident_id and r.actor_type == ActorType.ADMIN]
    assert len(matching) == 1


# --- Gas price + deadline changes (BillingPeriod) ---------------------------


def test_billing_period_rate_and_deadline_change_is_audit_logged(db_session):
    db = db_session
    admin = seed_admin(db)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.DRAFT)

    new_deadline = period.reading_window_end + timedelta(days=5)
    billing_service.update_billing_period(
        db,
        admin,
        period.billing_period_id,
        BillingPeriodUpdateRequest(rate_per_unit=Decimal("60.00"), reading_window_end=new_deadline),
    )

    rows = _actions_for(db, action="billing_period.update", entity_type="billing_period")
    matching = [r for r in rows if r.entity_id == period.billing_period_id]
    assert len(matching) == 1
    assert matching[0].after_state["rate_per_unit"] == "60.00"
    assert "reading_window_end" in matching[0].after_state


# --- System-config changes (also covers gas price / deadline defaults) -----


def test_system_config_change_is_audit_logged(db_session):
    db = db_session
    admin = seed_admin(db)
    seed_system_config(db)

    system_config_service.update_config(db, admin, "default_rate_per_unit", "65.00")

    rows = _actions_for(db, action="system_config.update", entity_type="system_configuration")
    assert any(r.actor_type == ActorType.ADMIN for r in rows)


# --- Reading submit / approve -----------------------------------------------


def test_reading_submit_and_confirm_are_audit_logged(db_session):
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True, house_number="AL-3", mobile="9500000003")
    seed_meter(db, resident, serial="MTR-AL3")
    seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.OPEN_FOR_READINGS)

    provider = FakeVisionProvider(accepted_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    assert _actions_for(db, action="reading.submit", entity_type="meter_reading")

    meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)
    rows = _actions_for(db, action="reading.confirm", entity_type="meter_reading")
    assert any(r.entity_id == reading.meter_reading_id for r in rows)


# --- Bill generated ----------------------------------------------------------


def test_bill_generation_is_audit_logged(db_session):
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True, house_number="AL-4", mobile="9500000004")
    meter = seed_meter(db, resident, serial="MTR-AL4")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)

    rows = _actions_for(db, action="billing_period.generate_bills", entity_type="billing_period")
    assert any(r.entity_id == period.billing_period_id for r in rows)


# --- Payment completed --------------------------------------------------------


def test_payment_completion_is_audit_logged(db_session):
    db = db_session
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True, house_number="AL-5", mobile="9500000005")
    meter = seed_meter(db, resident, serial="MTR-AL5")
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)
    billing_service.generate_bills_for_period(db, admin, period.billing_period_id)
    bill = billing_service.list_bills_admin(db, billing_period_id=period.billing_period_id)[0]

    from backend.providers.payment.mock_payment_provider import MockPaymentProvider

    provider = MockPaymentProvider()
    payment = payment_service.initiate_payment(db, resident, bill.bill_id, provider)
    payment_service.confirm_payment(db, resident, payment.payment_id, provider, simulate_success=True)

    rows = _actions_for(db, action="payment.confirm", entity_type="payment")
    matching = [r for r in rows if r.entity_id == payment.payment_id]
    assert len(matching) == 1
    assert matching[0].after_state == {"status": "success"}


# --- Fine added (scheduled job) ----------------------------------------------


def test_fine_accrual_is_audit_logged(jobs_db):
    db = jobs_db
    admin = seed_admin(db)
    resident = seed_resident(db, onboarded=True)
    meter = seed_meter(db, resident)
    period = seed_billing_period(db, admin.community_id, status=BillingPeriodStatus.READINGS_CLOSED)
    seed_finalized_reading(db, resident, meter, period)

    billing_service.system_generate_bills_for_period(db, period.billing_period_id)
    from backend.db.models.bill import Bill
    from backend.db.models.enums import BillStatus

    bill = db.query(Bill).filter(Bill.billing_period_id == period.billing_period_id).first()
    bill.status = BillStatus.OVERDUE
    bill.due_date = date.today() - timedelta(days=1)
    db.commit()

    definitions.fine_accrual()

    rows = _actions_for(db, action="bill.fine_accrued", entity_type="bill")
    assert any(r.entity_id == bill.bill_id and r.actor_type == ActorType.SYSTEM for r in rows)


# --- Spreadsheet imported ------------------------------------------------


def test_spreadsheet_import_is_audit_logged(client_and_session):
    client, db = client_and_session
    headers = _import_admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [{"House Number": "AL-6", "Name": "Audit Test", "Mobile": "9500000006", "Meter ID": "MTR-AL6"}],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    job_id, _ = _run_import_flow(client, headers, csv_bytes)

    confirm_resp = client.post(f"/api/v1/admin/imports/{job_id}/confirm", headers=headers)
    assert confirm_resp.status_code == 200

    rows = _actions_for(db, action="import.confirm", entity_type="import_job")
    assert any(r.entity_id == job_id for r in rows)
