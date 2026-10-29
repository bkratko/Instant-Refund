from __future__ import annotations
import os
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, Header, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from app.db import db_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/compliance", tags=["compliance"])

def _auth(x_api_key: Optional[str]):
    import secrets
    valid_keys = [k.strip() for k in os.environ.get("API_KEYS","").split(",") if k.strip()]
    if not x_api_key or not any(secrets.compare_digest(x_api_key.strip(), k) for k in valid_keys):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

@router.get("/report")
def compliance_report(
    merchant_id: str = Query(..., description="Merchant ID to report on"),
    period_start: str = Query(..., description="ISO date e.g. 2026-01-01"),
    period_end: str = Query(..., description="ISO date e.g. 2026-03-31"),
    format: str = Query("json", description="json or csv"),
    x_api_key: Optional[str] = Header(None),
):
    """
    Generate a PCI/SOX-ready refund reconciliation report for a merchant.
    Returns every refund in the period with Kaspa confirmation hash,
    authorization timestamp, settlement status, acquirer, and flow position.
    Suitable for direct inclusion in audit packages.
    """
    _auth(x_api_key)

    try:
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=timezone.utc)
        end_dt   = datetime.fromisoformat(period_end).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO: YYYY-MM-DD")

    with db_cursor() as (_, cur):
        cur.execute("""
            SELECT
                r.refund_id, r.merchant_id, r.order_id, r.customer_id, r.amount, r.currency, r.status,
                r.acquirer_id, r.flow_position, r.reason, r.idempotency_key, r.created_at, r.updated_at,
                r.commitment, r.kaspa_txid, r.kaspa_block_daa, r.settled_at
            FROM refunds r
            WHERE r.merchant_id = %s
              AND r.created_at >= %s
              AND r.created_at <  %s
            ORDER BY r.created_at ASC
        """, (merchant_id, start_dt, end_dt))

        rows = cur.fetchall()

    records = [dict(row) for row in rows]
    for rec in records:
        for k, v in rec.items():
            if hasattr(v, "isoformat"):
                rec[k] = v.isoformat()
            elif v is not None and k == "amount":
                rec[k] = f"{v:.2f}"

    summary = {
        "merchant_id":    merchant_id,
        "period_start":   period_start,
        "period_end":     period_end,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "total_records":  len(records),
        "total_settled":  sum(1 for r in records if r.get("status") == "settled"),
        "total_pending":  sum(1 for r in records if r.get("status") == "pending_settlement"),
        "total_failed":   sum(1 for r in records if r.get("status") == "failed"),
        "report_type":    "PCI_DSS_SOX_REFUND_RECONCILIATION",
        "records":        records,
    }

    if format == "csv":
        output = io.StringIO()
        fields = ["refund_id","merchant_id","order_id","customer_id","amount","status",
                  "acquirer_id","flow_position","reason","idempotency_key","created_at",
                  "updated_at","currency","commitment","kaspa_txid","kaspa_block_daa","settled_at"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
        output.seek(0)
        filename = f"refund-report-{merchant_id}-{period_start}-{period_end}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return JSONResponse(content=summary)
