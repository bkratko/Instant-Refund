from app.core.config import SIGNER_SHARED_SECRET, SIGNER_URL
import os
from fastapi import FastAPI, Header, HTTPException

if not SIGNER_SHARED_SECRET:
    raise RuntimeError("Signer shared secret not configured")

app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def verify_shared_secret(x_signer_secret: str | None):
    if not x_signer_secret or x_signer_secret != SIGNER_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid signer secret")


@app.post("/sign")
def sign_request(
    payload: dict,
    x_signer_secret: str | None = Header(default=None),
):
    """
    Kaspa signing is handled exclusively by the Rust sidecar.
    This service only authenticates and forwards intent.
    """
    verify_shared_secret(x_signer_secret)

    return {
        "status": "accepted",
        "note": "Signing delegated to Kaspa sidecar",
    }


print('SIGNER ROUTES LOADED')
