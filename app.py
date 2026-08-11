"""MeterVision — Streamlit prototype UI.

Upload a utility meter photograph, run it through the MeterVision pipeline
(preprocessing -> vision model -> validation), and show a structured,
trustworthy result. The Gemini API key is read only from server-side
configuration (config.settings) and is never displayed or logged here.
"""

from __future__ import annotations

import logging

import streamlit as st
from PIL import Image
import io

from config import settings
from models.meter_result import MeterReadingResult, ReviewStatus
from providers.base import ProviderConfigError, ProviderError
from providers.gemini_provider import GeminiProvider
from vision.detection import analyze_meter_image
from vision.preprocessing import validate_image_upload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("metervision.app")

st.set_page_config(page_title="MeterVision", page_icon="🔢", layout="centered")


@st.cache_resource(show_spinner=False)
def get_provider():
    """Instantiate the configured vision provider once per server process.
    Raises ProviderConfigError (caught by the caller) if GEMINI_API_KEY is
    missing — the key itself is never returned or displayed."""
    if settings.VISION_PROVIDER == "gemini":
        return GeminiProvider()
    raise ProviderConfigError(f"Unknown VISION_PROVIDER '{settings.VISION_PROVIDER}'.")


def render_accepted(result: MeterReadingResult) -> None:
    st.markdown(f"**Meter detected:** {'YES' if result.meter_detected else 'NO'}")
    st.markdown(f"**Display detected:** {'YES' if result.display_detected else 'NO'}")

    st.markdown("### Reading")
    unit_suffix = f" {result.unit}" if result.unit else ""
    st.markdown(f"## {result.reading}{unit_suffix}")

    st.markdown("### Confidence")
    st.progress(min(max(result.confidence, 0.0), 1.0))
    st.markdown(f"{result.confidence * 100:.0f}%")

    st.success(f"✓ Status: {result.status.value.replace('_', ' ').title()}")


def render_needs_attention(result: MeterReadingResult) -> None:
    st.markdown(f"**Meter detected:** {'YES' if result.meter_detected else 'NO'}")
    st.markdown(f"**Display detected:** {'YES' if result.display_detected else 'NO'}")

    if result.reading:
        st.markdown("### Reading (unconfirmed — needs review)")
        unit_suffix = f" {result.unit}" if result.unit else ""
        st.markdown(f"## {result.reading}{unit_suffix}")
        st.markdown(f"Confidence: {result.confidence * 100:.0f}%")

    st.warning("⚠ Reading could not be reliably determined.")

    reason = result.reason or "The model could not confidently read the meter display."
    st.markdown("**Reason:**")
    st.markdown(reason)

    if result.validation_notes:
        with st.expander("Validation details"):
            for note in result.validation_notes:
                st.markdown(f"- {note}")

    st.markdown(
        "**Please take another photograph with:**\n"
        "- the complete digit display visible\n"
        "- less glare (avoid direct flash on glass covers)\n"
        "- better, even lighting\n"
        "- the camera closer to the meter and held level\n"
        "- the camera focused (hold steady, avoid motion blur)"
    )


def render_result(result: MeterReadingResult) -> None:
    if result.status == ReviewStatus.ACCEPTED:
        render_accepted(result)
    else:
        render_needs_attention(result)

    with st.expander("Raw structured result (debug)"):
        st.json(result.model_dump())


def main() -> None:
    st.title("MeterVision")
    st.caption("AI-powered utility meter reading extraction — prototype v0.1")

    st.write("Upload a photograph of a gas, water, or electricity meter.")

    uploaded_file = st.file_uploader(
        "Upload Image",
        type=["jpg", "jpeg", "png", "webp", "bmp"],
    )

    image_bytes: bytes | None = None
    if uploaded_file is not None:
        image_bytes = uploaded_file.getvalue()
        try:
            validate_image_upload(image_bytes)
        except ValueError as exc:
            st.error(f"Invalid image: {exc}")
            image_bytes = None
        else:
            try:
                preview = Image.open(io.BytesIO(image_bytes))
                st.image(preview, caption="Uploaded image", use_container_width=True)
            except Exception:
                st.warning("Could not render a preview of this image, but it may still be analyzable.")

    analyze_clicked = st.button("Analyze Meter", type="primary", disabled=image_bytes is None)

    if analyze_clicked and image_bytes is not None:
        with st.spinner("Analyzing meter image..."):
            try:
                provider = get_provider()
            except ProviderConfigError as exc:
                st.error(
                    "MeterVision is not configured with a vision provider API key. "
                    "Set GEMINI_API_KEY in your .env file (see .env.example) and restart "
                    f"the app. ({exc})"
                )
                return
            except Exception as exc:  # noqa: BLE001 - surface unexpected provider init failures safely
                logger.exception("Failed to initialize vision provider")
                st.error(f"Could not initialize the vision provider: {exc}")
                return

            try:
                result = analyze_meter_image(image_bytes, provider)
            except ProviderError as exc:
                st.error(f"The vision provider failed to process this image: {exc}")
                return
            except Exception as exc:  # noqa: BLE001 - never crash the UI on unexpected failures
                logger.exception("Unexpected error during meter analysis")
                st.error(f"Something went wrong while analyzing this image: {exc}")
                return

        render_result(result)


if __name__ == "__main__":
    main()
