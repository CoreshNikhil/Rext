"""Central configuration for MeterVision.

All values are read from the environment (via .env in local dev). Nothing
in this module should ever contain a hardcoded secret.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# override=True so editing .env while a long-running process (e.g. the
# Streamlit server) is already up takes effect on the next script rerun,
# instead of the first (possibly empty) value staying cached for the
# lifetime of the process.
load_dotenv(override=True)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- Vision provider ---------------------------------------------------
VISION_PROVIDER: str = os.getenv("VISION_PROVIDER", "gemini")

GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_TIMEOUT_SECONDS: float = _get_float("GEMINI_TIMEOUT_SECONDS", 30.0)

# --- Validation ----------------------------------------------------------
CONFIDENCE_THRESHOLD: float = _get_float("CONFIDENCE_THRESHOLD", 0.85)

# Sanity bounds for the number of digits a mechanical utility meter display
# realistically shows. Not a hard schema — just a guard rail against
# obviously wrong extractions (e.g. an 11-digit serial number).
MIN_DIGIT_COUNT: int = _get_int("MIN_DIGIT_COUNT", 4)
MAX_DIGIT_COUNT: int = _get_int("MAX_DIGIT_COUNT", 10)

# --- Image handling --------------------------------------------------------
MAX_IMAGE_DIMENSION_PX: int = _get_int("MAX_IMAGE_DIMENSION_PX", 2000)
MAX_UPLOAD_SIZE_MB: float = _get_float("MAX_UPLOAD_SIZE_MB", 15.0)

SUPPORTED_IMAGE_FORMATS = {"JPEG", "JPG", "PNG", "WEBP", "BMP"}
