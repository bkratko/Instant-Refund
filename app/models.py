from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RefundStatus(str, Enum):
    CREATED = "created"                    # recorded, anchor queued
    PENDING_SETTLEMENT = "pending_settlement"  # anchor broadcast, awaiting confirmations
    SETTLED = "settled"                    # anchor final on Kaspa
    FAILED = "failed"


class FlowPosition(str, Enum):
    """Where in the payment flow the confirmation was captured."""
    PRE_SETTLEMENT = "pre_settlement"
    POST_AUTH = "post_auth"
    POST_SETTLEMENT = "post_settlement"


class InstantRefundRequest(BaseModel):
    merchant_id: str = Field(..., max_length=128)
    order_id: str = Field(..., max_length=128)
    customer_id: str = Field(..., max_length=128)
    amount: Decimal = Field(..., gt=0, lt=Decimal("1000000000"))
    currency: str = Field("USD", min_length=3, max_length=3)
    reason: Optional[str] = Field(None, max_length=500)
    idempotency_key: Optional[str] = Field(None, max_length=128)
    acquirer_id: Optional[str] = Field(None, max_length=64)
    flow_position: FlowPosition = FlowPosition.POST_AUTH


class KaspaProof(BaseModel):
    network: str
    txid: Optional[str]
    payload_hex: str
    block_daa_score: Optional[int]
    explorer_url: Optional[str]


class RefundReceipt(BaseModel):
    refund_id: str
    status: RefundStatus
    merchant_id: str
    order_id: str
    amount: Decimal
    currency: str
    created_at: str
    settled_at: Optional[str]
    receipt_message: str
    commitment: str
    kaspa: KaspaProof


class RefundProof(BaseModel):
    """Everything a third party needs to verify the refund without trusting us."""
    record: dict
    commitment: str
    payload_hex: str
    kaspa: KaspaProof
    how_to_verify: str
