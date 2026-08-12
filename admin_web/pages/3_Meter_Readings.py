from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Meter Readings — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Meter Readings")

STATUS_OPTIONS = ["(any)", "submitted", "ai_accepted", "needs_review", "rejected", "resident_confirmed", "admin_overridden"]

col1, col2 = st.columns(2)
status = col1.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index("needs_review"))
resident_id_filter = col2.text_input("Resident ID (optional)")

try:
    readings = api_client.list_readings_admin(
        status=None if status == "(any)" else status,
        resident_id=int(resident_id_filter) if resident_id_filter.strip().isdigit() else None,
    )
except ApiError as exc:
    st.error(f"Could not load readings: {exc.detail}")
    st.stop()

st.dataframe(
    [
        {
            "ID": r["meter_reading_id"],
            "Resident": r["resident_id"],
            "Status": r["status"],
            "AI status": r["ai_status"] or "",
            "Confidence": r["ai_confidence"],
            "Submitted value": r["submitted_reading_value"],
            "Final value": r["final_reading_value"],
            "Submitted by": r["submitted_by"],
            "Created": r["created_at"],
        }
        for r in readings
    ],
    use_container_width=True,
    hide_index=True,
)

if not readings:
    st.info("No readings match this filter.")
    st.stop()

st.divider()
st.subheader("Review a reading")

options = {f"#{r['meter_reading_id']} — resident {r['resident_id']} ({r['status']})": r["meter_reading_id"] for r in readings}
selected_label = st.selectbox("Select reading", list(options.keys()))
reading_id = options[selected_label]

try:
    reading = api_client.get_reading_admin(reading_id)
except ApiError as exc:
    st.error(f"Could not load reading: {exc.detail}")
    st.stop()

col_img, col_detail = st.columns([1, 1])
with col_img:
    try:
        image_bytes = api_client.get_reading_image_admin(reading_id)
        st.image(image_bytes, caption=f"Reading #{reading_id}", use_container_width=True)
    except ApiError as exc:
        st.warning(f"Could not load image: {exc.detail}")

with col_detail:
    st.write(f"**Status:** {reading['status']}")
    st.write(f"**AI status:** {reading['ai_status']}")
    st.write(f"**AI confidence:** {reading['ai_confidence']}")
    st.write(f"**AI reason:** {reading['ai_reason'] or '—'}")
    if reading["ai_validation_notes"]:
        st.write("**Validation notes:**")
        for note in reading["ai_validation_notes"]:
            st.write(f"- {note}")
    st.write(f"**Previous reading:** {reading['previous_reading_value']}")
    st.write(f"**Submitted reading:** {reading['submitted_reading_value']}")
    st.write(f"**Final reading:** {reading['final_reading_value']}")

st.divider()
col_override, col_reject = st.columns(2)

with col_override:
    st.write("**Override**")
    with st.form("override_form"):
        final_value = st.text_input("Corrected final reading value")
        override_reason = st.text_area("Reason for override", key="override_reason")
        override_submit = st.form_submit_button("Override reading")
    if override_submit:
        if not final_value or not override_reason:
            st.error("Both a corrected value and a reason are required.")
        else:
            try:
                api_client.override_reading(reading_id, final_value, override_reason)
                st.success("Reading overridden.")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))

with col_reject:
    st.write("**Reject**")
    with st.form("reject_form"):
        reject_reason = st.text_area("Reason for rejection", key="reject_reason")
        reject_submit = st.form_submit_button("Reject reading")
    if reject_submit:
        if not reject_reason:
            st.error("A reason is required.")
        else:
            try:
                api_client.reject_reading(reading_id, reject_reason)
                st.success("Reading rejected — the resident can resubmit.")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))
