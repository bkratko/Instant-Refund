from __future__ import annotations
import os

import secrets
from typing import Optional
from fastapi import Header, HTTPException, status

async def require_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    valid_keys = [k.strip() for k in os.environ.get('API_KEYS','').split(',') if k.strip()]
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing X-API-Key header')
    for vk in valid_keys:
        if secrets.compare_digest(x_api_key.strip(), vk):
            return x_api_key.strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid API key')

from fastapi import APIRouter, Header, HTTPException
from decimal import Decimal

from ..models import InstantRefundRequest, RefundReceipt, RefundStatus, RefreshResponse
from ..store import STORE
from ..settlement.engine import process_pending_refunds


router = APIRouter(prefix="/v1/refunds", tags=["refunds"])


@router.post("/instant", response_model=RefundReceipt)
def create_instant_refund(
    payload: InstantRefundRequest,
    idempotency_key: str | None = Header(default=None, convert_underscores=False),
):
    # Header wins if present
    idem = idempotency_key or payload.idempotency_key

    # Normalize amount to 2dp string
    amt = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
    rec = STORE.create_refund(
        merchant_id=payload.merchant_id,
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        amount=f"{amt:.2f}",
        reason=payload.reason,
        idempotency_key=idem,
    )

    receipt_msg = (
        "Refund approved and initiated instantly. "
        "Customer should see a pending credit shortly; final settlement will confirm."
    )

    return RefundReceipt(
        refund_id=rec.refund_id,
        status=rec.status,
        merchant_id=rec.merchant_id,
        order_id=rec.order_id,
        customer_id=rec.customer_id,
        amount=rec.amount,
        created_at=rec.created_at,
        receipt_message=receipt_msg,
        settlement_reference=rec.settlement_reference,
    )


@router.get("/{refund_id}", response_model=RefundReceipt)
def get_refund(refund_id: str):
    rec = STORE.get_refund(refund_id)
    if not rec:
        raise HTTPException(status_code=404, detail="refund not found")

    if rec.status == RefundStatus.SETTLED:
        msg = "Refund settled successfully."
    elif rec.status == RefundStatus.PENDING_SETTLEMENT:
        msg = "Refund initiated; settlement pending."
    elif rec.status == RefundStatus.FAILED:
        msg = "Refund failed; review settlement logs."
    else:
        msg = "Refund created."

    return RefundReceipt(
        refund_id=rec.refund_id,
        status=rec.status,
        merchant_id=rec.merchant_id,
        order_id=rec.order_id,
        customer_id=rec.customer_id,
        amount=rec.amount,
        created_at=rec.created_at,
        receipt_message=msg,
        settlement_reference=rec.settlement_reference,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh():
    updated = process_pending_refunds()
    return RefreshResponse(updated=updated)