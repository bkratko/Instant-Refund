from __future__ import annotations

import os
import time
import uuid
from typing import Dict, Any

from .base import SettlementProvider


class KaspaSettlementProvider(SettlementProvider):
    """
    DEMO provider
    - quote(): stub
    - settle(): stub
    - status(): AUTO-CONFIRMS (for Instant Refund demo)
    """

    def __init__(self) -> None:
        self.network = os.getenv("KASPA_NETWORK", "mainnet")

    def quote(self, amount: int, currency: str) -> Dict[str, Any]:
        return {
            "rail": "kaspa",
            "network": self.network,
            "estimated_fee": 1,
            "currency": currency,
        }

    def settle(self, refund_id: str, amount: int, currency: str) -> Dict[str, Any]:
        settlement_ref = f"kaspa_{uuid.uuid4().hex}"
        return {
            "rail": "kaspa",
            "network": self.network,
            "settlement_ref": settlement_ref,
            "deposit_address": "kaspa:demo-address-not-used",
            "submitted_at": int(time.time()),
            "status": "submitted",
        }

    def status(self, settlement_ref: str) -> Dict[str, Any]:
        # DEMO: always confirm
        return {
            "settlement_ref": settlement_ref,
            "state": "confirmed",
            "confirmations": 1,
            "confirmations_required": 1,
        }
