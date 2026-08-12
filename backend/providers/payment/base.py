"""Abstract payment provider.

Mirrors what a real gateway integration looks like: initiate a payment
attempt and get back a provider reference, then separately confirm the
outcome. Swapping in a real provider (e.g. Razorpay) later means
implementing this one interface — nothing in payment_service.py or the
billing logic changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentProvider(ABC):
    @abstractmethod
    def initiate(self, amount: Decimal, bill_id: int) -> str:
        """Start a payment attempt with the provider, returning a
        provider-specific reference id."""
        raise NotImplementedError

    @abstractmethod
    def confirm(self, provider_reference_id: str, *, simulate_success: bool = True) -> bool:
        """Confirm/simulate the outcome of a previously-initiated payment.
        Returns True if the payment succeeded."""
        raise NotImplementedError
