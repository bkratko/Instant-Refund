use crate::state::RuntimeState;
use std::time::Duration;

pub async fn run(state: RuntimeState) {
    loop {
        tokio::time::sleep(Duration::from_secs(1)).await;
        let uptime = state.started_at.elapsed().as_secs();
        tracing::info!("settlement clock tick - uptime={}s", uptime);
    }
}
