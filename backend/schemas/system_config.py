"""Pydantic v2 request/response DTOs for admin system configuration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    value_type: str
    description: str | None
    updated_at: datetime


class SystemConfigUpdateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=255)
