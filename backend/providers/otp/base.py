"""Abstract OTP delivery provider.

Mirrors what a real SMS gateway call looks like: fire-and-forget, no
return value. The auth service generates and hashes the OTP itself and
only asks the provider to deliver the raw code — swapping in a real
provider (e.g. MSG91, Twilio) later means implementing this one interface,
nothing in backend/services/auth_service.py changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class OTPProvider(ABC):
    @abstractmethod
    def send_otp(self, mobile_number: str, otp_code: str) -> None:
        raise NotImplementedError
