"""Pydantic v2 request/response DTOs for meter reading submission/review."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MeterReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meter_reading_id: int
    billing_period_id: int
    meter_id: int
    resident_id: int
    previous_reading_value: Decimal | None
    submitted_reading_value: Decimal | None
    raw_digits: str | None
    unit: str | None
    ai_confidence: Decimal | None
    ai_status: str | None
    ai_reason: str | None
    ai_validation_notes: list[str] | None
    status: str
    submitted_by: str
    final_reading_value: Decimal | None
    resident_confirmed_at: datetime | None
    admin_reviewed_at: datetime | None
    created_at: datetime


class MeterReadingOverrideRequest(BaseModel):
    final_reading_value: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class MeterReadingRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
