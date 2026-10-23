from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, List

from .db import db_cursor, init_schema
from .models import RefundStatus


@dataclass
class RefundRecord:
    refund_id: str
    merchant_id: str
    order_id: str
    customer_id: str
    amount: str
    reason: Optional[str]
    idempotency_key: Optional[str]
    status: RefundStatus
    created_at: str
    updated_at: str
    settlement_reference: Optional[str]


class Store:
    def __init__(self) -> None:
        # Ensure schema exists at import time (DO startup hooks can be unreliable).
        init_schema()

    def _row_to_record(self, row: dict) -> RefundRecord:
        return RefundRecord(
            refund_id=row["refund_id"],
            merchant_id=row["merchant_id"],
            order_id=row["order_id"],
            customer_id=row["customer_id"],
            amount=row["amount"],
            reason=row.get("reason"),
            idempotency_key=row.get("idempotency_key"),
            status=RefundStatus(row["status"]),
            created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
            settlement_reference=row.get("settlement_reference"),
        )

    def create_refund(
        self,
        merchant_id: str,
        order_id: str,
        customer_id: str,
        amount: str,
        reason: Optional[str],
        idempotency_key: Optional[str],
    ) -> RefundRecord:
        """Create refund record. If idempotency hits, return existing row."""
        with db_cursor() as (conn, cur):
            if idempotency_key:
                cur.execute(
                    """
                    SELECT * FROM refunds
                    WHERE merchant_id = %s AND idempotency_key = %s
                    LIMIT 1;
                    """,
                    (merchant_id, idempotency_key),
                )
                existing = cur.fetchone()
                if existing:
                    return self._row_to_record(existing)

            refund_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            cur.execute(
                """
                INSERT INTO refunds (
                  refund_id, merchant_id, order_id, customer_id, amount, reason,
                  idempotency_key, status, created_at, updated_at, settlement_reference
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,
                  %s,%s,%s,%s,%s
                )
                RETURNING *;
                """,
                (
                    refund_id,
                    merchant_id,
                    order_id,
                    customer_id,
                    amount,
                    reason,
                    idempotency_key,
                    RefundStatus.CREATED.value,
                    now,
                    now,
                    None,
                ),
            )
            row = cur.fetchone()

            # Initial event log
            cur.execute(
                """
                INSERT INTO settlement_events (refund_id, event_type, payload_json)
                VALUES (%s, %s, %s);
                """,
                (refund_id, "CREATED", json.dumps({"note": "refund created"})),
            )

            return self._row_to_record(row)

    def get_refund(self, refund_id: str) -> Optional[RefundRecord]:
        with db_cursor() as (conn, cur):
            cur.execute("SELECT * FROM refunds WHERE refund_id = %s LIMIT 1;", (refund_id,))
            row = cur.fetchone()
            return self._row_to_record(row) if row else None

    def list_pending_for_settlement(self, limit: int = 50) -> List[RefundRecord]:
        with db_cursor() as (conn, cur):
            cur.execute(
                """
                SELECT * FROM refunds
                WHERE status IN (%s, %s)
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (RefundStatus.CREATED.value, RefundStatus.PENDING_SETTLEMENT.value, limit),
            )
            rows = cur.fetchall() or []
            return [self._row_to_record(r) for r in rows]

    def mark_pending_settlement(self, refund_id: str, settlement_reference: Optional[str]) -> None:
        with db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE refunds
                SET status = %s,
                    settlement_reference = COALESCE(%s, settlement_reference),
                    updated_at = NOW()
                WHERE refund_id = %s;
                """,
                (RefundStatus.PENDING_SETTLEMENT.value, settlement_reference, refund_id),
            )

    def mark_settled(self, refund_id: str) -> None:
        with db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE refunds
                SET status = %s,
                    updated_at = NOW()
                WHERE refund_id = %s;
                """,
                (RefundStatus.SETTLED.value, refund_id),
            )

    def mark_failed(self, refund_id: str, reason: str) -> None:
        with db_cursor() as (conn, cur):
            cur.execute(
                """
                UPDATE refunds
                SET status = %s,
                    updated_at = NOW()
                WHERE refund_id = %s;
                """,
                (RefundStatus.FAILED.value, refund_id),
            )
            cur.execute(
                """
                INSERT INTO settlement_events (refund_id, event_type, payload_json)
                VALUES (%s, %s, %s);
                """,
                (refund_id, "FAILED", json.dumps({"reason": reason})),
            )

    def add_settlement_event(self, refund_id: str, event_type: str, payload: Optional[dict[str, Any]] = None) -> None:
        with db_cursor() as (conn, cur):
            cur.execute(
                """
                INSERT INTO settlement_events (refund_id, event_type, payload_json)
                VALUES (%s, %s, %s);
                """,
                (refund_id, event_type, json.dumps(payload or {})),
            )


STORE = Store()