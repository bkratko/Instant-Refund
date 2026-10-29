"""Runtime configuration. Required secrets fail fast at startup."""
from __future__ import annotations

import os
import sys

_FORBIDDEN = {"", "secret", "changeme", "password", "dev_secret_key_change_me"}


def _require(name: str, *, secret: bool = False) -> str:
    value = os.environ.get(name, "").strip()
    if not value or (secret and (value.lower() in _FORBIDDEN or len(value) < 32)):
        print(f"STARTUP FAILED: env var {name} is missing or weak.", file=sys.stderr)
        sys.exit(1)
    return value


DATABASE_URL = _require("DATABASE_URL")
API_KEYS = [k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()]

SIDECAR_URL = os.environ.get("SIDECAR_URL", "http://sidecar:8080").rstrip("/")
KASPA_NETWORK = os.environ.get("KASPA_NETWORK", "testnet-10")
EXPLORER_TX_URL = os.environ.get(
    "EXPLORER_TX_URL",
    "https://explorer-tn10.kaspa.org/txs/{txid}" if "testnet" in KASPA_NETWORK else "https://explorer.kaspa.org/txs/{txid}",
)

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
RATE_LIMIT = os.environ.get("RATE_LIMIT", "300/minute")


def signer_secret() -> bytes:
    """Only the worker needs this; the API never talks to the signer."""
    return _require("SIGNER_SHARED_SECRET", secret=True).encode()
