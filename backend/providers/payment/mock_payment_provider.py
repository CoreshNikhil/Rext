"""MOCK payment provider — no real money ever moves.

Not a production implementation. `confirm()` here is a stand-in for a
webhook/redirect callback a real gateway would send; the resident-facing
`/payments/{id}/mock-confirm` endpoint simulates that callback directly
since there's no real checkout page to redirect through yet.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from backend.providers.payment.base import PaymentProvider

logger = logging.getLogger("backend.providers.payment.mock")


class MockPaymentProvider(PaymentProvider):
    def initiate(self, amount: Decimal, bill_id: int) -> str:
        reference = f"MOCK-{uuid.uuid4()}"
        logger.info("[MOCK PAYMENT] initiated %s for bill_id=%s amount=%s", reference, bill_id, amount)
        return reference

    def confirm(self, provider_reference_id: str, *, simulate_success: bool = True) -> bool:
        logger.info("[MOCK PAYMENT] confirm %s -> %s", provider_reference_id, "SUCCESS" if simulate_success else "FAILED")
        return simulate_success
