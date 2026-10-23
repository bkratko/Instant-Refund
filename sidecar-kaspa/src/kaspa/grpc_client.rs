use kaspa_grpc_core::protowire::rpc_client::RpcClient;
use tracing::{error, info};
use std::time::Duration;

pub async fn connect_with_retry(endpoint: String) {
    let mut delay = 1u64;

    loop {
        match RpcClient::connect(endpoint.clone()).await {
            Ok(_) => {
                info!("connected to kaspad at {}", endpoint);
                return;
            }
            Err(e) => {
                error!("kaspad connection failed: {:?}", e);
                tokio::time::sleep(Duration::from_secs(delay)).await;
                delay = (delay * 2).min(60);
            }
        }
    }
}
