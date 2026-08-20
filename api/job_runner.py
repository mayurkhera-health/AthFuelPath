"""
api/job_runner.py — standalone entry points for AthFuelPath's background jobs
(migration/postgres-cloud-run, Phase 6).

Cloud Run can run multiple instances of the API. Relying on the in-process
APScheduler (api/main.py's BackgroundScheduler, still used when
IN_PROCESS_SCHEDULER_ENABLED=true, e.g. on Fly.io's single-instance
deployment) would mean every instance runs its own copy of every job —
duplicate/unreliable execution. This module exposes the SAME job functions
(no business-logic changes — each one is imported unmodified from its
existing service module) as plain callables, one per Cloud Run Job /
Scheduler trigger, so exactly one instance of each job runs per invocation
regardless of how many API replicas are up.

Cadence groups, matching the existing APScheduler registration in
api/main.py's lifespan:

  quarter_hour      — notifications, fueliq_notifications, grocery_reset,
                       grocery_reminder, health (all every 15 min today)
  calendar_sync     — every 6 hours
  health_daily      — daily, 9am server-local
  daily_challenge_push — daily, 5pm America/Los_Angeles
  teamcoach_snapshot   — daily, 11pm America/Los_Angeles

Each quarter_hour sub-job keeps its own try/except so one job's failure
doesn't stop the others in the group from running (mirrors the isolation
the old in-process scheduler gave each job by registering them as separate
APScheduler jobs).

Usage:
    python -m api.job_runner quarter_hour
    python -m api.job_runner calendar_sync
    python -m api.job_runner health_daily
    python -m api.job_runner daily_challenge_push
    python -m api.job_runner teamcoach_snapshot
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_quarter_hour() -> None:
    from api.services.notification_service import run_notification_tick
    from api.services.fueliq_notification_service import run_fueliq_notification_tick
    from api.services.grocery_reset_service import run_grocery_reset_tick
    from api.services.grocery_reminder_service import run_grocery_reminder_tick
    from api.services.health_service import instrument_job, run_health_tick

    jobs = [
        ("notifications", instrument_job("notifications", run_notification_tick)),
        ("fueliq_notifications", instrument_job("fueliq_notifications", run_fueliq_notification_tick)),
        ("grocery_reset", run_grocery_reset_tick),
        ("grocery_reminder", run_grocery_reminder_tick),
        ("health", run_health_tick),
    ]
    failures = []
    for name, fn in jobs:
        try:
            fn()
            logger.info("quarter_hour job '%s' completed", name)
        except Exception:
            logger.exception("quarter_hour job '%s' FAILED", name)
            failures.append(name)
    if failures:
        # Non-zero exit so a Cloud Run Job execution is marked failed/retried,
        # but every job still got its own chance to run above (no early exit).
        raise SystemExit(f"quarter_hour: {len(failures)} job(s) failed: {failures}")


def _run_calendar_sync() -> None:
    from api.services.ics_sync import run_calendar_sync_tick
    from api.services.health_service import instrument_job
    instrument_job("calendar_sync", run_calendar_sync_tick)()


def _run_health_daily() -> None:
    from api.services.health_service import run_health_daily
    run_health_daily()


def _run_daily_challenge_push() -> None:
    from api.services.fueliq_daily_challenge_service import run_daily_challenge_push
    from api.services.health_service import instrument_job
    instrument_job("daily_challenge_push", run_daily_challenge_push)()


def _run_teamcoach_snapshot() -> None:
    from api.services.snapshot_job import generate_all_snapshots
    generate_all_snapshots()


JOBS = {
    "quarter_hour": _run_quarter_hour,
    "calendar_sync": _run_calendar_sync,
    "health_daily": _run_health_daily,
    "daily_challenge_push": _run_daily_challenge_push,
    "teamcoach_snapshot": _run_teamcoach_snapshot,
}


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1 or argv[0] not in JOBS:
        names = ", ".join(sorted(JOBS))
        print(f"Usage: python -m api.job_runner <{names}>", file=sys.stderr)
        raise SystemExit(2)

    job_name = argv[0]
    logger.info("job_runner: starting '%s'", job_name)
    JOBS[job_name]()
    logger.info("job_runner: '%s' done", job_name)


if __name__ == "__main__":
    main()
