"""Instant Refund API."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import CORS_ORIGINS, RATE_LIMIT
from app.db import init_schema
from app.routes import compliance, demo, refunds

app = FastAPI(title="Instant Refund on Kaspa", version="0.2.0")

app.state.limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key"],
)

app.include_router(refunds.router)
app.include_router(compliance.router)
if demo.ENABLED:
    app.include_router(demo.router)


@app.on_event("startup")
def _startup() -> None:
    init_schema()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
