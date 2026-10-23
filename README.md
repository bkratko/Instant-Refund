# Instant Refund on Kaspa

A refund settlement layer that uses the Kaspa blockDAG as proof of finality.

Card and ACH refunds are approved in seconds but settle in 3–5 business days. Until they settle there is no shared, final record that the refund happened — the window where duplicate refunds, refund-then-chargeback fraud and disputes live. Retailers took back $706B in merchandise in 2025, and $100B of it was lost to returns fraud and abuse ([Appriss Retail, Feb 2026](https://www.businesswire.com/news/home/20260219293604/en/Appriss-Retail-Benchmark-Report-Uncovers-%24796B-in-Total-Retail-Loss)).

Instant Refund leaves the existing rails moving the money and anchors each refund to Kaspa as a signed transaction. The confirmed transaction ID becomes the refund's settlement reference: final in seconds, verifiable by every party, with no customer or card data on-chain.

## Architecture

```
 Merchant / POS ──► Refund API (FastAPI) ──► Postgres ledger ──► Compliance export
                                                │        │        (refund → Kaspa tx id)
                                    settlement jobs   pending intents
                                                ▼        ▼
 Settlement worker ──► Signer gateway (HMAC) ──► Rust Kaspa sidecar ──► kaspad (gRPC)
                                                 holds the only key
```

| Component | Responsibility | Path |
| --- | --- | --- |
| Refund API | Accepts refunds, enforces idempotency, returns receipts, serves compliance reports | `app/main.py`, `app/api.py`, `app/routes/` |
| Ledger | System of record: refunds, signed intents, settlement events, settlement jobs | `app/db.py`, `app/store.py`, `app/migrate.py` |
| Settlement worker | Claims jobs with row locks, builds intents, requests signatures, records broadcasts | `app/worker.py`, `app/settlement/` |
| Signer gateway | Authenticates intents with a shared secret, hands off to the sidecar | `app/signer_service.py` |
| Kaspa sidecar | Loads the settlement key, binds it to the mainnet address, signs and submits | `sidecar-kaspa/` |

The signing key never leaves the Rust sidecar. Python only passes HMAC-authenticated intents that expire after 60 seconds.

## Refund lifecycle

```
created ──job claimed──► pending_settlement ──confirmed──► settled
                               │   ▲
                               │   └── error: retry after 10 s backoff
                               └──unrecoverable──► failed
```

Every transition writes a row to `settlement_events`, so each refund carries its full audit history.

## How a refund reaches the DAG

1. **Idempotent create.** `POST /v1/refunds/instant`. A unique index on `(merchant_id, idempotency_key)` makes a retried request return the original refund.
2. **Job claim.** Workers drain `settlement_jobs` with `FOR UPDATE SKIP LOCKED`, so any number of them can run in parallel without touching the same refund.
3. **Signed intent.** The worker sends `{refund_id, network, from, to, amount_sompi, expires_at_unix, idempotency_key}` to the signer, authenticated with `HMAC-SHA256(secret, job_id | canonical_json(intent) | unsigned_tx_b64)`.
4. **Key binding.** At startup the sidecar derives the x-only Schnorr key, builds the mainnet address with `kaspa-addresses`, and refuses to bind if it doesn't match `KASPA_EXPECTED_FROM_ADDRESS` (`sidecar-kaspa/src/settlement_key.rs`).
5. **Sign and submit.** Each input is signed with `kaspa_consensus_core::sign::sign_input` (`SigHashType::All`) and submitted with kaspad `submit_transaction` (`sidecar-kaspa/src/kaspa/submit_signed.rs`).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/v1/refunds/instant` | Create a refund (idempotent), return a receipt |
| GET | `/v1/refunds/{refund_id}` | Status and receipt for one refund |
| POST | `/v1/refunds/refresh` | Advance pending refunds through the settlement engine |
| GET | `/v1/compliance/report` | PCI DSS / SOX reconciliation per merchant and period (JSON or CSV), keyed to Kaspa tx IDs. Requires `X-API-Key` |

```json
POST /v1/refunds/instant
{
  "merchant_id": "M-8821",
  "order_id": "ORD-100245",
  "customer_id": "C-55710",
  "amount": "42.50",
  "reason": "item returned",
  "idempotency_key": "ord-100245-r1",
  "acquirer_id": "ACQ-01",
  "flow_position": "post_auth"
}
```

## Status

| Layer | State |
| --- | --- |
| Refund API, Postgres ledger, job queue | Working |
| Compliance export | Working |
| Signer boundary (HMAC intents) | Working |
| Sidecar key load + mainnet address binding | Working |
| On-chain leg (UTXO selection, signing, `submit_transaction`) | Written in `submit_signed.rs`; wiring into the running sidecar is the current milestone. The worker currently exercises the path with a stand-in transaction (`build_unsigned_tx_stub`, `broadcast_stub_and_get_txid`). |

Next: real UTXO selection and change output, a public-key push in the signature script, sompi conversion from a quoted rate, confirmation tracking by txid, and the API-key check on `/v1/refunds/*`.

## Running locally

```bash
cp .env.example .env          # fill in values
pip install -r requirements.txt
uvicorn app.main:app --port 8080          # API
uvicorn app.signer_service:app --port 8001 # signer gateway
python -m app.worker                       # settlement worker

cd sidecar-kaspa && cargo build --release  # Linux; Windows builds a dev stub for key binding
```

Postgres tables are created at startup; run `python -m app.migrate` once for the acquirer and flow-position columns.

## Stack

Python 3.11 · FastAPI · Pydantic 1.x · PostgreSQL · psycopg2 · slowapi · Rust 2021 · Tokio · Axum 0.7 · secp256k1 0.29 · kaspa-addresses · kaspa-consensus-core · kaspa-txscript · tokio-postgres · Docker · DigitalOcean App Platform

## Author

Brian Kratko, Settlement Assurance LLC — brian@bmkdigitalsolutions.com
