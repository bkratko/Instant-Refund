use crate::anchor::Anchorer;
use anyhow::Result;
use axum::{
    body::Bytes,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use hmac::{Hmac, Mac};
use serde::Deserialize;
use serde_json::json;
use sha2::Sha256;
use std::sync::Arc;

type AppState = Arc<Anchorer>;

#[derive(Deserialize)]
struct AnchorRequest {
    refund_id: String,
    /// 32-byte refund commitment, hex. Computed by the worker; contains no PII.
    commitment_hex: String,
    expires_at_unix: u64,
}

fn err(code: StatusCode, msg: impl ToString) -> Response {
    (code, Json(json!({ "error": msg.to_string() }))).into_response()
}

fn verify_hmac(secret: &[u8], headers: &HeaderMap, body: &[u8]) -> bool {
    let Some(sig) = headers.get("x-signer-auth").and_then(|v| v.to_str().ok()) else { return false };
    let Ok(sig) = hex::decode(sig) else { return false };
    let mut mac = Hmac::<Sha256>::new_from_slice(secret).expect("hmac key");
    mac.update(body);
    mac.verify_slice(&sig).is_ok() // constant-time
}

async fn healthz() -> &'static str {
    "ok"
}

async fn wallet(State(a): State<AppState>) -> Response {
    match a.wallet().await {
        Ok(w) => Json(w).into_response(),
        Err(e) => err(StatusCode::SERVICE_UNAVAILABLE, e),
    }
}

async fn anchor(State(a): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    if !verify_hmac(&a.cfg.hmac_secret, &headers, &body) {
        return err(StatusCode::UNAUTHORIZED, "invalid X-Signer-Auth");
    }
    let req: AnchorRequest = match serde_json::from_slice(&body) {
        Ok(r) => r,
        Err(e) => return err(StatusCode::BAD_REQUEST, e),
    };
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
    if req.expires_at_unix < now || req.expires_at_unix > now + 300 {
        return err(StatusCode::BAD_REQUEST, "intent expired or expiry too far out");
    }
    let commitment: [u8; 32] = match hex::decode(&req.commitment_hex).ok().and_then(|b| b.try_into().ok()) {
        Some(c) => c,
        None => return err(StatusCode::BAD_REQUEST, "commitment_hex must be 32 bytes"),
    };
    match a.anchor(commitment).await {
        Ok(r) => {
            tracing::info!(refund_id = %req.refund_id, txid = %r.txid, "refund anchored");
            Json(r).into_response()
        }
        Err(e) => err(StatusCode::BAD_GATEWAY, e),
    }
}

async fn status(State(a): State<AppState>, Path(txid): Path<String>) -> Response {
    match a.status(&txid).await {
        Ok(s) => Json(s).into_response(),
        Err(e) => err(StatusCode::BAD_GATEWAY, e),
    }
}

pub async fn serve(state: AppState) -> Result<()> {
    let bind = state.cfg.bind.clone();
    let app = Router::new()
        .route("/healthz", get(healthz))
        .route("/v1/wallet", get(wallet))
        .route("/v1/anchor", post(anchor))
        .route("/v1/anchor/:txid", get(status))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!(%bind, "sidecar listening");
    axum::serve(listener, app).await?;
    Ok(())
}
