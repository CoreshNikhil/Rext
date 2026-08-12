"""Spreadsheet import wizard: upload -> map columns -> validate -> preview
-> confirm -> history, all on one page per the approved design. The
job's own `status` field (from the backend) drives which step renders —
session_state only remembers *which* job is currently in progress, never
duplicates status locally, so a page refresh can't desync from reality.
"""

from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Import Data — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Import Data")

CANONICAL_FIELDS = ["house_number", "full_name", "mobile_number", "meter_serial_number", "email", "install_date"]
REQUIRED_FIELDS = {"house_number", "full_name", "mobile_number", "meter_serial_number"}

if "import_job_id" not in st.session_state:
    st.session_state["import_job_id"] = None

if st.session_state["import_job_id"] is not None:
    if st.button("Start a new import"):
        st.session_state["import_job_id"] = None
        st.rerun()

if st.session_state["import_job_id"] is None:
    st.subheader("1. Upload a spreadsheet")
    uploaded = st.file_uploader("Resident roster (.xlsx or .csv)", type=["xlsx", "xls", "csv"])
    if uploaded is not None and st.button("Upload"):
        try:
            job = api_client.upload_import(uploaded.name, uploaded.getvalue())
            st.session_state["import_job_id"] = job["import_job_id"]
            st.rerun()
        except ApiError as exc:
            st.error(str(exc.detail))
else:
    job_id = st.session_state["import_job_id"]
    try:
        job = api_client.get_import(job_id)
    except ApiError as exc:
        st.error(f"Could not load import job: {exc.detail}")
        st.session_state["import_job_id"] = None
        st.stop()

    st.write(f"**Job #{job_id}** — {job['original_filename']} — status: **{job['status']}**")

    if job["status"] == "uploaded":
        st.subheader("2. Map columns")
        try:
            columns_info = api_client.get_import_columns(job_id)
        except ApiError as exc:
            st.error(str(exc.detail))
            st.stop()

        columns = columns_info["columns"]
        suggested = columns_info["suggested_mapping"]
        st.caption("Map each field this system needs to a column from your spreadsheet.")

        mapping = {}
        for field in CANONICAL_FIELDS:
            options = ["— none —"] + columns
            default = suggested.get(field)
            default_index = options.index(default) if default in options else 0
            label = f"{field} (required)" if field in REQUIRED_FIELDS else f"{field} (optional)"
            choice = st.selectbox(label, options, index=default_index, key=f"map_{field}")
            mapping[field] = None if choice == "— none —" else choice

        if st.button("Confirm mapping"):
            missing = [f for f in REQUIRED_FIELDS if not mapping.get(f)]
            if missing:
                st.error(f"These required fields still need a column: {', '.join(missing)}")
            else:
                try:
                    api_client.confirm_mapping(job_id, mapping)
                    st.rerun()
                except ApiError as exc:
                    st.error(str(exc.detail))

    elif job["status"] == "mapped":
        st.subheader("3. Validate")
        if st.button("Run validation"):
            try:
                api_client.validate_import(job_id)
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))

    elif job["status"] == "validated":
        st.subheader("3. Validation results")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total rows", job["total_rows"])
        col2.metric("Valid/warning rows", job["valid_rows"])
        col3.metric("Error rows", job["error_rows"])

        st.subheader("4. Preview")
        try:
            rows = api_client.preview_import(job_id, limit=200)
        except ApiError as exc:
            st.error(str(exc.detail))
            rows = []

        status_icon = {"valid": "🟢", "warning": "🟡", "error": "🔴"}
        st.dataframe(
            [
                {
                    "Row": r["row_number"],
                    "Status": f"{status_icon.get(r['validation_status'], '')} {r['validation_status']}",
                    "Action": r["action"] or "",
                    "House": (r["mapped_data"] or {}).get("house_number", ""),
                    "Name": (r["mapped_data"] or {}).get("full_name", ""),
                    "Mobile": (r["mapped_data"] or {}).get("mobile_number", ""),
                    "Meter": (r["mapped_data"] or {}).get("meter_serial_number", ""),
                    "Errors": "; ".join(r["validation_errors"] or []),
                }
                for r in rows
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Error rows are always skipped on confirm. Warning rows (e.g. house already exists → update) still import.")

        st.subheader("5. Confirm")
        if job["error_rows"] > 0:
            st.warning(f"{job['error_rows']} row(s) have errors and will be skipped if you confirm.")
        if st.button("Confirm import", type="primary"):
            try:
                api_client.confirm_import(job_id)
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))

    elif job["status"] == "confirmed":
        st.success(f"Import confirmed at {job['confirmed_at']}.")

    elif job["status"] in ("failed", "cancelled"):
        st.error(f"This import job is {job['status']} and can't continue.")

st.divider()
st.subheader("Import history")
try:
    history = api_client.list_imports()
except ApiError as exc:
    st.error(f"Could not load import history: {exc.detail}")
    history = []

if history:
    st.dataframe(
        [
            {
                "ID": h["import_job_id"],
                "File": h["original_filename"],
                "Status": h["status"],
                "Total": h["total_rows"],
                "Valid": h["valid_rows"],
                "Errors": h["error_rows"],
                "Created": h["created_at"],
                "Confirmed": h["confirmed_at"] or "",
            }
            for h in history
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No imports yet.")
