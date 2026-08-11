"""Pipeline orchestration: preprocessing -> provider call -> parsing ->
validation -> structured MeterReadingResult.

This module intentionally contains no OpenCV or SDK-specific code itself —
it wires together vision.preprocessing, a providers.base.VisionProvider,
and vision.validation.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from models.meter_result import ImageQuality, MeterReadingResult, VisionModelOutput
from providers.base import ImagePayload, ProviderError, VisionProvider, VisionRequest
from vision.preprocessing import PreprocessedImage, build_preprocessed_variants
from vision.prompts import build_meter_reading_prompt
from vision.validation import validate_output

logger = logging.getLogger(__name__)

# Keep the number of images sent to the vision API small and deliberate —
# more variants improve robustness but increase cost/latency per request.
MAX_VARIANTS_TO_SEND = 2
PREFERRED_VARIANT_ORDER = ("enhanced", "original", "deglared", "aligned")


def select_variants_for_upload(
    variants: list[PreprocessedImage], max_variants: int = MAX_VARIANTS_TO_SEND
) -> list[PreprocessedImage]:
    """Pick a small, complementary subset of variants to send to the vision
    model, prioritizing the enhanced and original renderings."""
    if not variants:
        return []
    by_label = {v.label: v for v in variants}
    ordered = [by_label[label] for label in PREFERRED_VARIANT_ORDER if label in by_label]
    remaining = [v for v in variants if v.label not in PREFERRED_VARIANT_ORDER]
    ordered.extend(remaining)
    return ordered[:max_variants]


def parse_model_response(raw: dict | str | None) -> VisionModelOutput:
    """Parse a provider's raw response into a VisionModelOutput.

    Never raises: malformed JSON, non-dict payloads, or schema-violating
    fields all fall back to a conservative "needs retake" output that
    explains what went wrong, rather than crashing the pipeline or
    fabricating a reading.
    """
    if raw is None:
        return _fallback_output("Vision model returned no response.")

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            return _fallback_output(f"Vision model response was not valid JSON: {exc}")

    if not isinstance(raw, dict):
        return _fallback_output("Vision model response was not a JSON object.")

    try:
        output = VisionModelOutput.model_validate(raw)
    except ValidationError as exc:
        return _fallback_output(
            f"Vision model response did not match the expected schema: {exc}"
        )

    # Defensive normalization in case the model drifts from the schema's
    # intended ranges/enums despite structured-output constraints.
    output.confidence = max(0.0, min(1.0, output.confidence))
    if output.image_quality not in (ImageQuality.ACCEPTABLE.value, ImageQuality.POOR.value):
        output.image_quality = ImageQuality.UNKNOWN.value

    return output


def _fallback_output(reason: str) -> VisionModelOutput:
    logger.warning("Falling back to conservative output: %s", reason)
    return VisionModelOutput(
        meter_detected=False,
        display_detected=False,
        raw_digits=None,
        reading=None,
        unit=None,
        confidence=0.0,
        image_quality=ImageQuality.UNKNOWN.value,
        needs_retake=True,
        reason=reason,
    )


def analyze_meter_image(image_bytes: bytes, provider: VisionProvider) -> MeterReadingResult:
    """Run the full MeterVision pipeline on a single uploaded image."""
    variants = build_preprocessed_variants(image_bytes)
    upload_variants = select_variants_for_upload(variants)

    images = [
        ImagePayload(data=v.encode_jpeg(), mime_type="image/jpeg", label=v.label)
        for v in upload_variants
    ]
    request = VisionRequest(prompt=build_meter_reading_prompt(), images=images)

    try:
        raw_response = provider.extract_reading(request)
    except ProviderError as exc:
        logger.warning("Vision provider error: %s", exc)
        output = _fallback_output(f"Vision provider error: {exc}")
        return validate_output(output)

    output = parse_model_response(raw_response)
    return validate_output(output)
