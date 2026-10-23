from __future__ import annotations

import os

from ..store import STORE
from ..models import RefundStatus


def _kaspa_enabled() -> bool:
    # Task #3 will require treasury credentials. Keep app boot-safe until configured.
    return bool(os.getenv("KASPA_TREASURY_MNEMONIC") or os.getenv("KASPA_TREASURY_PRIVATE_KEY"))


def process_pending_refunds(limit: int = 50) -> int:
    """
    Task #2 behavior:
      - Postgres is authoritative
      - Prove persistence + state transition

    Task #3 behavior (next):
      - Build/sign tx from treasury key (testnet)
      - Broadcast to node
      - Persist txid as settlement_reference
      - Confirmations -> SETTLED
      - Failures -> FAILED with retry policy + event log
    """
    updated = 0
    recs = STORE.list_pending_for_settlement(limit=limit)

    for rec in recs:
        # For now: keep simple and deterministic.
        if rec.status == RefundStatus.CREATED:
            if not _kaspa_enabled():
                # Do NOT change state if Kaspa treasury isn't configured yet.
                STORE.add_settlement_event(rec.refund_id, "KASPA_NOT_CONFIGURED", {"note": "set KASPA_TREASURY_* env vars to enable Task #3 broadcast"})
                continue

            # Placeholder hook: mark pending and record event.
            # Next commit replaces this with real kaspa broadcast + txid persistence.
            STORE.mark_pending_settlement(rec.refund_id, settlement_reference=None)
            STORE.add_settlement_event(rec.refund_id, "MARKED_PENDING", {"note": "task3 hook armed; next commit will broadcast kaspa tx"})
            updated += 1

    return updated