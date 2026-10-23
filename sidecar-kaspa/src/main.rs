use tracing::{error, info};
use tracing_subscriber::EnvFilter;

mod settlement_key;
mod state;
mod http_server;

use state::RuntimeState;

use tokio::time::{sleep, Duration};
use tokio_postgres::NoTls;

async fn poll_pending_signed_intents() {
    let db_url = match std::env::var("DATABASE_URL") {
        Ok(v) => v,
        Err(_) => {
            error!("DATABASE_URL not set; sidecar DB polling disabled");
            return;
        }
    };

    loop {
        match tokio_postgres::connect(&db_url, NoTls).await {
            Ok((client, connection)) => {
                tokio::spawn(async move {
                    if let Err(e) = connection.await {
                        error!("postgres_connection_error: {}", e);
                    }
                });

                match client
                    .query(
                        "SELECT signed_intent_id, refund_id FROM signed_intents WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 25",
                        &[],
                    )
                    .await
                {
                    Ok(rows) => {
                        info!("pending_signed_intents count={}", rows.len());
                        for r in rows {
                            let sid: String = r.get(0);
                            let rid: String = r.get(1);
                            info!("pending_intent signed_intent_id={} refund_id={}", sid, rid);
                        }
                    }
                    Err(e) => {
                        error!("pending_intents_query_failed: {}", e);
                    }
                }
            }
            Err(e) => {
                error!("postgres_connect_failed: {}", e);
            }
        }

        sleep(Duration::from_secs(10)).await;
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let state = RuntimeState::new();

    // --- SIGNER INIT (AUTHORITATIVE) ---
    match settlement_key::assert_expected_from_address(&()) {
        Ok(from) => {
            info!("signer_loaded from_address={}", from);
            state.set_wallet_ok(from);
        }
        Err(e) => {
            error!("signer_init_failed: {}", e);
            state.set_wallet_error(e.to_string());
        }
    }

    // --- BACKGROUND DB POLLER ---
    tokio::spawn(poll_pending_signed_intents());

    // --- HTTP SERVER ---
    if let Err(e) = http_server::serve_http(state.clone()).await {
        error!("http_server_failed: {}", e);
        std::process::exit(1);
    }
}