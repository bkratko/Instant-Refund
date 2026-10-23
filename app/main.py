"""
Instant Refund API entrypoint.

Router wiring happens at import time (deterministic) because some platforms
do not reliably run FastAPI startup hooks.
"""
import os

from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import app
from app.routes import compliance as compliance_router
from app.routes.refunds import router as refunds_router

limiter = Limiter(key_func=get_remote_address, default_limits=[os.getenv("RATE_LIMIT", "60/minute")])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key"],
)

app.include_router(compliance_router.router)
app.include_router(refunds_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
