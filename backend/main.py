"""FastAPI app entry point.

Run from the repo root (not from inside backend/) so `vision`, `models`,
`providers`, `config` resolve as top-level packages exactly as they do for
the existing app.py Streamlit prototype:

    uvicorn backend.main:app --reload

Phase 4 adds the MeterVision integration (meter reading submission/review)
on top of Phases 1-3. Billing/payments/notifications are added in later
phases.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.routers import admin_auth, admin_import, admin_residents, auth, meters

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
app.include_router(admin_residents.router)
app.include_router(admin_import.router)
app.include_router(meters.resident_router)
app.include_router(meters.admin_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
