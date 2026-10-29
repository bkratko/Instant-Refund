use anyhow::{anyhow, bail, Context, Result};
use kaspa_addresses::{Address, Prefix, Version};
use kaspa_wrpc_client::prelude::NetworkId;
use secp256k1::{Keypair, Secp256k1, SecretKey, XOnlyPublicKey};
use std::str::FromStr;

const FORBIDDEN_SECRETS: &[&str] = &["", "secret", "changeme", "password", "dev_secret_key_change_me"];

pub struct Config {
    pub network_id: NetworkId,
    pub address: Address,
    pub private_key: [u8; 32],
    pub hmac_secret: Vec<u8>,
    pub wrpc_url: String,
    pub confirmations_required: u64,
    pub bind: String,
}

fn prefix_for(network: &NetworkId) -> Prefix {
    Prefix::from(network.network_type())
}

pub fn derive_address(sk_bytes: &[u8; 32], network: &NetworkId) -> Result<Address> {
    let secp = Secp256k1::new();
    let sk = SecretKey::from_slice(sk_bytes).context("invalid secp256k1 private key")?;
    let kp = Keypair::from_secret_key(&secp, &sk);
    let (xonly, _) = XOnlyPublicKey::from_keypair(&kp);
    Ok(Address::new(prefix_for(network), Version::PubKey, &xonly.serialize()))
}

pub fn keygen(path: &str, network: &str) -> Result<Address> {
    if std::path::Path::new(path).exists() {
        bail!("{path} already exists; refusing to overwrite a settlement key");
    }
    let network_id = NetworkId::from_str(network).map_err(|e| anyhow!("bad KASPA_NETWORK {network}: {e}"))?;
    let sk = SecretKey::new(&mut secp256k1::rand::thread_rng());
    std::fs::write(path, hex::encode(sk.secret_bytes()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o400))?;
    }
    derive_address(&sk.secret_bytes(), &network_id)
}

fn env(name: &str) -> Result<String> {
    std::env::var(name).map_err(|_| anyhow!("required env var {name} is not set"))
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let network = std::env::var("KASPA_NETWORK").unwrap_or_else(|_| "testnet-10".into());
        let network_id = NetworkId::from_str(&network).map_err(|e| anyhow!("bad KASPA_NETWORK {network}: {e}"))?;

        let key_file = env("KASPA_SETTLEMENT_PRIVKEY_FILE")?;
        let raw = std::fs::read_to_string(&key_file).with_context(|| format!("reading {key_file}"))?;
        let bytes = hex::decode(raw.trim()).context("settlement key file must be 64 hex chars")?;
        let private_key: [u8; 32] = bytes.try_into().map_err(|_| anyhow!("settlement key must be 32 bytes"))?;

        let address = derive_address(&private_key, &network_id)?;
        let expected = env("KASPA_EXPECTED_FROM_ADDRESS")?;
        if address.to_string() != expected.trim() {
            bail!("FROM address mismatch: key derives {address}, expected {expected}");
        }

        let secret = env("SIGNER_SHARED_SECRET")?;
        if FORBIDDEN_SECRETS.contains(&secret.trim().to_lowercase().as_str()) || secret.len() < 32 {
            bail!("SIGNER_SHARED_SECRET is missing, a placeholder, or shorter than 32 chars");
        }

        Ok(Self {
            network_id,
            address,
            private_key,
            hmac_secret: secret.into_bytes(),
            wrpc_url: std::env::var("KASPAD_WRPC_URL").unwrap_or_else(|_| "ws://kaspad:17210".into()),
            confirmations_required: std::env::var("KASPA_CONFIRMATIONS_REQUIRED").ok().and_then(|v| v.parse().ok()).unwrap_or(10),
            bind: std::env::var("SIDECAR_BIND").unwrap_or_else(|_| "0.0.0.0:8080".into()),
        })
    }
}
