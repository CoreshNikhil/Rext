"""End-to-end tests for the spreadsheet import pipeline via FastAPI's
TestClient: upload -> columns -> mapping -> validate -> preview -> confirm.

Covers the spec's explicit test list for imports: different column-name
formats, duplicate records within a file, missing values, plus the
house-exists-as-update / mobile-conflict / meter-conflict rules from the
approved design.
"""

from __future__ import annotations

import csv
import io

from backend.services import auth_service
from backend.tests.conftest import seed_admin, seed_resident


def _csv_bytes(rows: list[dict], headers: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _admin_auth_header(db) -> dict:
    seed_admin(db, email="owner@example.com", password="AdminPass123!")
    pair = auth_service.login_admin(db, "owner@example.com", "AdminPass123!")
    return {"Authorization": f"Bearer {pair.access_token}"}


def _run_import_flow(client, headers, csv_bytes, filename="residents.csv", mapping_override=None):
    upload_resp = client.post(
        "/api/v1/admin/imports/upload", headers=headers, files={"file": (filename, csv_bytes, "text/csv")}
    )
    assert upload_resp.status_code == 201, upload_resp.text
    job_id = upload_resp.json()["import_job_id"]

    columns_resp = client.get(f"/api/v1/admin/imports/{job_id}/columns", headers=headers)
    assert columns_resp.status_code == 200
    mapping = mapping_override or columns_resp.json()["suggested_mapping"]

    mapping_resp = client.post(f"/api/v1/admin/imports/{job_id}/mapping", headers=headers, json={"mapping": mapping})
    assert mapping_resp.status_code == 200, mapping_resp.text

    validate_resp = client.post(f"/api/v1/admin/imports/{job_id}/validate", headers=headers)
    assert validate_resp.status_code == 200, validate_resp.text
    return job_id, validate_resp.json()


def test_valid_import_creates_residents_and_meters(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [
            {"House Number": "A-1", "Name": "Alice", "Mobile": "9111111111", "Meter ID": "M-001"},
            {"House Number": "A-2", "Name": "Bob", "Mobile": "9222222222", "Meter ID": "M-002"},
        ],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["total_rows"] == 2
    assert job_body["valid_rows"] == 2
    assert job_body["error_rows"] == 0

    confirm_resp = client.post(f"/api/v1/admin/imports/{job_id}/confirm", headers=headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"

    residents_resp = client.get("/api/v1/admin/residents", headers=headers)
    house_numbers = {r["house_number"] for r in residents_resp.json()}
    assert {"A-1", "A-2"} <= house_numbers


def test_different_column_names_still_import_correctly(client_and_session):
    """The spec explicitly requires the mapping to survive different
    spreadsheet formats — this uses the "Flat No / Resident Name / Phone /
    Gas Meter" example format instead of "House Number / Name / Mobile /
    Meter ID"."""
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [{"Flat No": "B-1", "Resident Name": "Carol", "Phone": "9333333333", "Gas Meter": "M-100"}],
        headers=["Flat No", "Resident Name", "Phone", "Gas Meter"],
    )
    job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["valid_rows"] == 1
    assert job_body["error_rows"] == 0

    preview_resp = client.get(f"/api/v1/admin/imports/{job_id}/preview", headers=headers)
    row = preview_resp.json()[0]
    assert row["mapped_data"]["house_number"] == "B-1"
    assert row["mapped_data"]["mobile_number"] == "9333333333"


def test_duplicate_house_number_within_file_is_flagged(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [
            {"House Number": "C-1", "Name": "Dave", "Mobile": "9444444444", "Meter ID": "M-201"},
            {"House Number": "C-1", "Name": "Dave2", "Mobile": "9555555555", "Meter ID": "M-202"},
        ],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 1
    assert job_body["valid_rows"] == 1


def test_duplicate_mobile_within_file_is_flagged(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [
            {"House Number": "D-1", "Name": "Eve", "Mobile": "9666666666", "Meter ID": "M-301"},
            {"House Number": "D-2", "Name": "Eve2", "Mobile": "9666666666", "Meter ID": "M-302"},
        ],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 1


def test_duplicate_meter_within_file_is_flagged(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [
            {"House Number": "E-1", "Name": "Frank", "Mobile": "9777777777", "Meter ID": "SHARED"},
            {"House Number": "E-2", "Name": "Grace", "Mobile": "9788888888", "Meter ID": "SHARED"},
        ],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 1


def test_missing_required_value_is_flagged(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [{"House Number": "F-1", "Name": "", "Mobile": "9899999999", "Meter ID": "M-401"}],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 1
    assert job_body["valid_rows"] == 0


def test_invalid_mobile_and_house_format_are_flagged(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [
            {"House Number": "G@1", "Name": "Bad House", "Mobile": "9111111112", "Meter ID": "M-501"},
            {"House Number": "G-2", "Name": "Bad Mobile", "Mobile": "1234567890", "Meter ID": "M-502"},
        ],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 2


def test_existing_house_number_is_update_warning_not_error(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    existing = seed_resident(db, house_number="H-1", mobile="9000000001")

    csv_bytes = _csv_bytes(
        [{"House Number": "H-1", "Name": "Updated Name", "Mobile": "9000000001", "Meter ID": "M-601"}],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 0
    assert job_body["valid_rows"] == 1  # warnings count as importable, not errors

    preview_resp = client.get(f"/api/v1/admin/imports/{job_id}/preview", headers=headers)
    row = preview_resp.json()[0]
    assert row["validation_status"] == "warning"
    assert row["action"] == "update"
    assert row["resident_id"] == existing.resident_id

    confirm_resp = client.post(f"/api/v1/admin/imports/{job_id}/confirm", headers=headers)
    assert confirm_resp.status_code == 200

    updated_resp = client.get(f"/api/v1/admin/residents/{existing.resident_id}", headers=headers)
    assert updated_resp.json()["full_name"] == "Updated Name"


def test_mobile_conflict_with_different_house_is_error(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    seed_resident(db, house_number="I-1", mobile="9000000002")

    csv_bytes = _csv_bytes(
        [{"House Number": "I-2", "Name": "Conflict", "Mobile": "9000000002", "Meter ID": "M-701"}],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 1


def test_meter_conflict_with_different_resident_is_error(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)
    resident = seed_resident(db, house_number="J-1", mobile="9000000003")

    assign_resp = client.post(
        f"/api/v1/admin/residents/{resident.resident_id}/meters",
        headers=headers,
        json={"meter_serial_number": "EXISTING-METER"},
    )
    assert assign_resp.status_code == 201

    csv_bytes = _csv_bytes(
        [{"House Number": "J-2", "Name": "Conflict", "Mobile": "9000000004", "Meter ID": "EXISTING-METER"}],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    _job_id, job_body = _run_import_flow(client, headers, csv_bytes)
    assert job_body["error_rows"] == 1


def test_import_history_lists_jobs(client_and_session):
    client, db = client_and_session
    headers = _admin_auth_header(db)

    csv_bytes = _csv_bytes(
        [{"House Number": "K-1", "Name": "Kim", "Mobile": "9000000005", "Meter ID": "M-801"}],
        headers=["House Number", "Name", "Mobile", "Meter ID"],
    )
    job_id, _job_body = _run_import_flow(client, headers, csv_bytes)

    history_resp = client.get("/api/v1/admin/imports", headers=headers)
    assert history_resp.status_code == 200
    job_ids = {j["import_job_id"] for j in history_resp.json()}
    assert job_id in job_ids


def test_resident_token_cannot_access_import_endpoints(client_and_session):
    client, db = client_and_session
    seed_resident(db, onboarded=True, house_number="L-1", mobile="9000000006")
    pair = auth_service.login_resident(db, "L-1", "OldPass123!")

    resp = client.get("/api/v1/admin/imports", headers={"Authorization": f"Bearer {pair.access_token}"})
    assert resp.status_code == 401
