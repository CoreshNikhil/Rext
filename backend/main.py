"""FastAPI app entry point.

Run from the repo root (not from inside backend/) so `vision`, `models`,
`providers`, `config` resolve as top-level packages exactly as they do for
the existing app.py Streamlit prototype:

    uvicorn backend.main:app --reload

Phase 7 adds notifications and the scheduled-job system (billing-cycle
kickoff, deadline checks, fine accrual, reminders) on top of Phases 1-6.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.jobs.scheduler import start_scheduler, stop_scheduler
from backend.routers import (
    admin_auth,
    admin_billing,
    admin_import,
    admin_residents,
    auth,
    billing,
    meters,
    notifications,
    payments,
    resident,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Gas Billing System API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin_auth.router)
app.include_router(resident.router)
app.include_router(admin_residents.router)
app.include_router(admin_import.router)
app.include_router(meters.resident_router)
app.include_router(meters.admin_router)
app.include_router(billing.router)
app.include_router(admin_billing.billing_period_router)
app.include_router(admin_billing.bill_router)
app.include_router(payments.resident_router)
app.include_router(payments.admin_router)
app.include_router(payments.public_router)
app.include_router(notifications.resident_router)
app.include_router(notifications.admin_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
