"""FastAPI app entry point.

Run from the repo root (not from inside backend/) so `vision`, `models`,
`providers`, `config` resolve as top-level packages exactly as they do for
the existing app.py Streamlit prototype:

    uvicorn backend.main:app --reload

Phase 7 adds notifications and the scheduled-job system (billing-cycle
kickoff, deadline checks, fine accrual, reminders) on top of Phases 1-6.
Also includes the admin dashboard and system-config endpoints, which were
in the original approved design but hadn't been assigned to any phase.

Phase 8 adds slowapi rate limiting (see core/rate_limit.py and the
@limiter.limit(...) decorators on the auth/payment routers) and a uniform
JSON error envelope for every error response (see core/error_handlers.py).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from backend.core.config import settings
from backend.core.error_handlers import register_error_handlers
from backend.core.rate_limit import limiter
from backend.jobs.scheduler import start_scheduler, stop_scheduler
from backend.routers import (
    admin_auth,
    admin_billing,
    admin_dashboard,
    admin_import,
    admin_residents,
    admin_system_config,
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

app.state.limiter = limiter
register_error_handlers(app)
app.add_middleware(SlowAPIMiddleware)

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
app.include_router(admin_dashboard.router)
app.include_router(admin_system_config.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
