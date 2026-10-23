use anyhow::{Result, anyhow};

#[cfg(windows)]
pub fn assert_expected_from_address(_: &()) -> Result<String> {
    Ok("windows-dev-stub".to_string())
}

#[cfg(not(windows))]
use kaspa_addresses::{Address, Prefix, Version};
#[cfg(not(windows))]
use secp256k1::{Secp256k1, SecretKey, Keypair, XOnlyPublicKey};
#[cfg(not(windows))]
use std::fs;

#[cfg(not(windows))]
pub fn assert_expected_from_address(_: &()) -> Result<String> {
    let privkey_file = std::env::var("KASPA_SETTLEMENT_PRIVKEY_FILE")?;
    let expected = std::env::var("KASPA_EXPECTED_FROM_ADDRESS")?;

    let raw = fs::read_to_string(privkey_file)?;
    let bytes = hex::decode(raw.trim())?;
    let mut sk_bytes = [0u8; 32];
    sk_bytes.copy_from_slice(&bytes);

    let secp = Secp256k1::new();
    let sk = SecretKey::from_slice(&sk_bytes)?;
    let kp = Keypair::from_secret_key(&secp, &sk);
    let (xonly, _) = XOnlyPublicKey::from_keypair(&kp);

    let addr = Address::new(Prefix::Mainnet, Version::PubKey, &xonly.serialize())
        .address_to_string();

    if addr != expected {
        return Err(anyhow!("FROM address mismatch"));
    }

    Ok(addr)
}
