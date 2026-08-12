# Gas Billing System — Backend

A FastAPI backend for a residential gas meter reading and billing system,
built on top of [MeterVision](../README.md) (the AI meter-reading
extraction prototype in the repo root). Residents submit a photo of their
meter; MeterVision extracts the reading; the resident confirms it; the
admin runs the billing cycle; residents pay. Everything money- or
reading-related that a client submits is treated as untrusted — amounts,
consumption, and status transitions are always computed server-side.

## Architecture

```
routers/     Thin HTTP layer — request/response mapping only, no business logic
services/    Business logic, one file per domain (auth, residents, meter
             readings, billing, payments, notifications, imports, dashboard,
             system config, audit)
db/models/   SQLAlchemy 2.0 ORM models, one file per table
schemas/     Pydantic v2 request/response DTOs
core/        Cross-cutting: config, security, JWT deps, rate limiting,
             uniform error envelope, domain/auth exception types
providers/   Pluggable interfaces with mock implementations: OTP (SMS),
             payment gateway — real providers slot in later without
             touching billing logic
jobs/        APScheduler job definitions + scheduler wiring (see below)
alembic/     Migrations (SQLite now; portable to Postgres later)
storage/     Uploaded meter images + import spreadsheets (gitignored)
```

`services/meter_reading_service.py` is the integration point with the
root `vision/`, `models/`, `providers/` packages — it calls
`vision.detection.analyze_meter_image()` directly, in-process. Those
packages are never modified by the backend; the two systems only share
that one call.

**Never client-trusted, server-computed:** consumption, bill amounts, and
payment amounts are always calculated or copied from the DB server-side —
no endpoint accepts them from a request body. Resident endpoints always
resolve identity from the JWT (`get_current_resident`), never from a
client-supplied `resident_id`.

## Setup

From the repo root (not from inside `backend/`) — the app imports
`vision`, `models`, `providers`, `config` as top-level packages, exactly
like the root `app.py` Streamlit prototype does.

```bash
# 1. Dependencies (see the root README if you need the no-pip bootstrap)
.venv/bin/python3 -m pip install -r requirements.txt

# 2. Configure secrets — copy .env.example to .env and set:
#      GEMINI_API_KEY=...          (from https://aistudio.google.com/apikey)
#      SECRET_KEY=...              (32+ random bytes, see comment in .env.example)
cp .env.example .env

# 3. Create the schema
.venv/bin/python3 -m alembic -c backend/alembic.ini upgrade head

# 4. Seed one Community + default SystemConfiguration rows (idempotent)
.venv/bin/python3 backend/db/seed.py

# 5. Run the API
.venv/bin/uvicorn backend.main:app --reload
```

Swagger UI is at `http://localhost:8000/docs`. In development
(`ENVIRONMENT=development`, the default), OTP-request responses echo the
generated code in a `dev_otp` field so signup/login can be tested without
a real SMS provider — this field is never present otherwise.

## API surface

All routes are under `/api/v1`. Full detail, request/response shapes, and
a try-it-out console are at `/docs`.

| Area | Base path | Notes |
|---|---|---|
| Auth | `/auth/...`, `/admin/auth/login` | Resident signup (OTP), login, password reset, refresh/logout. Admin login is a fully separate code path. |
| Resident profile | `/resident/me`, `/resident/home` | Own profile (GET/PATCH), home-screen summary. |
| Meter readings | `/resident/meter-readings`, `/admin/meter-readings` | Submit → AI extraction → resident confirm; admin override/reject. |
| Billing | `/resident/bills`, `/admin/billing-periods`, `/admin/bills` | Period lifecycle, bill generation, waive/cancel. |
| Payments | `/resident/bills/{id}/payments`, `/payments/{id}/mock-confirm`, `/admin/payments` | Mock payment gateway; amount always server-side. |
| Admin residents | `/admin/residents` | CRUD (delete = soft-deactivate), meter assignment, password reset. |
| Admin import | `/admin/imports` | Spreadsheet upload → column mapping → validate → preview → confirm. |
| Admin dashboard | `/admin/dashboard/{overview,collections}` | Aggregate stats for the admin UI. |
| System config | `/admin/system-config` | Rate, fine, OTP, regex, and auto-period-creation settings. |
| Notifications | `/resident/notifications`, `/admin/notifications` | In-app only; SMS/email channels are logged mocks. |

Role separation is enforced at the dependency level: `get_current_resident`
and `get_current_admin` are two separate FastAPI dependencies, each
checking a distinct JWT `scope` claim, applied per-router — a
resident-scoped token structurally cannot satisfy an admin route.

## Rate limiting

Via [slowapi](https://github.com/laurentS/slowapi), configured in
`core/rate_limit.py`:

| Endpoint(s) | Limit |
|---|---|
| Resident/admin login | 5/minute per IP |
| OTP request (signup + password reset) | 3/hour per mobile number, 10/hour per IP |
| Payment mock-confirm | 10/minute per IP |

The OTP per-mobile limit uses a custom key function so a phone number
can't be hammered from many IPs even though the per-IP limit alone
wouldn't catch that. Exceeding a limit returns `429` in the same envelope
as every other error (see below).

## Error responses

Every error response — a domain error, a validation failure, a rate-limit
rejection, or a genuinely unhandled exception — has the same shape:

```json
{"detail": "...", "error_type": "conflict", "status_code": 409}
```

`detail` is a string for most errors and the structured Pydantic error
list for `422` validation failures. Unhandled exceptions are logged
server-side with a full traceback and returned to the client as a generic
`500` with no internal detail leaked. See `core/error_handlers.py`.

## Audit logging

Every state-changing action funnels through one
`services/audit_service.py::record()` helper, called from the service
layer (never from routers), so coverage doesn't depend on remembering it
at each new endpoint. Covers: resident data changes (admin- and
self-service), billing period create/update/lifecycle transitions and
rate/deadline changes, bill generation/waive/cancel, meter reading
submit/confirm/override/reject, payment initiate/confirm/mark-offline,
fine accrual, spreadsheet import confirmation, and system-config changes.
Rows record `actor_type` (`RESIDENT` / `ADMIN` / `SYSTEM`) so
scheduler-triggered actions are distinguishable from a human click on the
same code path (e.g. `billing_period.open` fired by an admin vs. by the
`billing_cycle_kickoff` job).

## Scheduled jobs

In-process via APScheduler (`jobs/scheduler.py`, wired into FastAPI's
`lifespan`). Every job is idempotent — safe to run twice without
duplicating side effects — since a single-process in-memory scheduler
offers no other guarantee against a double-fire or a restart mid-run.

| Job | Schedule | What it does |
|---|---|---|
| `billing_cycle_kickoff` | daily 00:15 | Opens DRAFT periods whose reading window has started; auto-creates the next DRAFT period per community if none is pending. |
| `reading_window_deadline_check` | daily 00:30 | Closes readings past the window end, notifies residents/admin of missing readings, generates bills. |
| `bill_due_date_check` | daily 01:00 | Marks bills OVERDUE past their due date, notifies resident + admin. |
| `fine_accrual` | daily 01:15 | Adds a daily late fine to overdue bills. |
| `late_payment_reminder` | daily 09:00 | Reminds residents with an overdue bill (once per day). |
| `import_job_cleanup` | weekly, Sun 02:00 | Deletes stored spreadsheet files older than 90 days for terminal-status import jobs (DB rows are kept). |

**Evolution note:** a second uvicorn worker would double-fire every job
(mitigated by the idempotency checks above) and a crash mid-job loses
in-flight state. Real-production path: Celery beat + Redis/RabbitMQ, or a
hosted cron hitting a token-secured internal endpoint.

## Testing

```bash
.venv/bin/python3 -m pytest backend/tests/ -v       # backend only
.venv/bin/python3 -m pytest tests/ backend/tests/ -v # backend + MeterVision
```

Service-layer and router tests use an isolated in-memory SQLite DB per
test (`conftest.py`'s `client_and_session`/`db_session`/`jobs_db`
fixtures) with a `FakeVisionProvider` test double standing in for Gemini.
One dedicated test
(`test_meter_reading_service.py::test_submit_and_confirm_reading_against_real_gemini_api`)
calls the real Gemini API against the repo's sample photo to prove the
integration genuinely works end-to-end; it skips itself (rather than
failing) on a transient quota/timeout error, since that's an external
condition, not a code defect.

## Known limitations (by design, for this scale)

- **SQLite**, not Postgres — fine for one community of ~10-15 residents;
  written portably (typed columns, no SQLite-specific SQL) so a swap is a
  connection-string change plus an Alembic re-target, not a rewrite.
- **Mock OTP and payment providers** (`providers/otp/`,
  `providers/payment/`) — both log what they'd send/charge instead of
  calling a real gateway, behind interfaces a real provider can replace
  without touching billing logic.
- **In-process scheduler**, not a separate worker — see "Evolution note"
  above.
- **No admin web UI or mobile app yet** — this is the API only. The
  approved design reserves `admin_web/` (Streamlit) and `mobile/`
  (Flutter) for later, calling this API over HTTP with no business logic
  of their own.
