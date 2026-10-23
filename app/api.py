from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime

from app.store import STORE
from app.db import db_cursor

app = FastAPI()

class InstantRefundRequest(BaseModel):
    merchant_id: str
    order_id: str
    customer_id: str
    amount: str
    reason: str | None = None
    idempotency_key: str | None = None

class InstantRefundResponse(BaseModel):
    refund_id: str
    signed_intent_id: str
    status: str

@app.post("/v1/refunds/instant", response_model=InstantRefundResponse)
def instant_refund(req: InstantRefundRequest):
    try:
        # 1) Create or fetch refund (idempotent)
        refund = STORE.create_refund(
            merchant_id=req.merchant_id,
            order_id=req.order_id,
            customer_id=req.customer_id,
            amount=req.amount,
            reason=req.reason,
            idempotency_key=req.idempotency_key,
        )

        # 2) Create signed_intent placeholder
        signed_intent_id = str(uuid4())
        now = datetime.utcnow()

        with db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO signed_intents (
                    signed_intent_id,
                    refund_id,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s);
                """,
                (
                    signed_intent_id,
                    refund.refund_id,
                    "PENDING",
                    now,
                ),
            )

        return InstantRefundResponse(
            refund_id=refund.refund_id,
            signed_intent_id=signed_intent_id,
            status="PENDING",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")