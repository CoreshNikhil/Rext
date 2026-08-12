from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="System Settings — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("System Settings")
st.caption("OTP behavior and validation patterns for resident signup/login.")

KEYS = ["otp_expiry_minutes", "otp_max_attempts", "mobile_number_regex", "house_number_regex"]

try:
    config = {c["key"]: c for c in api_client.list_system_config()}
except ApiError as exc:
    st.error(f"Could not load configuration: {exc.detail}")
    st.stop()

with st.form("system_settings_form"):
    new_values = {}
    for key in KEYS:
        entry = config.get(key)
        if entry is None:
            st.warning(f"Key '{key}' not found in system configuration.")
            continue
        new_values[key] = st.text_input(key, value=entry["value"], help=entry["description"])
    submitted = st.form_submit_button("Save changes")

if submitted:
    errors = []
    for key, value in new_values.items():
        if value != config[key]["value"]:
            try:
                api_client.update_system_config(key, value)
            except ApiError as exc:
                errors.append(f"{key}: {exc.detail}")
    if errors:
        for e in errors:
            st.error(e)
    else:
        st.success("Saved.")
        st.rerun()
