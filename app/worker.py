"""Settlement worker.

Loop:
  1. Claim a queued job (FOR UPDATE SKIP LOCKED, so many workers can run safely).
  2. Send the refund's commitment to the Rust sidecar as an HMAC-signed intent that
     expires in 60 s. The sidecar signs and submits the Kaspa transaction; Python never
     sees the key.
  3. Poll broadcast anchors until they reach the required confirmations, then mark the
     refund settled with its Kaspa txid and block DAA score.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

import requests

from app import store
from app.config import SIDECAR_URL, signer_secret
from app.db import db_cursor, init_schema
from app.models import RefundStatus

log = logging.getLogger("worker")
POLL_SECONDS = 1.0
MAX_ATTEMPTS = 8
SECRET = b""


def _sign(body: bytes) -> str:
    return hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def claim_job():
    with db_cursor() as (_, cur):
        cur.execute("""
            WITH next_job AS (
              SELECT job_id FROM settlement_jobs
              WHERE state IN ('queued', 'failed_retryable') AND next_run_at <= NOW()
              ORDER BY next_run_at, job_id
              FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE settlement_jobs j SET state='processing', locked_at=NOW(), updated_at=NOW()
            FROM next_job WHERE j.job_id = next_job.job_id
            RETURNING j.*
        """)
        return cur.fetchone()


def anchor(job: dict) -> None:
    refund = store.get_refund(job["refund_id"])
    body = json.dumps({
        "refund_id": refund["refund_id"],
        "commitment_hex": refund["commitment"],
        "expires_at_unix": int(time.time()) + 60,
    }, separators=(",", ":"), sort_keys=True).encode()
    r = requests.post(f"{SIDECAR_URL}/v1/anchor", data=body, timeout=45,
                      headers={"Content-Type": "application/json", "X-Signer-Auth": _sign(body)})
    if r.status_code != 200:
        raise RuntimeError(f"sidecar {r.status_code}: {r.text[:500]}")
    receipt = r.json()

    with db_cursor() as (_, cur):
        cur.execute("UPDATE settlement_jobs SET state='broadcast', last_error=NULL, updated_at=NOW() WHERE job_id=%s",
                    (job["job_id"],))
        cur.execute("UPDATE refunds SET status=%s, kaspa_txid=%s, updated_at=NOW() WHERE refund_id=%s",
                    (RefundStatus.PENDING_SETTLEMENT.value, receipt["txid"], refund["refund_id"]))
        store.add_event(cur, refund["refund_id"], "BROADCAST", receipt)
    log.info("anchored refund=%s txid=%s fee=%s", refund["refund_id"], receipt["txid"], receipt["fee_sompi"])


def fail(job: dict, error: str) -> None:
    attempts = job["attempts"] + 1
    final = attempts >= MAX_ATTEMPTS
    with db_cursor() as (_, cur):
        cur.execute("""
            UPDATE settlement_jobs SET state=%s, attempts=%s, last_error=%s, updated_at=NOW(),
                   next_run_at = NOW() + make_interval(secs => %s)
            WHERE job_id=%s
        """, ("failed" if final else "failed_retryable", attempts, error[:2000], min(10 * 2 ** (attempts - 1), 300),
              job["job_id"]))
        if final:
            cur.execute("UPDATE refunds SET status=%s, updated_at=NOW() WHERE refund_id=%s",
                        (RefundStatus.FAILED.value, job["refund_id"]))
            store.add_event(cur, job["refund_id"], "FAILED", {"error": error[:500]})
    log.warning("job=%s attempt=%s error=%s", job["job_id"], attempts, error)


def confirm_broadcasts() -> None:
    with db_cursor() as (_, cur):
        cur.execute("""
            SELECT j.job_id, r.refund_id, r.kaspa_txid FROM settlement_jobs j JOIN refunds r USING (refund_id)
            WHERE j.state='broadcast' ORDER BY j.updated_at LIMIT 25
        """)
        rows = cur.fetchall()
    for row in rows:
        try:
            s = requests.get(f"{SIDECAR_URL}/v1/anchor/{row['kaspa_txid']}", timeout=10).json()
        except Exception as e:  # sidecar briefly down; try next loop
            log.warning("status check failed txid=%s: %s", row["kaspa_txid"], e)
            continue
        if s.get("final_"):
            with db_cursor() as (_, cur):
                cur.execute("UPDATE settlement_jobs SET state='settled', updated_at=NOW() WHERE job_id=%s",
                            (row["job_id"],))
                cur.execute("""UPDATE refunds SET status=%s, kaspa_block_daa=%s, settled_at=NOW(), updated_at=NOW()
                               WHERE refund_id=%s""",
                            (RefundStatus.SETTLED.value, s["block_daa_score"], row["refund_id"]))
                store.add_event(cur, row["refund_id"], "SETTLED", {
                    "kaspa_tx_id": row["kaspa_txid"], "block_daa_score": s["block_daa_score"],
                    "confirmations": s["confirmations"]})
            log.info("settled refund=%s txid=%s confs=%s", row["refund_id"], row["kaspa_txid"], s["confirmations"])


def main() -> None:
    global SECRET
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    SECRET = signer_secret()
    init_schema()
    log.info("settlement worker started; sidecar=%s", SIDECAR_URL)
    while True:
        job = None
        try:
            confirm_broadcasts()
            job = claim_job()
            if job:
                anchor(job)
                continue
        except Exception as e:
            if job:
                fail(job, str(e))
            else:
                log.exception("worker loop error")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
