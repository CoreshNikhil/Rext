from __future__ import annotations

import streamlit as st

import api_client
import auth
from api_client import ApiError

st.set_page_config(page_title="Billing — Admin", page_icon="🔥", layout="wide")
auth.require_login()

st.title("Billing")

try:
    periods = api_client.list_billing_periods()
except ApiError as exc:
    st.error(f"Could not load billing periods: {exc.detail}")
    st.stop()

st.dataframe(
    [
        {
            "ID": p["billing_period_id"],
            "Label": p["period_label"],
            "Status": p["status"],
            "Reading window": f"{p['reading_window_start']} to {p['reading_window_end']}",
            "Payment due": p["payment_due_date"],
            "Rate/unit": p["rate_per_unit"],
            "Fine/day": p["fine_per_day_overdue"],
        }
        for p in periods
    ],
    use_container_width=True,
    hide_index=True,
)

with st.expander("Create billing period"):
    with st.form("create_period"):
        period_label = st.text_input("Period label (e.g. 2026-09)")
        c1, c2, c3 = st.columns(3)
        reading_start = c1.date_input("Reading window start")
        reading_end = c2.date_input("Reading window end")
        payment_due = c3.date_input("Payment due date")
        c4, c5 = st.columns(2)
        rate = c4.number_input("Rate per unit", min_value=0.01, value=50.0, step=1.0)
        fine = c5.number_input("Fine per day overdue", min_value=0.0, value=10.0, step=1.0)
        create_submit = st.form_submit_button("Create period")

    if create_submit:
        if not period_label:
            st.error("Period label is required.")
        else:
            payload = {
                "period_label": period_label,
                "reading_window_start": str(reading_start),
                "reading_window_end": str(reading_end),
                "payment_due_date": str(payment_due),
                "rate_per_unit": str(rate),
                "fine_per_day_overdue": str(fine),
            }
            try:
                created = api_client.create_billing_period(payload)
                st.success(f"Created billing period {created['period_label']}.")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))

st.divider()
st.subheader("Manage a billing period")

if not periods:
    st.info("No billing periods yet.")
    st.stop()

options = {f"{p['period_label']} ({p['status']}, id {p['billing_period_id']})": p["billing_period_id"] for p in periods}
selected_label = st.selectbox("Select billing period", list(options.keys()))
period_id = options[selected_label]
period = next(p for p in periods if p["billing_period_id"] == period_id)

st.write(f"**Status:** {period['status']}")

col1, col2, col3, col4 = st.columns(4)
if col1.button("Open (draft → open_for_readings)"):
    try:
        api_client.open_billing_period(period_id)
        st.success("Period opened.")
        st.rerun()
    except ApiError as exc:
        st.error(str(exc.detail))
if col2.button("Close readings"):
    try:
        api_client.close_readings(period_id)
        st.success("Reading window closed.")
        st.rerun()
    except ApiError as exc:
        st.error(str(exc.detail))
if col3.button("Generate bills"):
    try:
        result = api_client.generate_bills(period_id)
        st.success(f"Generated {result['bills_created']} bill(s) from {result['total_finalized_readings']} finalized reading(s).")
        st.rerun()
    except ApiError as exc:
        st.error(str(exc.detail))
if col4.button("Close period"):
    try:
        api_client.close_billing_period(period_id)
        st.success("Period closed.")
        st.rerun()
    except ApiError as exc:
        st.error(str(exc.detail))

if period["status"] == "draft":
    with st.expander("Edit period (only while DRAFT)"):
        with st.form("update_period"):
            c1, c2, c3 = st.columns(3)
            reading_start = c1.date_input("Reading window start", value=None)
            reading_end = c2.date_input("Reading window end", value=None)
            payment_due = c3.date_input("Payment due date", value=None)
            c4, c5 = st.columns(2)
            rate = c4.text_input("Rate per unit (leave blank to keep)")
            fine = c5.text_input("Fine per day overdue (leave blank to keep)")
            update_submit = st.form_submit_button("Save changes")

        if update_submit:
            payload = {}
            if reading_start:
                payload["reading_window_start"] = str(reading_start)
            if reading_end:
                payload["reading_window_end"] = str(reading_end)
            if payment_due:
                payload["payment_due_date"] = str(payment_due)
            if rate:
                payload["rate_per_unit"] = rate
            if fine:
                payload["fine_per_day_overdue"] = fine
            try:
                api_client.update_billing_period(period_id, payload)
                st.success("Period updated.")
                st.rerun()
            except ApiError as exc:
                st.error(str(exc.detail))

st.divider()
st.subheader(f"Bills for {period['period_label']}")

try:
    bills = api_client.list_bills(billing_period_id=period_id)
except ApiError as exc:
    st.error(f"Could not load bills: {exc.detail}")
    st.stop()

st.dataframe(
    [
        {
            "ID": b["bill_id"],
            "Resident": b["resident_id"],
            "Consumption": b["consumption_units"],
            "Amount due": b["amount_due"],
            "Fine": b["fine_amount"],
            "Total": b["total_amount_due"],
            "Status": b["status"],
            "Due date": b["due_date"],
        }
        for b in bills
    ],
    use_container_width=True,
    hide_index=True,
)

if bills:
    bill_options = {f"#{b['bill_id']} — resident {b['resident_id']} ({b['status']})": b["bill_id"] for b in bills}
    selected_bill_label = st.selectbox("Select bill", list(bill_options.keys()))
    bill_id = bill_options[selected_bill_label]

    col_waive, col_cancel = st.columns(2)
    with col_waive:
        with st.form("waive_bill"):
            waive_reason = st.text_area("Reason to waive")
            waive_submit = st.form_submit_button("Waive bill")
        if waive_submit:
            if not waive_reason:
                st.error("A reason is required.")
            else:
                try:
                    api_client.waive_bill(bill_id, waive_reason)
                    st.success("Bill waived.")
                    st.rerun()
                except ApiError as exc:
                    st.error(str(exc.detail))
    with col_cancel:
        with st.form("cancel_bill"):
            cancel_reason = st.text_area("Reason to cancel")
            cancel_submit = st.form_submit_button("Cancel bill")
        if cancel_submit:
            if not cancel_reason:
                st.error("A reason is required.")
            else:
                try:
                    api_client.cancel_bill(bill_id, cancel_reason)
                    st.success("Bill cancelled.")
                    st.rerun()
                except ApiError as exc:
                    st.error(str(exc.detail))
