use axum::{routing::get, Router};
use tokio::net::TcpListener;
use tracing::info;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use std::time::Duration;
use tokio::net::TcpStream;
use tokio::time::timeout;

async fn healthz() -> &'static str {
    "ok"
}

pub async fn serve() {
    let app = Router::new().route("/healthz", get(healthz));

    let addr = "0.0.0.0:8080";
    let listener = TcpListener::bind(addr).await.unwrap();

    info!("healthz listening on {}", addr);

    axum::serve(listener, app).await.unwrap();
}

async fn debug_kaspad_connect() -> impl IntoResponse {
    // wRPC is websocket over TCP; TCP connect is sufficient to prove VPC reachability.
    let host = std::env::var("KASPA_WRPC_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
    let port: u16 = std::env::var("KASPA_WRPC_PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
        .unwrap_or(16110);

    let timeout_secs: f64 = std::env::var("KASPA_WRPC_TIMEOUT_SECS")
        .ok()
        .and_then(|v| v.parse::<f64>().ok())
        .unwrap_or(3.0);

    let addr = format!("{}:{}", host, port);

    match timeout(Duration::from_secs_f64(timeout_secs), TcpStream::connect(addr.clone())).await {
        Ok(Ok(_stream)) => {
            let body = format!(r#"{{"status":"ok","message":"Connected to kaspad wRPC (TCP) at {}"}}"#, addr);
            (StatusCode::OK, body)
        }
        Ok(Err(e)) => {
            let body = format!(r#"{{"status":"error","message":"TCP connect failed to {}","error":"{}"}}"#, addr, e);
            (StatusCode::SERVICE_UNAVAILABLE, body)
        }
        Err(_elapsed) => {
            let body = format!(r#"{{"status":"error","message":"TCP connect timed out to {}","error":"timeout"}}
"#, addr);
            (StatusCode::GATEWAY_TIMEOUT, body)
        }
    }
}


