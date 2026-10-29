"""Public demo endpoints (enabled with DEMO_MODE=true). No API key; one fixed demo merchant."""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import store
from app.config import SIDECAR_URL
from app.models import InstantRefundRequest
from app.routes.refunds import _receipt

ENABLED = os.environ.get("DEMO_MODE", "false").lower() == "true"
DEMO_MERCHANT = "DEMO-MERCHANT"
PAGE = Path(__file__).resolve().parents[2] / "demo" / "index.html"

router = APIRouter(tags=["demo"], include_in_schema=False)


class DemoRefund(BaseModel):
    order_id: str = Field("", max_length=64)
    amount: Decimal = Field(..., gt=0, le=Decimal("500"))


@router.get("/")
def page():
    return FileResponse(PAGE)


@router.post("/demo/refund")
def demo_refund(body: DemoRefund, request: Request):
    req = InstantRefundRequest(
        merchant_id=DEMO_MERCHANT,
        order_id=body.order_id.strip() or f"ORD-{uuid.uuid4().hex[:8].upper()}",
        customer_id="DEMO-CUSTOMER",
        amount=body.amount,
        reason="demo",
    )
    return _receipt(store.create_refund(req, None))


@router.get("/demo/refund/{refund_id}")
def demo_get(refund_id: str):
    row = store.get_refund(refund_id)
    if not row or row["merchant_id"] != DEMO_MERCHANT:
        raise HTTPException(404, "not found")
    return _receipt(row)


@router.get("/demo/wallet")
def demo_wallet():
    try:
        return requests.get(f"{SIDECAR_URL}/v1/wallet", timeout=5).json()
    except Exception:
        raise HTTPException(503, "settlement signer unavailable")
