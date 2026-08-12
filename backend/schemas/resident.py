"""Pydantic v2 request/response DTOs for admin resident management."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MeterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meter_id: int
    meter_serial_number: str
    install_date: date | None
    is_active: bool


class MeterCreateRequest(BaseModel):
    meter_serial_number: str = Field(min_length=1, max_length=40)
    install_date: date | None = None


class ResidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resident_id: int
    community_id: int
    house_number: str
    full_name: str
    mobile_number: str
    email: str | None
    is_active: bool
    onboarded_at: datetime | None
    created_at: datetime


class ResidentDetailResponse(ResidentResponse):
    meters: list[MeterResponse] = Field(default_factory=list)


class ResidentCreateRequest(BaseModel):
    house_number: str = Field(min_length=1, max_length=20)
    full_name: str = Field(min_length=1, max_length=120)
    mobile_number: str = Field(min_length=1, max_length=15)
    email: str | None = Field(default=None, max_length=255)
    # Optional: assign a meter to the resident at creation time.
    meter_serial_number: str | None = Field(default=None, max_length=40)


class ResidentUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    mobile_number: str | None = Field(default=None, min_length=1, max_length=15)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
