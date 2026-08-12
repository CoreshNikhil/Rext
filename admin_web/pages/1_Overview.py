from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Overview — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Overview")

try:
    overview = api_client.get_dashboard_overview()
    collections = api_client.get_dashboard_collections()
except ApiError as exc:
    st.error(f"Could not load dashboard: {exc.detail}")
    st.stop()

period_label = overview["current_billing_period_label"] or "No billing period yet"
st.caption(f"Current billing period: {period_label}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total residents", overview["total_residents"])
col2.metric("Active residents", overview["active_residents"])
col3.metric("Readings submitted", overview["readings_submitted"])
col4.metric("Readings pending", overview["readings_pending"])

col5, col6, col7, col8 = st.columns(4)
col5.metric("Bills generated", overview["bills_generated"])
col6.metric("Bills paid", overview["bills_paid"])
col7.metric("Bills unpaid", overview["bills_unpaid"])
col8.metric("Bills overdue", overview["bills_overdue"])

col9, col10, col11 = st.columns(3)
col9.metric("Total billed", f"Rs {overview['total_billed']}")
col10.metric("Total collected", f"Rs {overview['total_collected']}")
col11.metric("Outstanding", f"Rs {overview['outstanding']}")

st.subheader("Collections by billing period")
if collections:
    st.dataframe(
        [
            {
                "Period": row["period_label"],
                "Total billed": f"Rs {row['total_billed']}",
                "Total collected": f"Rs {row['total_collected']}",
                "Collection rate": f"{row['collection_rate_percent']}%",
            }
            for row in collections
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No billing periods yet.")
