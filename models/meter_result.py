"""Data models for MeterVision reading extraction results."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ImageQuality(str, Enum):
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    UNKNOWN = "unknown"


class ReviewStatus(str, Enum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class VisionModelOutput(BaseModel):
    """Raw structured output expected directly from the vision model.

    This mirrors the strict JSON contract given to the model in the prompt.
    Kept separate from MeterReadingResult so a malformed/partial model
    response never has to satisfy application-level fields.
    """

    meter_detected: bool = False
    display_detected: bool = False
    raw_digits: Optional[str] = None
    reading: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 0.0
    image_quality: str = ImageQuality.UNKNOWN.value
    needs_retake: bool = True
    reason: str = ""


class MeterReadingResult(BaseModel):
    """Final structured result returned by the MeterVision pipeline.

    Combines the vision model's own assessment with application-side
    validation, since the model's self-reported confidence is never
    trusted blindly.
    """

    meter_detected: bool = False
    display_detected: bool = False
    raw_digits: Optional[str] = None
    reading: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 0.0
    image_quality: str = ImageQuality.UNKNOWN.value
    needs_retake: bool = True
    reason: str = ""

    status: ReviewStatus = ReviewStatus.REJECTED
    validation_notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_model_output(
        cls, output: VisionModelOutput, **validation_fields
    ) -> "MeterReadingResult":
        return cls(**output.model_dump(), **validation_fields)
