use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use serde::Serialize;
use std::net::SocketAddr;

use crate::state::RuntimeState;

#[derive(Serialize)]
struct WalletDebug {
    address: Option<String>,
    wallet_bound: bool,
    startup_error: Option<String>,
}

pub async fn serve_http(state: RuntimeState) -> Result<(), Box<dyn std::error::Error>> {
    let app = Router::new()
        .route("/sidecar/healthz", get(|| async { "ok" }))
        .route("/sidecar/debug/wallet", get(debug_wallet))
        .with_state(state);

    let host = std::env::var("SIDECAR_HTTP_HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port = std::env::var("SIDECAR_HTTP_PORT").unwrap_or_else(|_| "8080".to_string());
    let addr: SocketAddr = format!("{}:{}", host, port).parse()?;

    println!("[sidecar] listening on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

async fn debug_wallet(State(state): State<RuntimeState>) -> impl IntoResponse {
    let (address, wallet_bound, startup_error) = state.wallet_snapshot();

    let body = WalletDebug {
        address,
        wallet_bound,
        startup_error,
    };

    if wallet_bound {
        (StatusCode::OK, Json(body))
    } else {
        (StatusCode::SERVICE_UNAVAILABLE, Json(body))
    }
}
