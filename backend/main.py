"""FastAPI app entry point.

Run from the repo root (not from inside backend/) so `vision`, `models`,
`providers`, `config` resolve as top-level packages exactly as they do for
the existing app.py Streamlit prototype:

    uvicorn backend.main:app --reload

Phase 2 scope: auth routers on top of Phase 1's foundations. The
MeterVision integration and business routers (billing, payments, etc.)
are added in later phases.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.routers import admin_auth, auth

app = FastAPI(title="Gas Billing System API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin_auth.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
