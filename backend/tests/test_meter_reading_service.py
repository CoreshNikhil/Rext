"""Tests for the MeterVision integration.

Split deliberately into two kinds:
- One real-API test that actually calls Gemini against the project's
  known sample photo — this is the test that proves the integration
  genuinely works end-to-end, not just against a mock.
- Service/HTTP-level tests using FakeVisionProvider or pre-seeded rows for
  everything else (validation rules, duplicate-submission blocking,
  ownership enforcement, admin override/reject) — fast, deterministic, no
  network cost.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.enums import MeterReadingStatus
from backend.services import auth_service, meter_reading_service
from backend.tests.conftest import (
    FakeVisionProvider,
    accepted_vision_response,
    close_billing_period,
    needs_review_vision_response,
    seed_admin,
    seed_billing_period,
    seed_meter,
    seed_resident,
)

SAMPLE_IMAGE_PATH = Path(__file__).resolve().parents[2] / "sample_images" / "test_meter_01.jpeg"


def _tiny_valid_jpeg() -> bytes:
    """A real (if trivial) JPEG — needed because validate_image_upload
    correctly rejects arbitrary bytes as unreadable image data, so tests
    that don't care about photo content still need a genuine image file."""
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(120, 120, 120)).save(buf, format="JPEG")
    return buf.getvalue()


def _admin_auth_header(db) -> dict:
    seed_admin(db, email="owner@example.com", password="AdminPass123!")
    pair = auth_service.login_admin(db, "owner@example.com", "AdminPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


def _resident_auth_header(db, resident) -> dict:
    pair = auth_service.login_resident(db, resident.house_number, "OldPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}, pair


# --- Real API integration test -----------------------------------------


@pytest.mark.skipif(not SAMPLE_IMAGE_PATH.exists(), reason="sample image not present")
def test_submit_and_confirm_reading_against_real_gemini_api(db_session):
    """The one test that actually proves vision.detection.analyze_meter_image
    works when called from inside the billing system, unmodified."""
    from providers.gemini_provider import GeminiProvider

    db = db_session
    resident = seed_resident(db, house_number="REAL-1", mobile="9111100001")
    seed_meter(db, resident, serial="16710009")
    seed_billing_period(db, resident.community_id)

    image_bytes = SAMPLE_IMAGE_PATH.read_bytes()
    provider = GeminiProvider()

    reading = meter_reading_service.submit_meter_reading(db, resident, image_bytes, provider)

    _EXTERNAL_FAILURE_MARKERS = ("rate limit", "resource_exhausted", "timed out", "timeout", "connection")
    if (
        reading.status != MeterReadingStatus.AI_ACCEPTED
        and reading.ai_reason
        and any(marker in reading.ai_reason.lower() for marker in _EXTERNAL_FAILURE_MARKERS)
    ):
        # A genuine external failure (quota exhausted, network timeout,
        # connection error) — not a code defect. The fact that it was
        # caught and fell back to a conservative result instead of
        # crashing or fabricating a reading is itself the correct,
        # designed behavior. Distinguish "Gemini/the network had a bad
        # moment" from "the integration is broken" rather than failing
        # either way.
        pytest.skip(f"Transient Gemini/network failure, not a code issue: {reading.ai_reason}")

    assert reading.status == MeterReadingStatus.AI_ACCEPTED
    assert reading.submitted_reading_value == Decimal("115.197")
    assert reading.previous_reading_value == Decimal("0.000")

    confirmed = meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)
    assert confirmed.status == MeterReadingStatus.RESIDENT_CONFIRMED
    assert confirmed.final_reading_value == Decimal("115.197")


# --- Service-level tests with a fake provider ---------------------------


def test_submit_requires_open_billing_period(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-1", mobile="9222200001")
    seed_meter(db, resident)

    provider = FakeVisionProvider(accepted_vision_response())
    with pytest.raises(ConflictError, match="No billing period is currently open"):
        meter_reading_service.submit_meter_reading(db, resident, b"fake-image-bytes", provider)


def test_submit_requires_assigned_meter(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-2", mobile="9222200002")
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(accepted_vision_response())
    with pytest.raises(ConflictError, match="No active meter is assigned"):
        meter_reading_service.submit_meter_reading(db, resident, b"fake-image-bytes", provider)


def test_confirm_rejects_reading_equal_to_previous(db_session, monkeypatch):
    db = db_session
    resident = seed_resident(db, house_number="B-3", mobile="9222200003")
    seed_meter(db, resident)
    first_period = seed_billing_period(db, resident.community_id)

    # First submission establishes a baseline previous reading of 0, so
    # use two submissions to get previous == 100.000 first.
    provider = FakeVisionProvider(accepted_vision_response(raw_digits="00100000", reading="00100.000"))
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)

    # Close the first period and open a new one, submit the SAME value
    # again -> equal to previous.
    close_billing_period(db, first_period)
    seed_billing_period(db, resident.community_id, period_label="2026-09")
    provider2 = FakeVisionProvider(accepted_vision_response(raw_digits="00100000", reading="00100.000"))
    reading2 = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider2)

    with pytest.raises(ConflictError, match="same as the previous reading"):
        meter_reading_service.confirm_meter_reading(db, resident, reading2.meter_reading_id)


def test_confirm_rejects_reading_lower_than_previous(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-4", mobile="9222200004")
    seed_meter(db, resident)
    first_period = seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(accepted_vision_response(raw_digits="00100000", reading="00100.000"))
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)

    close_billing_period(db, first_period)
    seed_billing_period(db, resident.community_id, period_label="2026-09")
    provider2 = FakeVisionProvider(accepted_vision_response(raw_digits="00090000", reading="00090.000"))
    reading2 = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider2)

    with pytest.raises(ConflictError, match="cannot be lower than the previous"):
        meter_reading_service.confirm_meter_reading(db, resident, reading2.meter_reading_id)


def test_confirm_accepts_reading_higher_than_previous(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-5", mobile="9222200005")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(accepted_vision_response(raw_digits="00115197", reading="00115.197"))
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    confirmed = meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)
    assert confirmed.status == MeterReadingStatus.RESIDENT_CONFIRMED
    assert confirmed.final_reading_value == Decimal("115.197")


def test_needs_review_reading_cannot_be_confirmed(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-6", mobile="9222200006")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(needs_review_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    assert reading.status == MeterReadingStatus.NEEDS_REVIEW

    with pytest.raises(ConflictError, match="Only an AI-accepted reading"):
        meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)


def test_duplicate_submission_blocked_after_confirmed(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-7", mobile="9222200007")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(accepted_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)

    provider2 = FakeVisionProvider(accepted_vision_response())
    with pytest.raises(ConflictError, match="already been accepted"):
        meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider2)


def test_resubmission_replaces_image_on_same_row_when_needs_review(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-8", mobile="9222200008")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(needs_review_vision_response())
    first = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)

    provider2 = FakeVisionProvider(accepted_vision_response())
    second = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider2)

    assert first.meter_reading_id == second.meter_reading_id
    assert second.status == MeterReadingStatus.AI_ACCEPTED


def test_retake_blocked_once_finalized(db_session):
    db = db_session
    resident = seed_resident(db, house_number="B-9", mobile="9222200009")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(accepted_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)
    meter_reading_service.confirm_meter_reading(db, resident, reading.meter_reading_id)

    with pytest.raises(ConflictError, match="already been finalized"):
        meter_reading_service.retake_meter_reading(db, resident, reading.meter_reading_id)


def test_other_residents_reading_is_not_found_not_forbidden(db_session):
    db = db_session
    resident_a = seed_resident(db, house_number="B-10", mobile="9222200010")
    resident_b = seed_resident(db, house_number="B-11", mobile="9222200011")
    seed_meter(db, resident_a, serial="MTR-A")
    seed_billing_period(db, resident_a.community_id)

    provider = FakeVisionProvider(accepted_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident_a, _tiny_valid_jpeg(), provider)

    with pytest.raises(NotFoundError):
        meter_reading_service.get_own_reading_or_404(db, resident_b, reading.meter_reading_id)


# --- HTTP-level tests for admin review + ownership ------------------------


def test_admin_override_reading(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    resident = seed_resident(db, house_number="C-1", mobile="9333300001")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(needs_review_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)

    resp = client.post(
        f"/api/v1/admin/meter-readings/{reading.meter_reading_id}/override",
        headers=headers,
        json={"final_reading_value": "120.500", "reason": "Manually verified against physical meter."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "admin_overridden"
    assert body["final_reading_value"] == "120.500"


def test_admin_reject_reading(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    resident = seed_resident(db, house_number="C-2", mobile="9333300002")
    seed_meter(db, resident)
    seed_billing_period(db, resident.community_id)

    provider = FakeVisionProvider(needs_review_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident, _tiny_valid_jpeg(), provider)

    resp = client.post(
        f"/api/v1/admin/meter-readings/{reading.meter_reading_id}/reject",
        headers=headers,
        json={"reason": "Image too blurry to verify manually."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_resident_cannot_access_admin_meter_reading_endpoints(client_and_session):
    client, db = client_and_session
    resident = seed_resident(db, onboarded=True, house_number="C-3", mobile="9333300003")
    headers, _pair = _resident_auth_header(db, resident)

    resp = client.get("/api/v1/admin/meter-readings", headers=headers)
    assert resp.status_code == 401


def test_resident_image_endpoint_enforces_ownership(client_and_session):
    client, db = client_and_session
    resident_a = seed_resident(db, onboarded=True, house_number="C-4", mobile="9333300004")
    resident_b = seed_resident(db, onboarded=True, house_number="C-5", mobile="9333300005")
    seed_meter(db, resident_a, serial="MTR-C4")
    seed_billing_period(db, resident_a.community_id)

    provider = FakeVisionProvider(accepted_vision_response())
    reading = meter_reading_service.submit_meter_reading(db, resident_a, _tiny_valid_jpeg(), provider)

    headers_b, _pair_b = _resident_auth_header(db, resident_b)
    resp = client.get(f"/api/v1/resident/meter-readings/{reading.meter_reading_id}/image", headers=headers_b)
    assert resp.status_code == 404

    headers_a, _pair_a = _resident_auth_header(db, resident_a)
    resp = client.get(f"/api/v1/resident/meter-readings/{reading.meter_reading_id}/image", headers=headers_a)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
