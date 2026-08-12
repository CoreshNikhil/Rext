"""MOCK OTP provider — logs the code instead of sending a real SMS.

Not a production implementation. The router layer (not this provider)
separately decides whether to echo the OTP in the API response, gated on
settings.ENVIRONMENT == "development" — kept out of this interface so it
stays a realistic stand-in for a real gateway call.
"""

from __future__ import annotations

import logging

from backend.providers.otp.base import OTPProvider

logger = logging.getLogger("backend.providers.otp.mock")


class MockOTPProvider(OTPProvider):
    def send_otp(self, mobile_number: str, otp_code: str) -> None:
        logger.info("[MOCK OTP] %s: %s", mobile_number, otp_code)
