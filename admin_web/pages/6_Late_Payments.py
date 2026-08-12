from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Late Payments — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Late Payments")
st.caption("Bills currently overdue — fines accrue daily via the scheduled fine_accrual job.")

try:
    overdue_bills = api_client.list_bills(status="overdue")
except ApiError as exc:
    st.error(f"Could not load overdue bills: {exc.detail}")
    st.stop()

if not overdue_bills:
    st.success("No overdue bills right now.")
    st.stop()

st.dataframe(
    [
        {
            "Bill ID": b["bill_id"],
            "Resident": b["resident_id"],
            "Billing period": b["billing_period_id"],
            "Amount due": b["amount_due"],
            "Fine accrued": b["fine_amount"],
            "Total due": b["total_amount_due"],
            "Due date": b["due_date"],
        }
        for b in overdue_bills
    ],
    use_container_width=True,
    hide_index=True,
)

st.info("Use the Payments page to mark a bill paid offline, or Billing to waive/cancel it.")
