"""Session-state-backed admin auth for the admin_web Streamlit app."""

from __future__ import annotations

import streamlit as st

import api_client
from api_client import ApiError


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token"))


def login(email: str, password: str) -> tuple[bool, str | None]:
    try:
        tokens = api_client.login_admin(email, password)
    except ApiError as exc:
        return False, str(exc.detail)
    st.session_state["access_token"] = tokens["access_token"]
    st.session_state["refresh_token"] = tokens["refresh_token"]
    st.session_state["admin_email"] = email
    return True, None


def logout() -> None:
    api_client.logout()
    for key in ("access_token", "refresh_token", "admin_email"):
        st.session_state.pop(key, None)


def require_login() -> None:
    """Call at the top of every page other than Home. Stops rendering
    with a message if there's no active admin session."""
    if not is_authenticated():
        st.warning("Please log in from the Home page first.")
        st.page_link("Home.py", label="Go to login", icon="🔑")
        st.stop()
