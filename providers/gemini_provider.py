"""Gemini implementation of the VisionProvider interface.

Uses the current unified `google-genai` SDK (package `google-genai`,
imported as `google.genai`), not the deprecated `google-generativeai`
package. The API key is read exclusively from configuration (which in
turn reads the environment) and is never hardcoded or logged.
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import settings
from models.meter_result import VisionModelOutput
from providers.base import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    VisionProvider,
    VisionRequest,
)

logger = logging.getLogger(__name__)


class GeminiProvider(VisionProvider):
    """Vision provider backed by Google's Gemini multimodal models."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is not set. Add it to a local .env file "
                "(see .env.example) — never hardcode it in source."
            )
        self.model = model or settings.GEMINI_MODEL
        self.timeout_seconds = timeout_seconds or settings.GEMINI_TIMEOUT_SECONDS

        http_options = types.HttpOptions(timeout=int(self.timeout_seconds * 1000))
        self._client = genai.Client(api_key=self.api_key, http_options=http_options)

    def extract_reading(self, request: VisionRequest) -> dict:
        contents = self._build_contents(request)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VisionModelOutput,
            temperature=0.1,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except genai_errors.ClientError as exc:
            raise self._map_client_error(exc) from exc
        except genai_errors.ServerError as exc:
            raise ProviderTimeoutError(f"Gemini server error: {exc}") from exc
        except genai_errors.APIError as exc:
            raise ProviderError(f"Gemini API error: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError(f"Gemini request timed out: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - last-resort network/SDK failure
            raise ProviderError(f"Unexpected error calling Gemini: {exc}") from exc

        return self._parse_response(response)

    def _build_contents(self, request: VisionRequest) -> list:
        parts = [types.Part.from_text(text=request.prompt)]
        for image in request.images:
            parts.append(
                types.Part.from_bytes(data=image.data, mime_type=image.mime_type)
            )
        return parts

    def _parse_response(self, response) -> dict:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, VisionModelOutput):
            return parsed.model_dump()

        text = getattr(response, "text", None)
        if not text:
            raise ProviderResponseError(
                "Gemini returned an empty response (possibly blocked by "
                "safety filters or an unsupported image)."
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                f"Gemini returned a response that was not valid JSON: {exc}"
            ) from exc

    def _map_client_error(self, exc: genai_errors.ClientError) -> ProviderError:
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return ProviderAuthError(f"Gemini rejected the API key: {exc}")
        if code == 429:
            return ProviderRateLimitError(f"Gemini rate limit exceeded: {exc}")
        if code == 408:
            return ProviderTimeoutError(f"Gemini request timed out: {exc}")
        return ProviderError(f"Gemini client error: {exc}")
