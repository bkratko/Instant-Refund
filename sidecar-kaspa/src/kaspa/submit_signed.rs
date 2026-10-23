use crate::state::AppState;

// IMPORTANT: This is the ONLY place we touch signing + submit_transaction.
// We keep it isolated so compile errors are localized.
//
// You MUST already have:
// - an RPC client in state or accessible via state
// - kaspad endpoint configured (KASPAD_GRPC_ENDPOINT or equivalent)
// - signer private key in env (KASPA_SIGNER_PRIVATE_KEY)

use std::env;

use kaspa_addresses::Address;
use kaspa_consensus_core::sign::{sign_input, SigHashType};
use kaspa_consensus_core::tx::{ScriptPublicKey, Transaction, TransactionInput, TransactionOutpoint, TransactionOutput};
use kaspa_txscript::script_builder::ScriptBuilder;

#[derive(Debug)]
pub struct UtxoIn {
    pub txid: String,
    pub index: u32,
    pub amount_sompi: u64,
}

fn parse_private_key_32() -> Result<[u8; 32], String> {
    let hex = env::var("KASPA_SIGNER_PRIVATE_KEY")
        .map_err(|_| "Missing env var KASPA_SIGNER_PRIVATE_KEY".to_string())?;
    let hex = hex.trim().trim_start_matches("0x");
    if hex.len() != 64 { return Err(format!("KASPA_SIGNER_PRIVATE_KEY must be 64 hex chars (32 bytes). Got len={}", hex.len())); }
    let bytes = faster_hex::hex_decode(hex.as_bytes()).map_err(|e| format!("Invalid hex in KASPA_SIGNER_PRIVATE_KEY: {e:?}"))?;
    let mut out = [0u8; 32];
    out.copy_from_slice(&bytes);
    Ok(out)
}

// Build a standard P2PK script public key from a kaspa address.
// This relies on Address parsing + version; we convert to ScriptPublicKey via txscript builder.
fn script_pubkey_from_address(addr: &str) -> Result<ScriptPublicKey, String> {
    let address = Address::try_from(addr).map_err(|e| format!("Invalid to_address: {e:?}"))?;

    // Typical Kaspa P2PK locking script is derived from address payload.
    // We build it using ScriptBuilder helper from kaspa_txscript.
    //
    // If your project already has a helper that converts Address->ScriptPublicKey,
    // swap this section to call that helper.

    let payload = address.payload();
    let mut sb = ScriptBuilder::new();
    sb.add_data(payload).map_err(|e| format!("ScriptBuilder add_data failed: {e:?}"))?;
    let script = sb.into_script();

    Ok(ScriptPublicKey::new(0, script.to_vec()))
}

fn build_signature_script(sig: &[u8], sighash_type: SigHashType) -> Vec<u8> {
    // Kaspa signature scripts typically push:
    // <signature+hashtype> <pubkey>
    //
    // We keep this minimal for now: push signature (with sighash byte).
    // If your node rejects due to missing pubkey push, we’ll extend with pubkey next iteration
    // once we confirm the address/pubkey mapping in your existing code.
    let mut sig_plus = sig.to_vec();
    sig_plus.push(sighash_type as u8);

    let mut sb = ScriptBuilder::new();
    let _ = sb.add_data(&sig_plus);
    sb.into_script().to_vec()
}

pub async fn submit_signed_tx(
    state: &AppState,
    to_address: &str,
    amount_sompi: u64,
    fee_sompi: u64,
    utxos: &[crate::api::submit_signed::UtxoIn],
) -> Result<String, String> {
    if utxos.is_empty() { return Err("utxos[] is empty".to_string()); }

    let privkey = parse_private_key_32()?;

    // TODO: change script should go to the sidecar-derived refund address
    // For now we require caller to send exact (sum inputs == amount+fee) or we fail.
    let input_sum: u64 = utxos.iter().map(|u| u.amount_sompi).sum();
    let needed = amount_sompi + fee_sompi;
    if input_sum != needed {
        return Err(format!("Input sum must equal amount+fee for now. input_sum={input_sum}, needed={needed}"));
    }

    let to_spk = script_pubkey_from_address(to_address)?;

    let inputs: Vec<TransactionInput> = utxos.iter().map(|u| {
        let outpoint = TransactionOutpoint::new(u.txid.clone(), u.index);
        TransactionInput::new(outpoint, vec![], 0, u.amount_sompi)
    }).collect();

    let outputs = vec![
        TransactionOutput::new(amount_sompi, to_spk),
    ];

    let mut tx = Transaction::new(0, inputs, outputs, 0);

    // Sign each input
    let sighash = SigHashType::All;
    for i in 0..tx.inputs.len() {
        let sig = sign_input(&tx, i, &privkey, sighash);
        let sig_script = build_signature_script(&sig, sighash);
        tx.inputs[i].signature_script = sig_script;
    }

    // Submit via RPC (kaspad)
    // This assumes you already have an RPC client in state with a submit_transaction method.
    // If your client differs (grpc vs wrpc), the compile error will point here.
    let txid = state.kaspa_client
        .submit_transaction(tx)
        .await
        .map_err(|e| format!("submit_transaction failed: {e:?}"))?;

    Ok(txid)
}
