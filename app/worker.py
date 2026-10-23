import logging

logger = logging.getLogger(__name__)
import os
import time
import base64
import json
import hmac
import hashlib
import requests
from datetime import datetime, timezone

from app.db import connect, init_schema_if_possible

POLL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "2"))

SIGNER_URL = os.getenv("SIGNER_URL", "http://instant-refund-signer:8080")
SIGNER_SHARED_SECRET = os.getenv("SIGNER_SHARED_SECRET", "")

KASPA_NETWORK = os.getenv("KASPA_NETWORK", "testnet")
KASPA_REFUND_FROM_ADDRESS = os.getenv("KASPA_REFUND_FROM_ADDRESS", "")
KASPA_FEE_ATOMIC = int(os.getenv("KASPA_FEE_ATOMIC", "1000"))  # placeholder

def _hmac_hex(payload_bytes: bytes) -> str:
    if not SIGNER_SHARED_SECRET:
        raise RuntimeError("SIGNER_SHARED_SECRET is not set")
    return hmac.new(SIGNER_SHARED_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

def claim_next_job():
    sql = """
    WITH next_job AS (
      SELECT job_id
      FROM settlement_jobs
      WHERE state IN ('queued', 'failed_retryable')
        AND next_run_at <= NOW()
      ORDER BY next_run_at ASC, job_id ASC
      FOR UPDATE SKIP LOCKED
      LIMIT 1
    )
    UPDATE settlement_jobs j
    SET state = 'processing',
        locked_at = NOW(),
        updated_at = NOW()
    FROM next_job
    WHERE j.job_id = next_job.job_id
    RETURNING j.*;
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
        conn.commit()
        return row

def load_refund(refund_id: str):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM refunds WHERE refund_id=%s", (refund_id,))
            row = cur.fetchone()
        return row

def mark_retryable(job_id: int, error: str, backoff_seconds: int = 10):
    sql = """
    UPDATE settlement_jobs
    SET state = 'failed_retryable',
        attempts = attempts + 1,
        next_run_at = NOW() + (%s || ' seconds')::interval,
        last_error = %s,
        updated_at = NOW()
    WHERE job_id = %s;
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (backoff_seconds, error[:2000], job_id))
        conn.commit()

def mark_broadcast(job_id: int, refund_id: str, txid: str):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE settlement_jobs
                SET state = 'broadcast',
                    last_error = NULL,
                    updated_at = NOW()
                WHERE job_id = %s;
                """,
                (job_id,)
            )
            cur.execute(
                """
                UPDATE refunds
                SET settlement_state = 'broadcast',
                    txid = %s,
                    last_error = NULL
                WHERE refund_id = %s;
                """,
                (txid, refund_id)
            )
        conn.commit()

def build_unsigned_tx_stub(refund_row: dict) -> str:
    """
    v1 stub unsigned tx:
    We encode a canonical JSON payload as base64 to validate the signer boundary flow.
    Next step replaces this with real kaspad UTXO selection + tx bytes.
    """
    if not KASPA_REFUND_FROM_ADDRESS:
        raise RuntimeError("KASPA_REFUND_FROM_ADDRESS is not set")
    # In v1 stub we don't have a real customer address in DB yet. We'll add it later.
    to_address = os.getenv("KASPA_REFUND_TEST_TO_ADDRESS", "")
    if not to_address:
        raise RuntimeError("KASPA_REFUND_TEST_TO_ADDRESS is not set")

    amount_atomic = int(float(refund_row["amount"]) * 100000000)  # placeholder conversion
    payload = {
        "network": KASPA_NETWORK,
        "from": KASPA_REFUND_FROM_ADDRESS,
        "to": to_address,
        "amount_atomic": amount_atomic,
        "fee_atomic": KASPA_FEE_ATOMIC,
        "refund_id": refund_row["refund_id"],
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")

def sign_with_signer(job_id: int, refund_row: dict, unsigned_b64: str) -> str:
    # create tx intent
    now = int(time.time())
    intent = {
        "refund_id": refund_row["refund_id"],
        "network": KASPA_NETWORK,
        "from_address": KASPA_REFUND_FROM_ADDRESS,
        "to_address": os.getenv("KASPA_REFUND_TEST_TO_ADDRESS", ""),
        "amount_atomic": int(float(refund_row["amount"]) * 100000000),
        "expires_at_unix": now + 60,
        "idempotency_key": refund_row["refund_id"]
    }

    body = {
        "job_id": int(job_id),
        "tx_intent": intent,
        "unsigned_tx_bytes_b64": unsigned_b64
    }

    canonical = (str(job_id) + "|" + json.dumps(intent, separators=(",", ":"), sort_keys=True) + "|" + unsigned_b64).encode("utf-8")
    auth = _hmac_hex(canonical)

    r = requests.post(
        f"{SIGNER_URL}/internal/sign",
        json=body,
        headers={"X-Signer-Auth": auth},
        timeout=10
    )
    if r.status_code != 200:
        raise RuntimeError(f"signer error {r.status_code}: {r.text}")

    data = r.json()
    return data["signed_tx_bytes_b64"]

def broadcast_stub_and_get_txid(signed_b64: str, job_id: int) -> str:
    """
    Stub txid: hash the signed payload to produce deterministic txid-like string.
    Next step replaces with kaspad submit_transaction and returns real txid.
    """
    h = hashlib.sha256(signed_b64.encode("utf-8")).hexdigest()
    return "txid_stub_" + h[:32]

def main():
    init_schema_if_possible()
    logger.info("instant-refund-worker: started (delegated custody mode)")

    while True:
        job = None
        try:
            job = claim_next_job()
            if not job:
                time.sleep(POLL_SECONDS)
                continue

            refund_id = job["refund_id"]
            refund = load_refund(refund_id)
            if not refund:
                raise RuntimeError(f"refund not found: {refund_id}")

            unsigned_b64 = build_unsigned_tx_stub(refund)
            signed_b64 = sign_with_signer(job["job_id"], refund, unsigned_b64)
            txid = broadcast_stub_and_get_txid(signed_b64, job["job_id"])

            mark_broadcast(job["job_id"], refund_id, txid)
            logger.info(f"broadcasted (stub): job_id={job['job_id']} refund_id={refund_id} txid={txid}")

        except Exception as e:
            if job and "job_id" in job:
                mark_retryable(job["job_id"], str(e), backoff_seconds=10)
            else:
                logger.info(f"worker error (no job claimed): {e}")
            time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
