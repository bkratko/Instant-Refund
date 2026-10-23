from __future__ import annotations

import uuid
from typing import Dict

from app.models import RefundRequest, RefundResponse
from app.settlement.engine import SettlementEngine


# In-memory store for MVP
_REFUNDS: Dict[str, RefundResponse] = {}

_engine = SettlementEngine()


def create_refund(req: RefundRequest) -> RefundResponse:
    refund_id = uuid.uuid4().hex

    # Create base refund object
    refund = RefundResponse(
        refund_id=refund_id,
        status="created",
        amount=req.amount,
        currency=req.currency,
        original_tx_id=req.original_tx_id,
        merchant_id=req.merchant_id,
        rail=req.rail,
    )

    # If kaspa chosen, simulate "instant settlement" submission immediately
    if req.rail == "kaspa":
        settlement = _engine.settle(rail="kaspa", refund_id=refund_id, amount=req.amount, currency=req.currency)
        refund.status = "submitted"
        refund.settlement_ref = settlement.get("settlement_ref")
        refund.deposit_address = settlement.get("deposit_address")
        refund.network = settlement.get("network")

        # and for MVP, flip to confirmed immediately (deterministic behavior)
        refund.status = "confirmed"

    _REFUNDS[refund_id] = refund
    return refund


def get_refund(refund_id: str) -> RefundResponse:
    if refund_id not in _REFUNDS:
        raise KeyError(refund_id)
    return _REFUNDS[refund_id]
