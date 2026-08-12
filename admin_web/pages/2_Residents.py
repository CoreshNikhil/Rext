from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Residents — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Residents")

col_search, col_active = st.columns([3, 1])
search = col_search.text_input("Search (house number / name / mobile)")
active_only = col_active.checkbox("Active only", value=False)

try:
    residents = api_client.list_residents(active_only=active_only, search=search or None)
except ApiError as exc:
    st.error(f"Could not load residents: {exc.detail}")
    st.stop()

st.dataframe(
    [
        {
            "ID": r["resident_id"],
            "House": r["house_number"],
            "Name": r["full_name"],
            "Mobile": r["mobile_number"],
            "Email": r["email"] or "",
            "Active": r["is_active"],
            "Onboarded": bool(r["onboarded_at"]),
        }
        for r in residents
    ],
    use_container_width=True,
    hide_index=True,
)

with st.expander("Add resident"):
    with st.form("create_resident"):
        c1, c2 = st.columns(2)
        house_number = c1.text_input("House number")
        full_name = c2.text_input("Full name")
        c3, c4 = st.columns(2)
        mobile_number = c3.text_input("Mobile number")
        email = c4.text_input("Email (optional)")
        meter_serial_number = st.text_input("Meter serial number (optional, assign now)")
        submitted = st.form_submit_button("Create resident")

    if submitted:
        if not house_number or not full_name or not mobile_number:
            st.error("House number, full name, and mobile number are required.")
        else:
            payload = {
                "house_number": house_number,
                "full_name": full_name,
                "mobile_number": mobile_number,
                "email": email or None,
                "meter_serial_number": meter_serial_number or None,
            }
            try:
                created = api_client.create_resident(payload)
                st.success(f"Created resident {created['house_number']} (id {created['resident_id']}).")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))

st.divider()
st.subheader("Manage a resident")

if not residents:
    st.info("No residents yet.")
    st.stop()

options = {f"{r['house_number']} — {r['full_name']} (id {r['resident_id']})": r["resident_id"] for r in residents}
selected_label = st.selectbox("Select resident", list(options.keys()))
resident_id = options[selected_label]

try:
    detail = api_client.get_resident(resident_id)
except ApiError as exc:
    st.error(f"Could not load resident: {exc.detail}")
    st.stop()

st.write(f"**Meters:** {', '.join(m['meter_serial_number'] for m in detail['meters']) or 'none assigned'}")

with st.form("update_resident"):
    c1, c2 = st.columns(2)
    full_name = c1.text_input("Full name", value=detail["full_name"])
    mobile_number = c2.text_input("Mobile number", value=detail["mobile_number"])
    c3, c4 = st.columns(2)
    email = c3.text_input("Email", value=detail["email"] or "")
    is_active = c4.checkbox("Active", value=detail["is_active"])
    save = st.form_submit_button("Save changes")

if save:
    try:
        api_client.update_resident(
            resident_id,
            {"full_name": full_name, "mobile_number": mobile_number, "email": email or None, "is_active": is_active},
        )
        st.success("Resident updated.")
        st.rerun()
    except ApiError as exc:
        st.error(str(exc.detail))

col_deactivate, col_reset = st.columns(2)
with col_deactivate:
    if st.button("Deactivate resident (soft-delete)"):
        try:
            api_client.deactivate_resident(resident_id)
            st.success("Resident deactivated.")
            st.rerun()
        except ApiError as exc:
            st.error(str(exc.detail))
with col_reset:
    if st.button("Reset password"):
        try:
            api_client.reset_resident_password(resident_id)
            st.success("Password reset — resident must use the OTP password-reset flow to log in again.")
        except ApiError as exc:
            st.error(str(exc.detail))

with st.expander("Assign a new meter"):
    with st.form("assign_meter"):
        meter_serial = st.text_input("Meter serial number")
        install_date = st.date_input("Install date", value=None)
        assign = st.form_submit_button("Assign meter")

    if assign:
        if not meter_serial:
            st.error("Meter serial number is required.")
        else:
            try:
                api_client.assign_meter(resident_id, meter_serial, install_date)
                st.success("Meter assigned.")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))
