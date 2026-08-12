"""In-process job scheduler.

Uses APScheduler's default in-memory jobstore — schedules are
re-registered from code on every process start, since these are fixed
cron-style jobs rather than dynamically created ones; nothing needs to
persist across restarts.

Evolution note for real production: this runs threads inside the same
process as the FastAPI app — fine for a single instance, but two uvicorn
workers would both fire every job (mitigated today only by each job's own
idempotency checks, which is exactly why every job in jobs/definitions.py
is designed to be safe to run twice), and a mid-job crash loses in-flight
state. Real production path: Celery beat + Celery workers + a Redis/
RabbitMQ broker (separate process, persisted schedule, horizontal scaling
with locking), or a hosted cron hitting an internal token-secured endpoint.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.jobs import definitions

logger = logging.getLogger("backend.jobs.scheduler")

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        definitions.billing_cycle_kickoff, "cron", hour=0, minute=15, id="billing_cycle_kickoff", replace_existing=True
    )
    scheduler.add_job(
        definitions.reading_window_deadline_check,
        "cron",
        hour=0,
        minute=30,
        id="reading_window_deadline_check",
        replace_existing=True,
    )
    scheduler.add_job(
        definitions.bill_due_date_check, "cron", hour=1, minute=0, id="bill_due_date_check", replace_existing=True
    )
    scheduler.add_job(definitions.fine_accrual, "cron", hour=1, minute=15, id="fine_accrual", replace_existing=True)
    scheduler.add_job(
        definitions.late_payment_reminder, "cron", hour=9, minute=0, id="late_payment_reminder", replace_existing=True
    )
    scheduler.add_job(
        definitions.import_job_cleanup, "cron", day_of_week="sun", hour=2, minute=0, id="import_job_cleanup", replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs.", len(scheduler.get_jobs()))
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
