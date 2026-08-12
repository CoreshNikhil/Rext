"""Thin httpx wrapper for every backend call admin_web makes — mirrors the
FastAPI routes 1:1, no business logic here (that all lives in the
backend). Auth tokens are read/written directly on st.session_state,
shared with auth.py, since Streamlit's session state is this process's
only persistence.
"""

from __future__ import annotations

import httpx
import streamlit as st

from config import BACKEND_URL


class ApiError(Exception):
    def __init__(self, status_code: int, detail, error_type: str = "error"):
        self.status_code = status_code
        self.detail = detail
        self.error_type = error_type
        super().__init__(str(detail))


def _headers() -> dict:
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _refresh_access_token() -> bool:
    refresh_token = st.session_state.get("refresh_token")
    if not refresh_token:
        return False
    resp = httpx.post(f"{BACKEND_URL}/api/v1/auth/refresh", json={"refresh_token": refresh_token}, timeout=10)
    if resp.status_code != 200:
        return False
    body = resp.json()
    st.session_state["access_token"] = body["access_token"]
    st.session_state["refresh_token"] = body["refresh_token"]
    return True


def _raise_for_error(resp: httpx.Response) -> None:
    body: dict = {}
    try:
        body = resp.json()
    except ValueError:
        pass
    raise ApiError(
        status_code=resp.status_code,
        detail=body.get("detail", resp.text or f"HTTP {resp.status_code}"),
        error_type=body.get("error_type", "error"),
    )


def request(method: str, path: str, *, retry_on_401: bool = True, **kwargs) -> httpx.Response:
    url = f"{BACKEND_URL}{path}"
    resp = httpx.request(method, url, headers=_headers(), timeout=30, **kwargs)

    if resp.status_code == 401 and retry_on_401 and st.session_state.get("refresh_token") and _refresh_access_token():
        resp = httpx.request(method, url, headers=_headers(), timeout=30, **kwargs)

    if resp.status_code == 401:
        # Refresh didn't happen or didn't help — the session is genuinely
        # gone. Clear it so the next page load bounces back to login
        # instead of repeatedly hitting a dead token.
        st.session_state.pop("access_token", None)
        st.session_state.pop("refresh_token", None)

    if resp.status_code >= 400:
        _raise_for_error(resp)
    return resp


def get(path: str, **kwargs) -> httpx.Response:
    return request("GET", path, **kwargs)


def post(path: str, **kwargs) -> httpx.Response:
    return request("POST", path, **kwargs)


def patch(path: str, **kwargs) -> httpx.Response:
    return request("PATCH", path, **kwargs)


def delete(path: str, **kwargs) -> httpx.Response:
    return request("DELETE", path, **kwargs)


# --- Auth --------------------------------------------------------------


def login_admin(email: str, password: str) -> dict:
    resp = httpx.post(f"{BACKEND_URL}/api/v1/admin/auth/login", json={"email": email, "password": password}, timeout=10)
    if resp.status_code >= 400:
        _raise_for_error(resp)
    return resp.json()


def logout() -> None:
    refresh_token = st.session_state.get("refresh_token")
    if not refresh_token:
        return
    try:
        httpx.post(f"{BACKEND_URL}/api/v1/auth/logout", json={"refresh_token": refresh_token}, timeout=10)
    except httpx.HTTPError:
        pass  # best-effort — the local session is cleared by the caller regardless


# --- Dashboard -----------------------------------------------------------


def get_dashboard_overview() -> dict:
    return get("/api/v1/admin/dashboard/overview").json()


def get_dashboard_collections() -> list:
    return get("/api/v1/admin/dashboard/collections").json()


# --- Residents -------------------------------------------------------------


def list_residents(active_only: bool = False, search: str | None = None) -> list:
    params: dict = {"active_only": active_only}
    if search:
        params["search"] = search
    return get("/api/v1/admin/residents", params=params).json()


def get_resident(resident_id: int) -> dict:
    return get(f"/api/v1/admin/residents/{resident_id}").json()


def create_resident(payload: dict) -> dict:
    return post("/api/v1/admin/residents", json=payload).json()


def update_resident(resident_id: int, payload: dict) -> dict:
    return patch(f"/api/v1/admin/residents/{resident_id}", json=payload).json()


def deactivate_resident(resident_id: int) -> dict:
    return delete(f"/api/v1/admin/residents/{resident_id}").json()


def reset_resident_password(resident_id: int) -> None:
    post(f"/api/v1/admin/residents/{resident_id}/reset-password")


def assign_meter(resident_id: int, meter_serial_number: str, install_date=None) -> dict:
    payload: dict = {"meter_serial_number": meter_serial_number}
    if install_date:
        payload["install_date"] = str(install_date)
    return post(f"/api/v1/admin/residents/{resident_id}/meters", json=payload).json()


# --- Meter readings --------------------------------------------------------


def list_readings_admin(billing_period_id: int | None = None, status: str | None = None, resident_id: int | None = None) -> list:
    params: dict = {}
    if billing_period_id is not None:
        params["billing_period_id"] = billing_period_id
    if status:
        params["status"] = status
    if resident_id is not None:
        params["resident_id"] = resident_id
    return get("/api/v1/admin/meter-readings", params=params).json()


def get_reading_admin(reading_id: int) -> dict:
    return get(f"/api/v1/admin/meter-readings/{reading_id}").json()


def get_reading_image_admin(reading_id: int) -> bytes:
    return get(f"/api/v1/admin/meter-readings/{reading_id}/image").content


def override_reading(reading_id: int, final_reading_value, reason: str) -> dict:
    payload = {"final_reading_value": str(final_reading_value), "reason": reason}
    return post(f"/api/v1/admin/meter-readings/{reading_id}/override", json=payload).json()


def reject_reading(reading_id: int, reason: str) -> dict:
    return post(f"/api/v1/admin/meter-readings/{reading_id}/reject", json={"reason": reason}).json()


# --- Billing periods & bills -------------------------------------------


def list_billing_periods() -> list:
    return get("/api/v1/admin/billing-periods").json()


def create_billing_period(payload: dict) -> dict:
    return post("/api/v1/admin/billing-periods", json=payload).json()


def update_billing_period(period_id: int, payload: dict) -> dict:
    return patch(f"/api/v1/admin/billing-periods/{period_id}", json=payload).json()


def open_billing_period(period_id: int) -> dict:
    return post(f"/api/v1/admin/billing-periods/{period_id}/open").json()


def close_readings(period_id: int) -> dict:
    return post(f"/api/v1/admin/billing-periods/{period_id}/close-readings").json()


def generate_bills(period_id: int) -> dict:
    return post(f"/api/v1/admin/billing-periods/{period_id}/generate-bills").json()


def close_billing_period(period_id: int) -> dict:
    return post(f"/api/v1/admin/billing-periods/{period_id}/close").json()


def list_bills(billing_period_id: int | None = None, status: str | None = None, resident_id: int | None = None) -> list:
    params: dict = {}
    if billing_period_id is not None:
        params["billing_period_id"] = billing_period_id
    if status:
        params["status"] = status
    if resident_id is not None:
        params["resident_id"] = resident_id
    return get("/api/v1/admin/bills", params=params).json()


def waive_bill(bill_id: int, reason: str) -> dict:
    return post(f"/api/v1/admin/bills/{bill_id}/waive", json={"reason": reason}).json()


def cancel_bill(bill_id: int, reason: str) -> dict:
    return post(f"/api/v1/admin/bills/{bill_id}/cancel", json={"reason": reason}).json()


# --- Payments --------------------------------------------------------------


def list_payments_admin(bill_id: int | None = None, status: str | None = None, resident_id: int | None = None) -> list:
    params: dict = {}
    if bill_id is not None:
        params["bill_id"] = bill_id
    if status:
        params["status"] = status
    if resident_id is not None:
        params["resident_id"] = resident_id
    return get("/api/v1/admin/payments", params=params).json()


def mark_bill_paid_offline(bill_id: int, reference_note: str) -> dict:
    return post(f"/api/v1/admin/payments/mark-offline/{bill_id}", json={"reference_note": reference_note}).json()


# --- Notifications -----------------------------------------------------


def list_admin_notifications() -> list:
    return get("/api/v1/admin/notifications").json()


def mark_admin_notification_read(notification_id: int) -> dict:
    return post(f"/api/v1/admin/notifications/{notification_id}/read").json()


# --- Import ------------------------------------------------------------


def upload_import(filename: str, file_bytes: bytes) -> dict:
    return post("/api/v1/admin/imports/upload", files={"file": (filename, file_bytes)}).json()


def get_import_columns(job_id: int) -> dict:
    return get(f"/api/v1/admin/imports/{job_id}/columns").json()


def confirm_mapping(job_id: int, mapping: dict) -> dict:
    return post(f"/api/v1/admin/imports/{job_id}/mapping", json={"mapping": mapping}).json()


def validate_import(job_id: int) -> dict:
    return post(f"/api/v1/admin/imports/{job_id}/validate").json()


def preview_import(job_id: int, status: str | None = None, limit: int = 100, offset: int = 0) -> list:
    params: dict = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    return get(f"/api/v1/admin/imports/{job_id}/preview", params=params).json()


def confirm_import(job_id: int) -> dict:
    return post(f"/api/v1/admin/imports/{job_id}/confirm").json()


def list_imports() -> list:
    return get("/api/v1/admin/imports").json()


def get_import(job_id: int) -> dict:
    return get(f"/api/v1/admin/imports/{job_id}").json()


# --- System config -----------------------------------------------------


def list_system_config() -> list:
    return get("/api/v1/admin/system-config").json()


def update_system_config(key: str, value: str) -> dict:
    return patch(f"/api/v1/admin/system-config/{key}", json={"value": value}).json()
