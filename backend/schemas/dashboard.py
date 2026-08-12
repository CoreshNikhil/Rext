"""Pydantic v2 response DTOs for the admin dashboard."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DashboardOverviewResponse(BaseModel):
    total_residents: int
    active_residents: int
    current_billing_period_id: int | None
    current_billing_period_label: str | None
    readings_submitted: int
    readings_pending: int
    bills_generated: int
    bills_paid: int
    bills_unpaid: int
    bills_overdue: int
    total_billed: Decimal
    total_collected: Decimal
    outstanding: Decimal


class CollectionsByPeriodResponse(BaseModel):
    billing_period_id: int
    period_label: str
    total_billed: Decimal
    total_collected: Decimal
    collection_rate_percent: Decimal
