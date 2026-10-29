//! Instant Refund — Kaspa settlement sidecar.
//!
//! The only process that ever holds the settlement private key. It:
//!   * binds the key to its Kaspa address at startup (and refuses to run on a mismatch),
//!   * anchors a refund with one transaction from the settlement address back to itself,
//!     whose payload carries the refund's 32-byte commitment hash,
//!   * reports acceptance of an anchor (DAA score + confirmations) by transaction id.
//!
//! Callers authenticate every POST with `X-Signer-Auth: hex(HMAC-SHA256(secret, body))`.
//!
//! Subcommand `keygen <file>` creates a fresh key on the server so it never leaves it.

mod anchor;
mod config;
mod http;

use anyhow::Result;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into())).init();

    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("keygen") {
        let path = args.get(2).cloned().unwrap_or_else(|| "settlement.key".into());
        let network = std::env::var("KASPA_NETWORK").unwrap_or_else(|_| "testnet-10".into());
        let addr = config::keygen(&path, &network)?;
        println!("{addr}");
        return Ok(());
    }

    let cfg = config::Config::from_env()?;
    tracing::info!(address = %cfg.address, network = %cfg.network_id, "settlement key bound");

    let anchor = anchor::Anchorer::connect(cfg).await?;
    http::serve(anchor).await
}
