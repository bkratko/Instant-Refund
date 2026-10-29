"""Postgres access and schema. Postgres is the system of record."""
from __future__ import annotations

from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from app.config import DATABASE_URL


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


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


SCHEMA = """
CREATE TABLE IF NOT EXISTS refunds (
  refund_id            TEXT PRIMARY KEY,
  merchant_id          TEXT NOT NULL,
  order_id             TEXT NOT NULL,
  customer_id          TEXT NOT NULL,
  amount               NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  currency             TEXT NOT NULL DEFAULT 'USD',
  reason               TEXT NULL,
  idempotency_key      TEXT NULL,
  acquirer_id          TEXT NULL,
  flow_position        TEXT NOT NULL DEFAULT 'post_auth',
  status               TEXT NOT NULL,
  commitment           TEXT NOT NULL,
  kaspa_txid           TEXT NULL,
  kaspa_block_daa      BIGINT NULL,
  settled_at           TIMESTAMPTZ NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS refunds_idem_unique
  ON refunds (merchant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS refunds_merchant_created ON refunds (merchant_id, created_at);

CREATE TABLE IF NOT EXISTS settlement_events (
  id           BIGSERIAL PRIMARY KEY,
  refund_id    TEXT NOT NULL REFERENCES refunds(refund_id) ON DELETE CASCADE,
  event_type   TEXT NOT NULL,
  payload_json JSONB NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS settlement_events_refund ON settlement_events (refund_id);

CREATE TABLE IF NOT EXISTS settlement_jobs (
  job_id      BIGSERIAL PRIMARY KEY,
  refund_id   TEXT NOT NULL UNIQUE REFERENCES refunds(refund_id) ON DELETE CASCADE,
  state       TEXT NOT NULL DEFAULT 'queued',   -- queued | processing | broadcast | settled | failed_retryable | failed
  attempts    INT NOT NULL DEFAULT 0,
  next_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  locked_at   TIMESTAMPTZ NULL,
  last_error  TEXT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS settlement_jobs_ready ON settlement_jobs (state, next_run_at);
"""


def init_schema() -> None:
    with db_cursor() as (_, cur):
        cur.execute("SELECT pg_advisory_xact_lock(424242)")  # api + worker may start together
        cur.execute(SCHEMA)
