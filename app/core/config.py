import os

import sys

_FORBIDDEN_SECRETS = {"dev_secret_key_change_me", "DEBUG_SHARED_SECRET_DO_NOT_KEEP", "secret", "changeme", "password", ""}

def _require_env(name: str, *, secret: bool = False) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"STARTUP FAILED: Required env var '{name}' is not set.", file=sys.stderr)
        sys.exit(1)
    if secret and value.lower() in _FORBIDDEN_SECRETS:
        print(f"STARTUP FAILED: '{name}' contains a known-weak placeholder.", file=sys.stderr)
        sys.exit(1)
    return value
from pydantic import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Instant Refund API"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev_secret_key_change_me")
    SIGNER_URL: str = os.getenv("SIGNER_URL", "http://instant-refund-signer:8080/sign")
    
    # SWITCHING TO PUBLIC IP (The Front Door)
    KASPAD_ADDRESS: str = _require_env("KASPAD_ADDRESS") 
    KASPAD_PORT: int = 16110

settings = Settings()


# Module-level exports for direct import
SIGNER_SHARED_SECRET = _require_env('SIGNER_SHARED_SECRET', secret=True)
SIGNER_URL = os.environ.get('SIGNER_URL', 'http://instant-refund-signer:8080/sign')
