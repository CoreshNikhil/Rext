from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Notifications — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Notifications")

try:
    notifications = api_client.list_admin_notifications()
except ApiError as exc:
    st.error(f"Could not load notifications: {exc.detail}")
    st.stop()

if not notifications:
    st.info("No notifications.")
    st.stop()

unread_count = sum(1 for n in notifications if not n["is_read"])
st.caption(f"{unread_count} unread of {len(notifications)} total")

for n in notifications:
    icon = "🔵" if not n["is_read"] else "⚪"
    with st.container(border=True):
        col_text, col_action = st.columns([5, 1])
        with col_text:
            st.write(f"{icon} **{n['title']}**")
            st.write(n["message"])
            st.caption(f"{n['type']} · {n['sent_at']}")
        with col_action:
            if not n["is_read"]:
                if st.button("Mark read", key=f"read_{n['notification_id']}"):
                    try:
                        api_client.mark_admin_notification_read(n["notification_id"])
                        st.rerun()
                    except ApiError as exc:
                        st.error(str(exc.detail))
