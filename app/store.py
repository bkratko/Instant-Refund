"""Ledger operations. A refund and its settlement job are written in one transaction."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.commitment import canonical_record, commitment_hex
from app.db import db_cursor
from app.models import InstantRefundRequest, RefundStatus

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def iso(ts: Optional[datetime]) -> Optional[str]:
    return ts.astimezone(timezone.utc).strftime(TS_FMT) if ts else None


def record_for(row: dict) -> dict:
    return canonical_record(row["refund_id"], row["merchant_id"], row["order_id"], row["amount"],
                            row["currency"], iso(row["created_at"]))


def create_refund(req: InstantRefundRequest, idempotency_key: Optional[str]) -> dict:
    """Create the refund + its anchor job. A repeated idempotency key returns the original."""
    with db_cursor() as (_, cur):
        if idempotency_key:
            cur.execute("SELECT * FROM refunds WHERE merchant_id=%s AND idempotency_key=%s",
                        (req.merchant_id, idempotency_key))
            existing = cur.fetchone()
            if existing:
                return existing

        refund_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        amount = req.amount.quantize(req.amount.__class__("0.01"))
        commitment = commitment_hex(canonical_record(
            refund_id, req.merchant_id, req.order_id, amount, req.currency, created_at.strftime(TS_FMT)))

        cur.execute(
            """
            INSERT INTO refunds (refund_id, merchant_id, order_id, customer_id, amount, currency, reason,
                                 idempotency_key, acquirer_id, flow_position, status, commitment, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (merchant_id, idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
            RETURNING *
            """,
            (refund_id, req.merchant_id, req.order_id, req.customer_id, amount, req.currency.upper(), req.reason,
             idempotency_key, req.acquirer_id, req.flow_position.value, RefundStatus.CREATED.value, commitment,
             created_at, created_at),
        )
        row = cur.fetchone()
        if row is None:  # lost an idempotency race; return the winner
            cur.execute("SELECT * FROM refunds WHERE merchant_id=%s AND idempotency_key=%s",
                        (req.merchant_id, idempotency_key))
            return cur.fetchone()

        cur.execute("INSERT INTO settlement_jobs (refund_id) VALUES (%s)", (refund_id,))
        cur.execute("INSERT INTO settlement_events (refund_id, event_type, payload_json) VALUES (%s,'CREATED',%s)",
                    (refund_id, json.dumps({"commitment": commitment})))
        return row


def get_refund(refund_id: str) -> Optional[dict]:
    with db_cursor() as (_, cur):
        cur.execute("SELECT * FROM refunds WHERE refund_id=%s", (refund_id,))
        return cur.fetchone()


def add_event(cur, refund_id: str, event_type: str, payload: dict[str, Any]) -> None:
    cur.execute("INSERT INTO settlement_events (refund_id, event_type, payload_json) VALUES (%s,%s,%s)",
                (refund_id, event_type, json.dumps(payload)))
