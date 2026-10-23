use axum::{extract::State, http::StatusCode, Json};
use serde::{Deserialize, Serialize};

use crate::state::AppState;

// --- Request/Response payloads ---
#[derive(Debug, Deserialize)]
pub struct UtxoIn {
    pub txid: String,
    pub index: u32,
    pub amount_sompi: u64,
}

#[derive(Debug, Deserialize)]
pub struct SubmitSignedReq {
    pub to_address: String,
    pub amount_sompi: u64,
    pub fee_sompi: u64,
    pub utxos: Vec<UtxoIn>,
}

#[derive(Debug, Serialize)]
pub struct SubmitSignedResp {
    pub status: &'static str,
    pub txid: Option<String>,
    pub error: Option<String>,
}

/// DEBUG ONLY:
/// Build + sign a tx inside the sidecar using KASPA_SIGNER_PRIVATE_KEY,
/// then submit via RPC submit_transaction.
///
/// This implements Option A: sidecar signing + kaspad submit_transaction.
///
/// IMPORTANT:
/// - This is not used by production refund flow yet.
/// - This is the “first real txid” proof endpoint.
pub async fn submit_signed(
    State(state): State<AppState>,
    Json(req): Json<SubmitSignedReq>,
) -> (StatusCode, Json<SubmitSignedResp>) {
    // 1) Build an unsigned plan (inputs/outputs/change)
    // 2) Sign each input with schnorr
    // 3) Submit via RPC

    let result = crate::kaspa::submit_signed_tx(
        &state,
        &req.to_address,
        req.amount_sompi,
        req.fee_sompi,
        &req.utxos,
    ).await;

    match result {
        Ok(txid) => (
            StatusCode::OK,
            Json(SubmitSignedResp { status: "ok", txid: Some(txid), error: None })
        ),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(SubmitSignedResp { status: "error", txid: None, error: Some(e) })
        ),
    }
}
