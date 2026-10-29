from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app import store
from app.commitment import payload_hex
from app.config import API_KEYS, EXPLORER_TX_URL, KASPA_NETWORK
from app.models import InstantRefundRequest, KaspaProof, RefundProof, RefundReceipt, RefundStatus


async def require_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if x_api_key and any(secrets.compare_digest(x_api_key.strip(), k) for k in API_KEYS):
        return x_api_key.strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid X-API-Key")


router = APIRouter(prefix="/v1/refunds", tags=["refunds"])

MESSAGES = {
    RefundStatus.CREATED: "Refund recorded. Anchoring to Kaspa now.",
    RefundStatus.PENDING_SETTLEMENT: "Refund anchored on Kaspa; awaiting confirmations.",
    RefundStatus.SETTLED: "Refund final: anchored and confirmed on Kaspa.",
    RefundStatus.FAILED: "Refund anchoring failed; see settlement events.",
}


def _proof(row: dict) -> KaspaProof:
    txid = row.get("kaspa_txid")
    return KaspaProof(
        network=KASPA_NETWORK,
        txid=txid,
        payload_hex=payload_hex(row["commitment"]),
        block_daa_score=row.get("kaspa_block_daa"),
        explorer_url=EXPLORER_TX_URL.format(txid=txid) if txid else None,
    )


def _receipt(row: dict) -> RefundReceipt:
    st = RefundStatus(row["status"])
    return RefundReceipt(
        refund_id=row["refund_id"], status=st, merchant_id=row["merchant_id"], order_id=row["order_id"],
        amount=row["amount"], currency=row["currency"], created_at=store.iso(row["created_at"]),
        settled_at=store.iso(row.get("settled_at")), receipt_message=MESSAGES[st],
        commitment=row["commitment"], kaspa=_proof(row),
    )


@router.post("/instant", response_model=RefundReceipt, dependencies=[Depends(require_api_key)])
def create_instant_refund(payload: InstantRefundRequest,
                          idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    row = store.create_refund(payload, idempotency_key or payload.idempotency_key)
    return _receipt(row)


@router.get("/{refund_id}", response_model=RefundReceipt, dependencies=[Depends(require_api_key)])
def get_refund(refund_id: str):
    row = store.get_refund(refund_id)
    if not row:
        raise HTTPException(status_code=404, detail="refund not found")
    return _receipt(row)


@router.get("/{refund_id}/proof", response_model=RefundProof)
def get_proof(refund_id: str):
    """Public: the canonical record, its hash, and where that hash lives on Kaspa."""
    row = store.get_refund(refund_id)
    if not row:
        raise HTTPException(status_code=404, detail="refund not found")
    return RefundProof(
        record=store.record_for(row),
        commitment=row["commitment"],
        payload_hex=payload_hex(row["commitment"]),
        kaspa=_proof(row),
        how_to_verify=("SHA-256 the record as compact JSON with sorted keys; it must equal `commitment`. "
                       "Open the Kaspa transaction: its payload must equal `payload_hex` (hex of 'IR1' + commitment)."),
    )
