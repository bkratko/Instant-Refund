from __future__ import annotations

import os

from .base import SettlementProvider
from .kaspa import KaspaSettlementProvider
from .kaspa_hosted import HostedKaspaSettlementProvider


def get_settlement_provider() -> SettlementProvider:
    """
    Select settlement provider by environment.

    SETTLEMENT_PROVIDER=kaspa        -> local kaspad (dev)
    SETTLEMENT_PROVIDER=kaspa_hosted -> hosted RPC (prod / partner demo)
    """

    provider = os.getenv("SETTLEMENT_PROVIDER", "kaspa").lower()

    if provider == "kaspa":
        return KaspaSettlementProvider()

    if provider == "kaspa_hosted":
        return HostedKaspaSettlementProvider()

    raise RuntimeError(f"Unknown SETTLEMENT_PROVIDER: {provider}")
