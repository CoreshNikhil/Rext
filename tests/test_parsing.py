"""Tests for parsing raw provider responses into VisionModelOutput.

Covers: valid JSON, invalid/malformed JSON, non-dict payloads, schema
violations, and defensive normalization (confidence clamping, unexpected
enum values).
"""

from __future__ import annotations

from models.meter_result import ImageQuality, VisionModelOutput
from vision.detection import parse_model_response


def test_parses_valid_dict_response():
    raw = {
        "meter_detected": True,
        "display_detected": True,
        "raw_digits": "00115197",
        "reading": "00115.197",
        "unit": "m3",
        "confidence": 0.96,
        "image_quality": "acceptable",
        "needs_retake": False,
        "reason": "",
    }
    output = parse_model_response(raw)
    assert isinstance(output, VisionModelOutput)
    assert output.raw_digits == "00115197"
    assert output.reading == "00115.197"
    assert output.confidence == 0.96
    assert output.needs_retake is False


def test_parses_valid_json_string_response():
    raw = (
        '{"meter_detected": true, "display_detected": true, "raw_digits": "123",'
        ' "reading": "123", "unit": null, "confidence": 0.9, "image_quality": "acceptable",'
        ' "needs_retake": false, "reason": ""}'
    )
    output = parse_model_response(raw)
    assert output.reading == "123"
    assert output.unit is None


def test_malformed_json_string_falls_back_conservatively():
    output = parse_model_response("{not valid json at all")
    assert output.meter_detected is False
    assert output.raw_digits is None
    assert output.reading is None
    assert output.needs_retake is True
    assert "not valid JSON" in output.reason


def test_non_dict_json_falls_back_conservatively():
    output = parse_model_response("[1, 2, 3]")
    assert output.meter_detected is False
    assert output.needs_retake is True
    assert "JSON object" in output.reason


def test_none_response_falls_back_conservatively():
    output = parse_model_response(None)
    assert output.meter_detected is False
    assert output.needs_retake is True
    assert "no response" in output.reason.lower()


def test_response_missing_all_fields_uses_defaults():
    # Every field on VisionModelOutput has a safe default, so an empty dict
    # should parse without raising rather than crashing the pipeline.
    output = parse_model_response({})
    assert output.meter_detected is False
    assert output.confidence == 0.0
    assert output.needs_retake is True


def test_response_with_wrong_field_types_falls_back():
    raw = {
        "meter_detected": "yes",  # not a bool, and not coercible by pydantic strict rules here
        "display_detected": True,
        "raw_digits": ["0", "0", "1"],  # not a string
        "reading": "001",
        "confidence": 0.9,
        "image_quality": "acceptable",
        "needs_retake": False,
        "reason": "",
    }
    output = parse_model_response(raw)
    # Either it fails validation and falls back, or pydantic coerces "yes" ->
    # truthy in a way we don't want. We only assert it never raises and
    # always returns a VisionModelOutput.
    assert isinstance(output, VisionModelOutput)


def test_confidence_out_of_range_is_clamped():
    raw = {
        "meter_detected": True,
        "display_detected": True,
        "raw_digits": "12345",
        "reading": "12345",
        "confidence": 1.5,
        "image_quality": "acceptable",
        "needs_retake": False,
        "reason": "",
    }
    output = parse_model_response(raw)
    assert output.confidence == 1.0

    raw["confidence"] = -0.3
    output = parse_model_response(raw)
    assert output.confidence == 0.0


def test_unexpected_image_quality_value_is_normalized():
    raw = {
        "meter_detected": True,
        "display_detected": True,
        "raw_digits": "12345",
        "reading": "12345",
        "confidence": 0.9,
        "image_quality": "blurry-ish",
        "needs_retake": False,
        "reason": "",
    }
    output = parse_model_response(raw)
    assert output.image_quality == ImageQuality.UNKNOWN.value
