from __future__ import annotations

import os
import time
import uuid
from typing import Dict, Any

import requests

from .base import SettlementProvider


class HostedKaspaSettlementProvider(SettlementProvider):
    """
    Ocean-hosted Kaspa provider.

    - No local node
    - No wallet custody
    - Real chain reads (status, health)
    - Stubbed settlement (safe MVP)

    Engine-agnostic and partner-safe.
    """

    def __init__(self) -> None:
        self.network = os.getenv("KASPA_NETWORK", "mainnet")
        self.confirmations_required = int(
            os.getenv("KASPA_CONFIRMATIONS_REQUIRED", "1")
        )

        self.base_url = os.getenv("KASPA_HOSTED_BASE_URL")
        self.api_key = os.getenv("KASPA_HOSTED_API_KEY")

        if not self.base_url:
            raise RuntimeError("KASPA_HOSTED_BASE_URL not set")

        self.base_url = self.base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ---------- PARTNER CONFIDENCE ----------

    def health(self) -> Dict[str, Any]:
        try:
            resp = requests.get(
                f"{self.base_url}/health",
                headers=self._headers(),
                timeout=3,
            )
            resp.raise_for_status()
        except Exception as e:
            return {
                "rail": "kaspa",
                "provider": "ocean",
                "ok": False,
                "error": str(e),
            }

        return {
            "rail": "kaspa",
            "provider": "ocean",
            "ok": True,
            "network": self.network,
        }

    # ---------- MVP SAFE ----------

    def quote(self, amount: int, currency: str) -> Dict[str, Any]:
        return {
            "rail": "kaspa",
            "network": self.network,
            "estimated_fee": 1,
            "currency": currency,
        }

    def settle(self, refund_id: str, amount: int, currency: str) -> Dict[str, Any]:
        """
        MVP stub — no funds are broadcast.
        Produces a realistic settlement reference.
        """
        settlement_ref = f"kaspa_{uuid.uuid4().hex}"

        return {
            "rail": "kaspa",
            "network": self.network,
            "settlement_ref": settlement_ref,
            "deposit_address": "kaspa:ocean-demo-address",
            "submitted_at": int(time.time()),
            "status": "submitted",
        }

    # ---------- REAL CHAIN READ ----------

    def status(self, settlement_ref: str) -> Dict[str, Any]:
        """
        Query Ocean-hosted RPC/indexer for transaction status.
        settlement_ref format: kaspa_<txid>
        """

        txid = settlement_ref.replace("kaspa_", "")

        try:
            resp = requests.get(
                f"{self.base_url}/tx/{txid}",
                headers=self._headers(),
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as e:
            return {
                "settlement_ref": settlement_ref,
                "state": "rpc_error",
                "error": str(e),
            }

        payload = resp.json()

        confirmations = payload.get("confirmations", 0)
        state = (
            "confirmed"
            if confirmations >= self.confirmations_required
            else "pending"
        )

        return {
            "settlement_ref": settlement_ref,
            "txid": txid,
            "state": state,
            "confirmations": confirmations,
            "confirmations_required": self.confirmations_required,
        }
