from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any


class SettlementProvider(ABC):
    """
    Interface for settlement rails (Kaspa, Stripe, PayPal, bank, etc.)
    Keep it tiny and deterministic.
    """

    @abstractmethod
    def quote(self, amount: int, currency: str) -> Dict[str, Any]:
        """Return fee estimate + any metadata needed before settling."""
        raise NotImplementedError

    @abstractmethod
    def settle(self, refund_id: str, amount: int, currency: str) -> Dict[str, Any]:
        """Perform (or simulate) settlement and return settlement reference info."""
        raise NotImplementedError

    @abstractmethod
    def status(self, settlement_ref: str) -> Dict[str, Any]:
        """Return settlement status by reference."""
        raise NotImplementedError
