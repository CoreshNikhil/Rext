"""Abstract vision provider interface.

Any cloud (or local) vision-capable model can be plugged in by implementing
this interface. The rest of the application only depends on this contract,
never on a specific provider's SDK, so a new provider can be added later
without touching detection/validation/UI code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    """Base class for all provider-level failures."""


class ProviderConfigError(ProviderError):
    """Raised when a provider is missing required configuration (e.g. API key)."""


class ProviderAuthError(ProviderError):
    """Raised when the provider rejects our credentials."""


class ProviderRateLimitError(ProviderError):
    """Raised when the provider throttles or quota-limits the request."""


class ProviderTimeoutError(ProviderError):
    """Raised when the provider does not respond in time."""


class ProviderResponseError(ProviderError):
    """Raised when the provider responds but the payload is unusable
    (malformed JSON, missing required fields, empty response, etc.)."""


@dataclass
class ImagePayload:
    """A single image variant to send to the vision model."""

    data: bytes
    mime_type: str
    label: str = "image"


@dataclass
class VisionRequest:
    """Everything a provider needs to perform one meter-reading extraction."""

    prompt: str
    images: list[ImagePayload] = field(default_factory=list)


class VisionProvider(ABC):
    """Contract every vision backend (Gemini, future providers) must satisfy."""

    @abstractmethod
    def extract_reading(self, request: VisionRequest) -> dict:
        """Send the request to the vision model and return the parsed JSON
        response as a plain dict.

        Implementations must raise one of the ProviderError subclasses on
        failure rather than letting SDK-specific exceptions leak out, so
        callers can handle failures generically.
        """
        raise NotImplementedError
