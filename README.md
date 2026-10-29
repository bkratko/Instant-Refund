# Instant Refund on Kaspa

A refund settlement layer that uses the Kaspa blockDAG as proof of finality.

Card and ACH refunds are approved in seconds but settle in 3–5 business days. Until they settle there is no shared, final record that the refund happened — the window where duplicate refunds, refund-then-chargeback fraud and disputes live. Retailers took back $706B in merchandise in 2025, and $100B of it was lost to returns fraud and abuse ([Appriss Retail, Feb 2026](https://www.businesswire.com/news/home/20260219293604/en/Appriss-Retail-Benchmark-Report-Uncovers-%24796B-in-Total-Retail-Loss)).

Instant Refund leaves the existing rails moving the money and anchors each refund to Kaspa as a signed transaction. The confirmed transaction ID becomes the refund's settlement reference: final in seconds, verifiable by every party, with no customer or card data on-chain.

## Architecture

```
 Merchant / PayFac ──► Refund API (FastAPI) ──► Postgres ledger ──► Compliance export
                                                     │                (refund → Kaspa txid)
                                               settlement_jobs
                                                     ▼
                     Settlement worker ──HMAC intent──► Rust Kaspa sidecar ──wRPC──► kaspad
                     (row-locked queue)   (60 s expiry)   holds the only key        (testnet-10)
```

| Component | Responsibility | Path |
| --- | --- | --- |
| Refund API | Accepts refunds (API key, idempotency), receipts, public proofs, compliance export | `app/main.py`, `app/routes/` |
| Ledger | Refunds, settlement events, settlement jobs | `app/db.py`, `app/store.py` |
| Commitment | `SHA-256` of the canonical refund record; only this hash goes on-chain | `app/commitment.py` |
| Settlement worker | Claims jobs with `FOR UPDATE SKIP LOCKED`, sends HMAC-signed intents, tracks confirmations | `app/worker.py` |
| Kaspa sidecar (Rust) | Binds the key to its address, builds/signs/submits the anchor tx, reports acceptance | `sidecar-kaspa/` |
| Demo console | Live merchant demo with in-browser proof verification | `demo/index.html`, `app/routes/demo.py` |

## How a refund reaches the DAG

1. **Record.** `POST /v1/refunds/instant` writes the refund, its commitment and a settlement job in one Postgres transaction. A unique `(merchant_id, idempotency_key)` index makes retries return the original refund.
2. **Claim.** The worker claims the job with `FOR UPDATE SKIP LOCKED`.
3. **Intent.** It posts `{refund_id, commitment_hex, expires_at_unix}` to the sidecar with `X-Signer-Auth: hex(HMAC-SHA256(secret, body))`. Intents expire after 60 s.
4. **Anchor.** The sidecar (Rust, `kaspa-wallet-core` 2.1) builds one transaction from the settlement address back to itself with payload `"IR1" ‖ commitment`, signs it with Schnorr, and submits it to kaspad over wRPC (Borsh). Only the network fee (~0.002 KAS) is spent.
5. **Finalize.** The worker polls the sidecar until the transaction is accepted and has `KASPA_CONFIRMATIONS_REQUIRED` DAA confirmations, then marks the refund `settled` with its txid and block DAA score.

## Verifying a refund without trusting us

`GET /v1/refunds/{id}/proof` returns the canonical record, its commitment and the Kaspa txid.

```python
import hashlib, json
h = hashlib.sha256(json.dumps(record, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
assert h == proof["commitment"]
# Open the txid on a Kaspa explorer: its payload must be hex("IR1") + h
```

## API

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/v1/refunds/instant` | `X-API-Key` | Create a refund (honours `Idempotency-Key`) |
| GET | `/v1/refunds/{refund_id}` | `X-API-Key` | Status, commitment, Kaspa txid |
| GET | `/v1/refunds/{refund_id}/proof` | public | Record + commitment + txid for independent verification |
| GET | `/v1/compliance/report` | `X-API-Key` | PCI DSS / SOX reconciliation per merchant and period (JSON or CSV) |

```json
POST /v1/refunds/instant
{"merchant_id": "M-8821", "order_id": "ORD-100245", "customer_id": "C-55710",
 "amount": "42.50", "currency": "USD", "acquirer_id": "ACQ-01", "flow_position": "post_auth"}
```

## Deploy (one droplet)

Ubuntu 24.04, 4 vCPU / 8 GB RAM / 160 GB disk. As root:

```bash
curl -fsSL https://raw.githubusercontent.com/bkratko/Instant-Refund/main/scripts/bootstrap.sh | bash
```

This installs Docker, generates secrets into `.env`, creates the settlement key **on the server** (`scripts/keygen.sh`), and starts kaspad (testnet-10), Postgres, the sidecar, the API and the worker with `docker compose`. Fund the printed `kaspatest:` address from a testnet faucet; anchors confirm once kaspad has synced. The demo console is served at `http://<droplet-ip>/` when `DEMO_MODE=true`.

## Stack

Python 3.12 · FastAPI · Pydantic 2 · PostgreSQL 16 · Rust 2021 · Tokio · Axum 0.7 · kaspa-wallet-core / kaspa-wrpc-client 2.1 · secp256k1 Schnorr · rusty-kaspa node · Docker Compose · DigitalOcean

## Author

Brian Kratko, Settlement Assurance LLC — brian@bmkdigitalsolutions.com
