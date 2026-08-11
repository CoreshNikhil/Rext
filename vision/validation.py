"""Application-side validation of vision-model output.

The model's own confidence and quality self-assessment are never trusted
blindly — every result is re-checked here against structural and
consistency rules before being marked "accepted".
"""

from __future__ import annotations

import re

from config import settings
from models.meter_result import (
    ImageQuality,
    MeterReadingResult,
    ReviewStatus,
    VisionModelOutput,
)

RAW_DIGITS_PATTERN = re.compile(r"^\d+$")
READING_PATTERN = re.compile(r"^\d+(\.\d+)?$")
UNIT_PATTERN = re.compile(r"^[A-Za-z0-9³/.\-\s]{1,10}$")


def validate_output(
    output: VisionModelOutput,
    confidence_threshold: float | None = None,
) -> MeterReadingResult:
    """Re-validate a parsed model output and assign a final review status.

    Status tiers:
      - REJECTED: no meter was found at all, nothing to review.
      - NEEDS_REVIEW: a meter/display was found but something about the
        reading, its format, or the model's own confidence/quality signal
        means it should not be auto-accepted.
      - ACCEPTED: passed every structural check and confidence >= threshold.
    """
    threshold = (
        confidence_threshold if confidence_threshold is not None else settings.CONFIDENCE_THRESHOLD
    )
    notes: list[str] = []

    if output.reason:
        notes.append(f"Model reason: {output.reason}")

    if not output.meter_detected:
        notes.append("Model did not detect a meter in the image.")
        return MeterReadingResult.from_model_output(
            output, status=ReviewStatus.REJECTED, validation_notes=notes
        )

    passes = True

    if not output.display_detected:
        notes.append("Meter detected, but the numeric reading display was not located.")
        passes = False

    if not output.reading or not output.raw_digits:
        notes.append("No reading was returned.")
        passes = False
    else:
        digit_count = None
        if not RAW_DIGITS_PATTERN.match(output.raw_digits):
            notes.append(f"raw_digits '{output.raw_digits}' contains non-digit characters.")
            passes = False
        else:
            digit_count = len(output.raw_digits)

        if not READING_PATTERN.match(output.reading):
            notes.append(f"reading '{output.reading}' is not a valid numeric format.")
            passes = False
        elif digit_count is not None and output.reading.replace(".", "") != output.raw_digits:
            notes.append("reading digits do not match raw_digits once the decimal point is removed.")
            passes = False

        if digit_count is not None and not (
            settings.MIN_DIGIT_COUNT <= digit_count <= settings.MAX_DIGIT_COUNT
        ):
            notes.append(
                f"Digit count {digit_count} is outside the expected range "
                f"[{settings.MIN_DIGIT_COUNT}, {settings.MAX_DIGIT_COUNT}] for a meter reading "
                "— this may be a serial number or other misread text."
            )
            passes = False

    if output.unit is not None and not UNIT_PATTERN.match(output.unit):
        notes.append(f"unit '{output.unit}' has an unexpected format.")

    if not (0.0 <= output.confidence <= 1.0):
        notes.append(f"Confidence {output.confidence} is outside the valid [0, 1] range.")
        passes = False

    if output.needs_retake:
        notes.append("Model explicitly flagged this image for retake.")
        passes = False

    if output.image_quality == ImageQuality.POOR.value:
        notes.append("Model rated image quality as poor.")
        passes = False

    if passes and output.confidence < threshold:
        notes.append(
            f"Confidence {output.confidence:.2f} is below the acceptance threshold {threshold:.2f}."
        )
        passes = False

    status = ReviewStatus.ACCEPTED if passes else ReviewStatus.NEEDS_REVIEW
    return MeterReadingResult.from_model_output(output, status=status, validation_notes=notes)
