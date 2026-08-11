"""Tests for application-side validation and confidence handling.

Covers: confidence threshold behavior, reading format validation, digit
count sanity checks, missing readings, and retake conditions. These checks
exist because the vision model's self-reported confidence/quality is never
trusted blindly.
"""

from __future__ import annotations

from models.meter_result import ReviewStatus, VisionModelOutput
from vision.validation import validate_output


def make_output(**overrides) -> VisionModelOutput:
    base = dict(
        meter_detected=True,
        display_detected=True,
        raw_digits="00115197",
        reading="00115.197",
        unit="m3",
        confidence=0.96,
        image_quality="acceptable",
        needs_retake=False,
        reason="",
    )
    base.update(overrides)
    return VisionModelOutput(**base)


def test_high_confidence_clean_reading_is_accepted():
    output = make_output(confidence=0.96)
    result = validate_output(output, confidence_threshold=0.85)
    assert result.status == ReviewStatus.ACCEPTED
    assert result.reading == "00115.197"


def test_confidence_below_threshold_needs_review():
    output = make_output(confidence=0.60)
    result = validate_output(output, confidence_threshold=0.85)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("below the acceptance threshold" in note for note in result.validation_notes)


def test_confidence_exactly_at_threshold_is_accepted():
    output = make_output(confidence=0.85)
    result = validate_output(output, confidence_threshold=0.85)
    assert result.status == ReviewStatus.ACCEPTED


def test_no_meter_detected_is_rejected():
    output = make_output(
        meter_detected=False,
        display_detected=False,
        raw_digits=None,
        reading=None,
        confidence=0.1,
        needs_retake=True,
        reason="No meter visible in the frame.",
    )
    result = validate_output(output)
    assert result.status == ReviewStatus.REJECTED


def test_meter_detected_but_no_display_needs_review():
    output = make_output(display_detected=False, reading=None, raw_digits=None)
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("display" in note.lower() for note in result.validation_notes)


def test_missing_reading_needs_review():
    output = make_output(raw_digits=None, reading=None, confidence=0.9)
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("no reading" in note.lower() for note in result.validation_notes)


def test_needs_retake_flag_forces_review_even_with_high_confidence():
    output = make_output(needs_retake=True, confidence=0.99, reason="Glare over digits.")
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW


def test_poor_image_quality_forces_review():
    output = make_output(image_quality="poor")
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW


def test_non_numeric_reading_is_rejected_as_invalid_format():
    output = make_output(raw_digits="00A15197", reading="00A15.197")
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("not a valid numeric format" in note or "non-digit" in note for note in result.validation_notes)


def test_reading_decimal_mismatch_with_raw_digits_is_flagged():
    # reading's digits (ignoring the decimal point) don't match raw_digits —
    # a sign the model formatted inconsistently.
    output = make_output(raw_digits="00115197", reading="00115.198")
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("do not match" in note for note in result.validation_notes)


def test_digit_count_too_low_is_flagged_as_likely_wrong_field():
    output = make_output(raw_digits="12", reading="12")
    result = validate_output(output, confidence_threshold=0.5)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("outside the expected range" in note for note in result.validation_notes)


def test_digit_count_too_high_is_flagged_as_possible_serial_number():
    # e.g. an 11-digit serial number accidentally read instead of the meter display
    output = make_output(raw_digits="12345678901", reading="12345678901")
    result = validate_output(output, confidence_threshold=0.5)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("outside the expected range" in note for note in result.validation_notes)


def test_confidence_out_of_valid_range_is_flagged():
    output = make_output(confidence=1.4)
    result = validate_output(output)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("outside the valid" in note for note in result.validation_notes)


def test_model_reason_is_preserved_in_validation_notes():
    output = make_output(
        meter_detected=True,
        display_detected=True,
        raw_digits=None,
        reading=None,
        confidence=0.3,
        needs_retake=True,
        reason="Digits obscured by glare.",
    )
    result = validate_output(output)
    assert any("Digits obscured by glare." in note for note in result.validation_notes)


def test_result_preserves_original_model_fields():
    output = make_output()
    result = validate_output(output)
    assert result.meter_detected == output.meter_detected
    assert result.raw_digits == output.raw_digits
    assert result.reading == output.reading
    assert result.unit == output.unit


def test_serial_number_is_preserved_when_distinct_from_reading():
    output = make_output(serial_number="16710009")
    result = validate_output(output)
    assert result.status == ReviewStatus.ACCEPTED
    assert result.serial_number == "16710009"


def test_missing_serial_number_does_not_block_acceptance():
    output = make_output(serial_number=None)
    result = validate_output(output)
    assert result.status == ReviewStatus.ACCEPTED


def test_serial_number_matching_raw_digits_is_flagged_as_confusion():
    # If the model reports the same value for both fields, it almost
    # certainly read the serial number into the reading (or vice versa) —
    # exactly the mix-up this tool exists to prevent.
    output = make_output(raw_digits="16710009", reading="16710009", serial_number="16710009")
    result = validate_output(output, confidence_threshold=0.5)
    assert result.status == ReviewStatus.NEEDS_REVIEW
    assert any("confused the reading display with the serial number" in note for note in result.validation_notes)
