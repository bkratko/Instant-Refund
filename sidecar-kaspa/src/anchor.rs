use crate::config::Config;
use anyhow::{anyhow, bail, Result};
use kaspa_consensus_client::{UtxoEntry, UtxoEntryReference};
use kaspa_wallet_core::tx::{Fees, Generator, GeneratorSettings, PaymentDestination, PaymentOutput};
use kaspa_wrpc_client::prelude::*;
use serde::Serialize;
use std::collections::HashMap;
use std::str::FromStr;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

/// Value of the anchor output, paid back to the settlement address (1 KAS). Only the fee is spent.
pub const ANCHOR_OUTPUT_SOMPI: u64 = 100_000_000;

/// Every anchor payload starts with this tag so refunds are easy to find on-chain.
pub const PAYLOAD_TAG: &[u8] = b"IR1";

#[derive(Serialize, Clone)]
pub struct AnchorReceipt {
    pub txid: String,
    pub fee_sompi: u64,
    pub payload_hex: String,
}

#[derive(Serialize, Clone)]
pub struct AnchorStatus {
    pub txid: String,
    /// "pending" (in mempool), "accepted" (in the DAG), or "unknown"
    pub state: &'static str,
    pub block_daa_score: Option<u64>,
    pub confirmations: Option<u64>,
    pub confirmations_required: u64,
    pub final_: bool,
}

#[derive(Serialize)]
pub struct WalletInfo {
    pub address: String,
    pub network: String,
    pub balance_sompi: u64,
    pub utxo_count: usize,
    pub node_synced: bool,
    pub virtual_daa_score: u64,
}

pub struct Anchorer {
    pub cfg: Config,
    rpc: Arc<KaspaRpcClient>,
    /// Serializes anchors: each anchor must see the previous one accepted.
    submit_lock: Mutex<Option<String>>,
    /// txid -> block DAA score, remembered once seen accepted.
    accepted: Mutex<HashMap<String, u64>>,
}

impl Anchorer {
    pub async fn connect(cfg: Config) -> Result<Arc<Self>> {
        let rpc = Arc::new(KaspaRpcClient::new(WrpcEncoding::Borsh, Some(&cfg.wrpc_url), None, Some(cfg.network_id), None)?);
        let options = ConnectOptions { block_async_connect: false, strategy: ConnectStrategy::Retry, ..Default::default() };
        rpc.connect(Some(options)).await?;
        tracing::info!(url = %cfg.wrpc_url, "connecting to kaspad wRPC");
        Ok(Arc::new(Self { cfg, rpc, submit_lock: Mutex::new(None), accepted: Mutex::new(HashMap::new()) }))
    }

    fn api(&self) -> Arc<dyn RpcApi> {
        self.rpc.rpc_api()
    }

    async fn utxos(&self) -> Result<Vec<UtxoEntryReference>> {
        let entries = self.rpc.get_utxos_by_addresses(vec![self.cfg.address.clone()]).await?;
        Ok(entries
            .into_iter()
            .map(|e| {
                UtxoEntryReference::from(UtxoEntry {
                    address: e.address,
                    outpoint: e.outpoint.into(),
                    amount: e.utxo_entry.amount,
                    script_public_key: e.utxo_entry.script_public_key,
                    block_daa_score: e.utxo_entry.block_daa_score,
                    is_coinbase: e.utxo_entry.is_coinbase,
                    covenant_id: e.utxo_entry.covenant_id,
                })
            })
            .collect())
    }

    pub async fn wallet(&self) -> Result<WalletInfo> {
        let info = self.rpc.get_server_info().await?;
        let utxos = self.utxos().await?;
        Ok(WalletInfo {
            address: self.cfg.address.to_string(),
            network: self.cfg.network_id.to_string(),
            balance_sompi: utxos.iter().map(|u| u.amount()).sum(),
            utxo_count: utxos.len(),
            node_synced: info.is_synced,
            virtual_daa_score: info.virtual_daa_score,
        })
    }

    /// Anchor one refund commitment: one transaction from the settlement address back to
    /// itself (anchor output + change), carrying `IR1 || commitment` as its payload.
    /// Only the network fee leaves the wallet.
    pub async fn anchor(&self, commitment: [u8; 32]) -> Result<AnchorReceipt> {
        let mut last = self.submit_lock.lock().await;

        // Wait for the previous anchor to leave the mempool, so its change output is spendable.
        if let Some(prev) = last.clone() {
            let deadline = Instant::now() + Duration::from_secs(30);
            while self.status(&prev).await?.state == "pending" {
                if Instant::now() > deadline {
                    bail!("previous anchor {prev} still pending after 30s");
                }
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
        }

        let utxos = self.utxos().await?;
        if utxos.is_empty() {
            bail!("settlement address {} has no funds", self.cfg.address);
        }

        let mut payload = PAYLOAD_TAG.to_vec();
        payload.extend_from_slice(&commitment);

        let settings = GeneratorSettings::try_new_with_iterator(
            self.cfg.network_id,
            Box::new(utxos.into_iter()),
            None,
            self.cfg.address.clone(),
            1,
            1,
            PaymentDestination::from(PaymentOutput::new(self.cfg.address.clone(), ANCHOR_OUTPUT_SOMPI)),
            None,
            Fees::SenderPays(0),
            Some(payload.clone()),
            None,
        )?;
        let generator = Generator::try_new(settings, None, None)?;

        let api = self.api();
        let mut final_receipt = None;
        for pending in generator.iter() {
            let pending = pending?;
            pending.try_sign_with_keys(&[self.cfg.private_key], Some(true))?;
            let txid = pending.try_submit(&api).await?;
            tracing::info!(%txid, fee = pending.fees(), final_tx = pending.is_final(), "anchor submitted");
            if pending.is_final() {
                final_receipt = Some(AnchorReceipt { txid: txid.to_string(), fee_sompi: pending.fees(), payload_hex: hex::encode(&payload) });
            }
        }
        let receipt = final_receipt.ok_or_else(|| anyhow!("generator produced no final transaction"))?;
        *last = Some(receipt.txid.clone());
        Ok(receipt)
    }

    /// Acceptance check: in mempool => pending; spendable change UTXO from this txid => accepted.
    pub async fn status(&self, txid: &str) -> Result<AnchorStatus> {
        let required = self.cfg.confirmations_required;
        let virtual_daa = self.rpc.get_server_info().await?.virtual_daa_score;
        let make = |state, score: Option<u64>| {
            let confs = score.map(|s| virtual_daa.saturating_sub(s));
            AnchorStatus {
                txid: txid.to_string(),
                state,
                block_daa_score: score,
                confirmations: confs,
                confirmations_required: required,
                final_: confs.map(|c| c >= required).unwrap_or(false),
            }
        };

        if let Some(score) = self.accepted.lock().await.get(txid).copied() {
            return Ok(make("accepted", Some(score)));
        }

        let id = RpcTransactionId::from_str(txid).map_err(|_| anyhow!("bad txid"))?;
        if self.rpc.get_mempool_entry(id, true, false).await.is_ok() {
            return Ok(make("pending", None));
        }

        let entries = self.rpc.get_utxos_by_addresses(vec![self.cfg.address.clone()]).await?;
        if let Some(e) = entries.iter().find(|e| e.outpoint.transaction_id == id) {
            let score = e.utxo_entry.block_daa_score;
            self.accepted.lock().await.insert(txid.to_string(), score);
            return Ok(make("accepted", Some(score)));
        }
        Ok(make("unknown", None))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use kaspa_consensus_client::TransactionOutpoint;
    use kaspa_wrpc_client::prelude::RpcTransactionId;

    /// Offline check of the anchor path: build, sign and inspect an anchor with the IR1 payload.
    #[test]
    fn builds_and_signs_anchor_offline() {
        let network = NetworkId::from_str("testnet-10").unwrap();
        let key = [7u8; 32];
        let address = crate::config::derive_address(&key, &network).unwrap();
        let spk = kaspa_txscript::pay_to_address_script(&address);
        let utxo = UtxoEntryReference::from(UtxoEntry {
            address: Some(address.clone()),
            outpoint: TransactionOutpoint::new(RpcTransactionId::from_slice(&[1u8; 32]), 0),
            amount: 1_000_000_000,
            script_public_key: spk,
            block_daa_score: 1,
            is_coinbase: false,
            covenant_id: None,
        });
        let mut payload = PAYLOAD_TAG.to_vec();
        payload.extend_from_slice(&[9u8; 32]);
        let settings = GeneratorSettings::try_new_with_iterator(
            network, Box::new(vec![utxo].into_iter()), None, address.clone(), 1, 1,
            PaymentDestination::from(PaymentOutput::new(address.clone(), ANCHOR_OUTPUT_SOMPI)), None, Fees::SenderPays(0), Some(payload.clone()), None,
        ).unwrap();
        let generator = Generator::try_new(settings, None, None).unwrap();
        let txs: Vec<_> = generator.iter().collect::<Result<_, _>>().unwrap();
        assert_eq!(txs.len(), 1);
        let tx = &txs[0];
        tx.try_sign_with_keys(&[key], Some(true)).unwrap();
        let t = tx.transaction();
        assert_eq!(t.payload, payload);
        assert_eq!(t.outputs.len(), 2); // anchor output + change, both to the settlement address
        assert!(tx.fees() > 0 && tx.fees() < 1_000_000, "fee {}", tx.fees());
        assert!(!t.inputs[0].signature_script.is_empty());
        println!("txid={} fee={} out={}", tx.id(), tx.fees(), t.outputs[0].value);
    }
}
