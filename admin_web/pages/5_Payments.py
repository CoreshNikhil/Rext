from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Payments — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Payments")

STATUS_OPTIONS = ["(any)", "initiated", "success", "failed", "cancelled"]

col1, col2 = st.columns(2)
status = col1.selectbox("Status", STATUS_OPTIONS)
bill_id_filter = col2.text_input("Bill ID (optional)")

try:
    payments = api_client.list_payments_admin(
        status=None if status == "(any)" else status,
        bill_id=int(bill_id_filter) if bill_id_filter.strip().isdigit() else None,
    )
except ApiError as exc:
    st.error(f"Could not load payments: {exc.detail}")
    st.stop()

st.dataframe(
    [
        {
            "ID": p["payment_id"],
            "Bill": p["bill_id"],
            "Resident": p["resident_id"],
            "Amount": p["amount"],
            "Provider": p["provider_name"],
            "Status": p["status"],
            "Failure reason": p["failure_reason"] or "",
            "Completed": p["completed_at"] or "",
        }
        for p in payments
    ],
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Mark a bill paid offline")
st.caption("For cash/cheque/bank-transfer payments collected outside the app.")

with st.form("mark_offline"):
    bill_id = st.text_input("Bill ID")
    reference_note = st.text_input("Reference note (e.g. cheque number, date collected)")
    submitted = st.form_submit_button("Mark paid offline")

if submitted:
    if not bill_id.strip().isdigit() or not reference_note:
        st.error("A numeric bill ID and a reference note are both required.")
    else:
        try:
            api_client.mark_bill_paid_offline(int(bill_id), reference_note)
            st.success("Bill marked paid offline.")
            st.rerun()
        except ApiError as exc:
            st.error(str(exc.detail))
