from __future__ import annotations
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator

class RefundStatus(str, Enum):
    CREATED = "created"
    PENDING_SETTLEMENT = "pending_settlement"
    SETTLED = "settled"
    FAILED = "failed"



class FlowPosition(str, Enum):
    """Where in the payment flow the confirmation was captured."""
    PRE_SETTLEMENT  = "pre_settlement"
    POST_AUTH       = "post_auth"
    POST_SETTLEMENT = "post_settlement"
class InstantRefundRequest(BaseModel):
    """API request from merchant/POS to initiate an instant refund."""
    merchant_id: str = Field(..., description="Merchant identifier")
    order_id: str = Field(..., description="Merchant order identifier")
    customer_id: str = Field(..., description="Customer identifier")
    amount: Decimal = Field(..., gt=0, description="Refund amount (positive)")
    reason: Optional[str] = Field(default=None, description="Optional refund reason")
    idempotency_key: Optional[str] = Field(default=None, description="Client-provided idempotency key to prevent duplicate refunds")
    acquirer_id: Optional[str] = Field(default=None, description="Acquirer ID that processed the transaction")
    flow_position: FlowPosition = Field(default=FlowPosition.POST_AUTH, description="Where in payment flow confirmation was captured")


class RefundReceipt(BaseModel):
    """API response returned immediately after refund creation or lookup."""
    refund_id: str
    status: RefundStatus
    merchant_id: str
    order_id: str
    customer_id: str
    amount: Decimal
    created_at: str
    receipt_message: str
    settlement_reference: Optional[str] = None


class RefreshResponse(BaseModel):
    """Response from POST /v1/refunds/refresh indicating how many refunds advanced state."""
    updated: int