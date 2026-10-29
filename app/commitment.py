"""The refund commitment anchored on Kaspa.

commitment = SHA-256(canonical JSON of the refund record)

Only the 32-byte hash goes on-chain (payload = b"IR1" + commitment), so no merchant,
customer or card data is public. Anyone holding the record can recompute the hash and
compare it with the payload of the Kaspa transaction.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

PAYLOAD_TAG = b"IR1"
VERSION = 1


def canonical_record(refund_id: str, merchant_id: str, order_id: str, amount: Decimal | str,
                     currency: str, created_at_iso: str) -> dict:
    return {
        "v": VERSION,
        "refund_id": refund_id,
        "merchant_id": merchant_id,
        "order_id": order_id,
        "amount": f"{Decimal(str(amount)):.2f}",
        "currency": currency.upper(),
        "created_at": created_at_iso,
    }


def commitment_hex(record: dict) -> str:
    blob = json.dumps(record, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def payload_hex(commitment: str) -> str:
    return (PAYLOAD_TAG + bytes.fromhex(commitment)).hex()
