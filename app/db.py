
from __future__ import annotations
import re as _re

def _redact_url(url: str) -> str:
    return _re.sub(r'(:)[^:@]+(@)', r'\1***\2', url)

import os
from contextlib import contextmanager

# NOTE: Expect psycopg2-binary in requirements.txt (common on DO App Platform).
# If you are using psycopg (v3) instead, we can swap this cleanly later.
import psycopg2
import psycopg2.extras


def _db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (required for Postgres persistence)")
    return url


def get_conn():
    """Return a new DB connection. DATABASE_URL must be set in DigitalOcean App Platform."""
    return psycopg2.connect(_db_url(), cursor_factory=psycopg2.extras.RealDictCursor)


@contextmanager
def db_cursor():
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    """Create tables if they do not exist. Safe to call repeatedly."""
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS refunds (
              refund_id TEXT PRIMARY KEY,
              merchant_id TEXT NOT NULL,
              order_id TEXT NOT NULL,
              customer_id TEXT NOT NULL,
              amount TEXT NOT NULL,
              reason TEXT NULL,
              idempotency_key TEXT NULL,
              status TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              settlement_reference TEXT NULL
            );
            """
        )

        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS refunds_idem_unique
            ON refunds (merchant_id, idempotency_key)
            WHERE idempotency_key IS NOT NULL;
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settlement_events (
              id BIGSERIAL PRIMARY KEY,
              refund_id TEXT NOT NULL REFERENCES refunds(refund_id) ON DELETE CASCADE,
              event_type TEXT NOT NULL,
              payload_json JSONB NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS settlement_events_refund_id_idx
            ON settlement_events (refund_id);
            """
        )