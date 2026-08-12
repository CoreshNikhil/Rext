"""admin_web entry point: login screen, and (once authenticated) a
landing page pointing at Overview. Run with:

    .venv/bin/streamlit run admin_web/Home.py --server.port 8502

Every page under pages/ calls the backend over httpx via api_client.py —
no business logic lives here, matching the approved design's "no
separate backend for admins" rule.
"""

from __future__ import annotations

import streamlit as st

import auth

st.set_page_config(page_title="Gas Billing — Admin", page_icon="🔥", layout="wide")

if auth.is_authenticated():
    st.title("Gas Billing System — Admin")
    st.success(f"Logged in as {st.session_state.get('admin_email', 'admin')}")
    st.write("Use the sidebar to navigate to Overview, Residents, Meter Readings, Billing, and more.")
    if st.button("Log out"):
        auth.logout()
        st.rerun()
else:
    st.title("Gas Billing System — Admin Login")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        if not email or not password:
            st.error("Enter both email and password.")
        else:
            ok, error = auth.login(email, password)
            if ok:
                st.rerun()
            else:
                st.error(error)
