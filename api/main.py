import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO)
from pathlib import Path
from fastapi import FastAPI

from api.startup import run_startup, StartupError

logger = logging.getLogger(__name__)

# Cloud Run runs multiple instances; an in-process APScheduler duplicated
# across every instance means duplicate/unreliable job execution. Fly.io
# (single instance) can keep it — Cloud Run sets this to "false" and instead
# triggers api/job_runner.py's entry points via Cloud Run Jobs / Cloud
# Scheduler. Defaults to enabled so existing (Fly.io) deployments are
# unaffected unless this is explicitly set.
IN_PROCESS_SCHEDULER_ENABLED = os.getenv("IN_PROCESS_SCHEDULER_ENABLED", "true").lower() not in ("false", "0", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # CRITICAL: schema migrations are no longer run from the API process (see
    # db/postgres_migrate.py — run it before deploying instead). run_startup()
    # verifies the DB is reachable and migrated; if that fails, the exception
    # is allowed to propagate and stop the process from serving traffic — do
    # NOT wrap this in a broad try/except that logs and continues.
    try:
        run_startup()
    except StartupError:
        logger.exception("FATAL: startup readiness check failed — refusing to serve traffic")
        raise

    # Start the in-process scheduler HERE — @app.on_event("startup") is
    # ignored by Starlette when a lifespan handler is set. Only when
    # IN_PROCESS_SCHEDULER_ENABLED (see api/job_runner.py for the Cloud Run
    # alternative — same job functions, triggered externally instead).
    if IN_PROCESS_SCHEDULER_ENABLED:
        try:
            from api.services.notification_service import run_notification_tick
            from api.services.fueliq_notification_service import run_fueliq_notification_tick
            from api.services.ics_sync import build_calendar_sync_job, configure_calendar_sync_startup
            from api.services.health_service import instrument_job, run_health_tick, run_health_daily
            from api.services.fueliq_daily_challenge_service import run_daily_challenge_push
            from api.services.grocery_reset_service import run_grocery_reset_tick
            from api.services.grocery_reminder_service import run_grocery_reminder_tick
            # Wrap the two existing jobs so they record scheduler heartbeats — no change
            # to the jobs' own logic; the wrapper only stamps last_run/last_success.
            _scheduler.add_job(instrument_job("notifications", run_notification_tick), "interval", minutes=15,
                               id="notifications", replace_existing=True)
            _scheduler.add_job(instrument_job("fueliq_notifications", run_fueliq_notification_tick),
                               "interval", minutes=15,
                               id="fueliq_notifications", replace_existing=True)
            _scheduler.add_job(run_grocery_reset_tick, "interval", minutes=15,
                               id="grocery_reset", replace_existing=True)
            _scheduler.add_job(run_grocery_reminder_tick, "interval", minutes=15,
                               id="grocery_reminder", replace_existing=True)
            # calendar_sync is registered via build_calendar_sync_job() (instrument + skip-
            # if-running lock); configure_calendar_sync_startup() then handles Option B
            # (catch-up if stale/initial, re-anchor next run if fresh) — see ics_sync.py.
            _scheduler.add_job(build_calendar_sync_job(), "interval", hours=6,
                               id="calendar_sync", replace_existing=True)
            # System Health: active probes every 15 min, one daily inference probe.
            _scheduler.add_job(run_health_tick, "interval", minutes=15,
                               id="health", replace_existing=True)
            _scheduler.add_job(run_health_daily, "cron", hour=9,
                               id="health_daily", replace_existing=True)
            # Fuel IQ Daily Challenge: announce the day's challenge once, at a fixed
            # 5pm Pacific — explicit IANA timezone (not server-local) so it stays
            # correct across the PST/PDT transition. instrument_job() gives it the
            # same System Health heartbeat as the other daily jobs; the job itself
            # is separately guarded against double-send via push_sent_at.
            _scheduler.add_job(instrument_job("daily_challenge_push", run_daily_challenge_push),
                               "cron", hour=17, timezone="America/Los_Angeles",
                               id="daily_challenge_push", replace_existing=True)
            from api.services.snapshot_job import generate_all_snapshots
            _scheduler.add_job(
                generate_all_snapshots, "cron", hour=23,
                timezone="America/Los_Angeles",
                id="teamcoach_snapshot", replace_existing=True,
            )
            if not _scheduler.running:
                _scheduler.start()
            configure_calendar_sync_startup(_scheduler)
            logger.info("In-process schedulers started (notifications 15-min, fueliq_notifications 15-min, "
                        "calendar sync 6-hr, health 15-min + daily, daily challenge push 5pm PT, "
                        "grocery reset 15-min, grocery reminder 15-min, teamcoach snapshot 11pm PT).")
        except Exception:
            logger.exception("Scheduler failed to start")
    else:
        logger.info("IN_PROCESS_SCHEDULER_ENABLED=false — scheduled jobs must be triggered externally "
                    "via `python -m api.job_runner <job>` (Cloud Run Jobs / Cloud Scheduler).")

    yield


from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.routes import parents, athletes, events, nutrition, meals, recipes, analysis, reports, notifications, meal_plans, meal_plan_selections, today, water, knowledge, legal, library, auth, fuel_report, report_config, coach, shopping, support, onboarding, feedback, calendar, admin, admin_analytics, admin_health, admin_overview, admin_action_hub, plate, fueliq, fueliq_daily_challenge, instacart_feedback, instacart, teamcoach_auth, teamcoach_admin, teamcoach_dashboard, families
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI(
    title="Fueling2Win Soccer Nutrition API",
    description="Science-backed pediatric sports nutrition platform for athletes ages 13-17. Educational food guidance — NOT medical nutrition therapy.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=True combined with a wildcard origin is a known bad
    # pairing — browsers actually respond by echoing back the requesting
    # origin instead of "*" whenever credentials are on, so this
    # combination effectively grants every website credentialed access.
    # Every real auth mechanism here (session Bearer tokens, X-Admin-Key)
    # travels in a header the client sets explicitly, never a cookie, so
    # allow_credentials was never actually needed — dropping it (rather
    # than guessing at a fixed origin allowlist, which risks breaking the
    # same-origin web frontend/admin panel this app also serves via
    # StaticFiles, or a dev frontend on a different port) closes the gap
    # with no behavior change for any real client.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/api/auth",      tags=["0. Auth"])
app.include_router(parents.router,   prefix="/api/parents",   tags=["1. Parental Consent"])
app.include_router(families.router,  prefix="/api/families",  tags=["1b. Family Actions"])
app.include_router(athletes.router,  prefix="/api/athletes",  tags=["2. Athlete Profiles"])
app.include_router(onboarding.router, prefix="/api/onboarding", tags=["2b. Onboarding"])
app.include_router(events.router,    prefix="/api/events",    tags=["3. Schedule"])
app.include_router(nutrition.router, prefix="/api/nutrition", tags=["4-6. Nutrition Targets + Timing"])
app.include_router(meals.router,     prefix="/api/meals",     tags=["7-8. Recipes + Meal Tracking"])
app.include_router(recipes.router,   prefix="/api/recipes",   tags=["7. Recipe Database"])
app.include_router(analysis.router,  prefix="/api/analysis",  tags=["9. Nutrient Gap Analysis"])
app.include_router(reports.router,       prefix="/api/reports",       tags=["11. Reports"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["12. Notifications"])
app.include_router(meal_plans.router,            prefix="/api/meal-plans",   tags=["10. Meal Planner"])
app.include_router(meal_plan_selections.router,  prefix="/api/meal-plan",    tags=["10b. Meal Plan Selections"])
app.include_router(today.router,        prefix="/api/athletes",     tags=["13. Today Screen"])
app.include_router(water.router,        prefix="/api/water-log",    tags=["14. Water Log"])
app.include_router(knowledge.router,    prefix="/api/knowledge",    tags=["15. Knowledge Base"])
app.include_router(legal.router,        prefix="/api/legal",        tags=["16. Legal Documents"])
app.include_router(library.router,      prefix="/api/library",      tags=["17. Content Library"])
app.include_router(fuel_report.router,  prefix="/api/athletes",     tags=["18. Fuel Report v2"])
app.include_router(report_config.router, prefix="/api/report-config", tags=["19. Report Config"])
app.include_router(coach.router,         prefix="/api/coach",         tags=["20. Nutrition Coach"])
app.include_router(plate.router,         prefix="/api/plate",         tags=["20b. Performance Plate"])
app.include_router(shopping.router,      prefix="/api/shopping",      tags=["21. Shopping"])
app.include_router(support.router,       prefix="/api/support",       tags=["22. Support"])
app.include_router(feedback.router,      prefix="/api/feedback",      tags=["24. Feature Requests"])
app.include_router(instacart_feedback.router, prefix="/api/instacart", tags=["28. Instacart Handoff"])
app.include_router(instacart.router,          prefix="/api/instacart", tags=["28. Instacart Handoff"])
app.include_router(calendar.router,      prefix="/api/athletes",      tags=["25. Calendar Sync"])
app.include_router(admin.router,           prefix="/api/admin",           tags=["26. Admin"])
app.include_router(admin_analytics.router, prefix="/api/admin",           tags=["27. Admin Analytics"])
app.include_router(admin_health.router,    prefix="/api/admin",           tags=["28. Admin Health"])
app.include_router(admin_overview.router,  prefix="/api/admin",           tags=["29. Admin Overview"])
app.include_router(admin_action_hub.router, prefix="/api/admin",          tags=["30. Admin Action Hub"])
app.include_router(fueliq.router,        prefix="/api/athletes",      tags=["31. Fuel IQ"])
app.include_router(fueliq_daily_challenge.router, prefix="/api/athletes", tags=["32. Fuel IQ Daily Challenge"])
app.include_router(teamcoach_auth.router, prefix="/api/team-coach/auth", tags=["33. TeamCoach Auth"])
app.include_router(teamcoach_admin.router, prefix="/api/admin/team-coach", tags=["34. TeamCoach Admin"])
app.include_router(teamcoach_dashboard.router, prefix="/api/team-coach/teams", tags=["35. TeamCoach Dashboard"])


_scheduler = BackgroundScheduler()


@app.get("/api/info")
def root():
    return {
        "app": "Fueling2Win Soccer Nutrition Platform",
        "version": "1.0.0",
        "launch_date": "June 16, 2026",
        "built_by": "Purvi Shah MS, RDN | Food Explorers LLC",
        "science": "Everett MD 2025 | Boston Children's Hospital RDN | AAP | ACSM 2016",
        "disclaimer": "Fueling2Win provides educational food guidance — not medical nutrition therapy.",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    """Readiness check (migration/postgres-cloud-run, Phase 13): verifies DB
    connectivity AND that at least one migration has actually been applied —
    distinct from /health, which is pure liveness. Returns 503 (not 200) when
    not ready, so a load balancer / Cloud Run health check correctly holds
    traffic back. Never includes connection strings, credentials, or any
    other infrastructure detail in the response."""
    from fastapi import Response
    from fastapi.responses import JSONResponse
    from api.database import db_is_ready
    from db.postgres_migrate import latest_applied_version

    db_ok = db_is_ready()
    version = latest_applied_version() if db_ok else None
    ready_state = db_ok and version is not None

    body = {
        "status": "ready" if ready_state else "not_ready",
        "database": "connected" if db_ok else "unreachable",
        "schema_version": version,
    }
    return JSONResponse(body, status_code=200 if ready_state else 503)


class SPAStaticFiles(StaticFiles):
    """Serve the built React SPA and fall back to index.html for client-side
    routes (e.g. /admin, /admin/library) so deep links / refreshes don't 404.
    The app has no router library — it reads window.location.pathname on boot —
    so every non-file path must return index.html. Genuine /api/* misses still
    return a JSON 404 (they are excluded from the fallback)."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api"):
                response = await super().get_response("index.html", scope)
            else:
                raise
        # Cache policy: content-hashed build assets (/assets/index-<hash>.js) are
        # immutable and cache forever; everything else — index.html and the SPA
        # fallback — must revalidate every load so a new deploy shows up immediately
        # (previously index.html had no Cache-Control → browsers served it stale).
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


# Serve TeamCoach React app at /coach/ — must be before the catch-all / mount
_coach_static_dir = Path(__file__).parent.parent / "frontend-coach" / "dist"
if _coach_static_dir.exists():
    app.mount("/coach", StaticFiles(directory=str(_coach_static_dir), html=True), name="teamcoach-static")

# Serve React frontend — must be last so API routes take precedence
_static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if _static_dir.exists():
    app.mount("/", SPAStaticFiles(directory=str(_static_dir), html=True), name="static")
