"""Pydantic v2 request/response DTOs for payments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: int
    bill_id: int
    resident_id: int
    amount: Decimal
    provider_name: str
    provider_reference_id: str | None
    status: str
    initiated_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    created_at: datetime


class MockConfirmRequest(BaseModel):
    # Lets a test/dev client simulate either outcome of the "gateway
    # callback" — there's no real checkout page to redirect through yet.
    simulate_success: bool = True


class MarkOfflineRequest(BaseModel):
    reference_note: str = Field(min_length=1, max_length=200)
