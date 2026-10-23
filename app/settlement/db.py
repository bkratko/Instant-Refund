from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, Optional


DB_PATH = os.getenv("REFUNDS_DB_PATH", os.path.join(os.getcwd(), "refunds.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id TEXT PRIMARY KEY,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL,
                rail TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT,
                quote_json TEXT,
                settlement_json TEXT,
                settlement_ref TEXT,
                settlement_status_json TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                idempotency_key TEXT PRIMARY KEY,
                refund_id TEXT NOT NULL
            )
            """
        )


def get_refund_id_for_key(idempotency_key: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT refund_id FROM idempotency WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return row["refund_id"] if row else None


def set_idempotency_key(idempotency_key: str, refund_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO idempotency (idempotency_key, refund_id) VALUES (?, ?)",
            (idempotency_key, refund_id),
        )


def insert_refund(record: Dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO refunds (
                refund_id, amount, currency, rail, status, idempotency_key,
                quote_json, settlement_json, settlement_ref, settlement_status_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["refund_id"],
                record["amount"],
                record["currency"],
                record["rail"],
                record["status"],
                record.get("idempotency_key"),
                json.dumps(record.get("quote")) if record.get("quote") is not None else None,
                json.dumps(record.get("settlement")) if record.get("settlement") is not None else None,
                record.get("settlement_ref"),
                json.dumps(record.get("settlement_status")) if record.get("settlement_status") is not None else None,
                record["created_at"],
                record["updated_at"],
            ),
        )


def update_refund(refund_id: str, **fields: Any) -> None:
    if not fields:
        return

    allowed = {
        "status",
        "quote",
        "settlement",
        "settlement_ref",
        "settlement_status",
        "updated_at",
    }

    set_parts = []
    params = []

    for k, v in fields.items():
        if k not in allowed:
            continue

        if k in ("quote", "settlement", "settlement_status"):
            set_parts.append(f"{k}_json = ?")
            params.append(json.dumps(v) if v is not None else None)
        else:
            set_parts.append(f"{k} = ?")
            params.append(v)

    if not set_parts:
        return

    params.append(refund_id)

    with _connect() as conn:
        conn.execute(
            f"UPDATE refunds SET {', '.join(set_parts)} WHERE refund_id = ?",
            tuple(params),
        )


def get_refund(refund_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM refunds WHERE refund_id = ?",
            (refund_id,),
        ).fetchone()

    if not row:
        return None

    def _loads(s: Any) -> Any:
        if s is None:
            return None
        return json.loads(s)

    return {
        "refund_id": row["refund_id"],
        "amount": row["amount"],
        "currency": row["currency"],
        "rail": row["rail"],
        "status": row["status"],
        "idempotency_key": row["idempotency_key"],
        "quote": _loads(row["quote_json"]),
        "settlement": _loads(row["settlement_json"]),
        "settlement_ref": row["settlement_ref"],
        "settlement_status": _loads(row["settlement_status_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_pending_refunds() -> list[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT refund_id FROM refunds WHERE status = 'pending'"
        ).fetchall()
    ids = [r["refund_id"] for r in rows]
    return [get_refund(rid) for rid in ids if rid]  # type: ignore
