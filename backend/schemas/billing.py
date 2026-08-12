"""Pydantic v2 request/response DTOs for the billing engine."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BillingPeriodCreateRequest(BaseModel):
    period_label: str = Field(min_length=1, max_length=20)
    reading_window_start: date
    reading_window_end: date
    payment_due_date: date
    rate_per_unit: Decimal = Field(gt=0)
    fine_per_day_overdue: Decimal = Field(ge=0)


class BillingPeriodUpdateRequest(BaseModel):
    reading_window_start: date | None = None
    reading_window_end: date | None = None
    payment_due_date: date | None = None
    rate_per_unit: Decimal | None = Field(default=None, gt=0)
    fine_per_day_overdue: Decimal | None = Field(default=None, ge=0)


class BillingPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    billing_period_id: int
    community_id: int
    period_label: str
    reading_window_start: date
    reading_window_end: date
    payment_due_date: date
    rate_per_unit: Decimal
    fine_per_day_overdue: Decimal
    status: str
    created_at: datetime
    closed_at: datetime | None


class GenerateBillsResponse(BaseModel):
    bills_created: int
    total_finalized_readings: int


class BillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bill_id: int
    billing_period_id: int
    resident_id: int
    meter_reading_id: int | None
    previous_reading_value: Decimal
    current_reading_value: Decimal
    consumption_units: Decimal
    rate_per_unit: Decimal
    amount_due: Decimal
    fine_amount: Decimal
    total_amount_due: Decimal
    due_date: date
    status: str
    generated_at: datetime | None
    paid_at: datetime | None
    created_at: datetime


class BillActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
