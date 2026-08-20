"""
System Health monitoring — active probes + passive signals + scheduler
heartbeats folded into one health_checks table, with transition detection that
writes incidents and fires alerts (see health_alerts).

Design constraints (deliberately small): ~9 checks, one 15-min job + one daily
job, best-effort everywhere. A crashing check marks itself red and never kills
the runner. Reuses existing clients — bedrock_client, email_service, the Expo
push path — rather than building parallel ones.
"""

import json
import logging
import os
import shutil
import smtplib
import ssl
import time
from datetime import datetime, timedelta

import boto3
from botocore.config import Config

from api.database import get_conn
from api.services import bedrock_client, health_alerts

log = logging.getLogger(__name__)

# Canonical display order for the admin grid.
CHECK_ORDER = [
    "bedrock_ping", "gmail_smtp", "db_writable", "disk_space",
    "scheduler_notifications", "scheduler_calendar_sync", "calendar_sync_systemic",
    "expo_push", "bedrock_inference",
]

DISK_RED_PCT = 80.0
NOTIF_STALE_MIN = 20        # 15-min job + tolerance
CALSYNC_STALE_MIN = 7 * 60  # 6-h job + tolerance (alert threshold — do not change)
CALSYNC_CADENCE_MIN = 6 * 60  # the job's own cadence; drives the startup catch-up decision
EXPO_WINDOW = 10            # last N sends define the passive expo signal


def _now() -> str:
    return datetime.utcnow().isoformat()


def _minutes_since(iso: str):
    try:
        return (datetime.utcnow() - datetime.fromisoformat(iso)).total_seconds() / 60.0
    except Exception:
        return None


# ── Individual checks: each returns (status, detail, metric_value) ────────────
def _bedrock_control_client():
    # Control-plane client ("bedrock", not "bedrock-runtime") for the free
    # list-models ping. Reuses the app's region + default credential chain.
    return boto3.client(
        "bedrock", region_name=bedrock_client._region(),
        config=Config(connect_timeout=10, read_timeout=10, retries={"max_attempts": 1}),
    )


def check_bedrock_ping(conn):
    if not bedrock_client.is_configured():
        return "unknown", "AWS not configured", None
    t0 = time.monotonic()
    try:
        _bedrock_control_client().list_foundation_models()
        ms = round((time.monotonic() - t0) * 1000)
        return "green", f"ping {ms}ms", float(ms)
    except Exception as e:
        return "red", f"ping failed: {e}"[:200], None


def check_bedrock_inference(conn):
    if not bedrock_client.is_configured():
        return "unknown", "AWS not configured", None
    t0 = time.monotonic()
    try:
        # Minimal, ~free real inference — catches model-access/quota issues the
        # control-plane ping can't. Cheapest configured model, tiny max_tokens.
        txt = bedrock_client.converse_text(user="Reply with the single word ok.", max_tokens=5, temperature=0)
        ms = round((time.monotonic() - t0) * 1000)
        if txt and txt.strip():
            return "green", f"inference OK ({ms}ms)", float(ms)
        return "red", "empty inference response", None
    except Exception as e:
        return "red", f"inference failed: {e}"[:200], None


def check_gmail_smtp(conn):
    user = os.getenv("GMAIL_USER")
    pw = os.getenv("GMAIL_APP_PASSWORD")
    if not (user and pw):
        return "unknown", "not configured", None
    t0 = time.monotonic()
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=10) as s:
            s.login(user, pw)  # connect + auth only — NO email sent
        ms = round((time.monotonic() - t0) * 1000)
        return "green", f"login OK ({ms}ms)", float(ms)
    except Exception as e:
        return "red", f"auth/connect failed: {e}"[:200], None


def check_db_writable(conn):
    try:
        conn.execute(
            "INSERT INTO health_scratch (id, v) VALUES (1, %s) "
            "ON CONFLICT (id) DO UPDATE SET v = EXCLUDED.v",
            (_now(),))
        conn.execute("DELETE FROM health_scratch WHERE id = 1")
        return "green", "writable", None
    except Exception as e:
        conn.rollback()
        return "red", f"write failed: {e}"[:200], None


def _disk_path() -> str:
    db = os.getenv("DB_PATH", "")
    d = os.path.dirname(db)
    return d if (d and os.path.isdir(d)) else "/"


def check_disk_space(conn):
    try:
        total, used, _free = shutil.disk_usage(_disk_path())
        pct = round(100 * used / total, 1)
        status = "red" if pct >= DISK_RED_PCT else "green"
        return status, f"{pct}% used of {round(total / 1e9, 1)}GB volume", pct
    except Exception as e:
        return "red", f"disk check failed: {e}"[:200], None


def _check_scheduler(conn, job_name, max_minutes):
    row = conn.execute(
        "SELECT last_run_at FROM scheduler_heartbeats WHERE job_name = %s", (job_name,)).fetchone()
    if not row or not row["last_run_at"]:
        return "unknown", "no run recorded yet", None
    mins = _minutes_since(row["last_run_at"])
    if mins is None:
        return "unknown", "unparseable heartbeat", None
    if mins > max_minutes:
        return "red", f"last run {int(mins)} min ago (> {max_minutes})", float(round(mins, 1))
    return "green", f"tick {int(mins)}m ago", float(round(mins, 1))


def check_scheduler_notifications(conn):
    return _check_scheduler(conn, "notifications", NOTIF_STALE_MIN)


def check_scheduler_calendar_sync(conn):
    return _check_scheduler(conn, "calendar_sync", CALSYNC_STALE_MIN)


def check_calendar_sync_systemic(conn):
    row = conn.execute(
        "SELECT meta FROM scheduler_heartbeats WHERE job_name = 'calendar_sync'").fetchone()
    if not row or not row["meta"]:
        return "unknown", "no sync tick recorded", None
    try:
        meta = json.loads(row["meta"])
    except Exception:
        return "unknown", "no counts recorded", None
    attempted = int(meta.get("attempted", 0) or 0)
    succeeded = int(meta.get("succeeded", 0) or 0)
    if attempted == 0:
        return "unknown", "no feeds to sync", None
    if succeeded == 0:
        return "red", f"0/{attempted} feeds succeeded — possible provider change", 0.0
    return "green", f"{succeeded}/{attempted} feeds OK", float(round(succeeded / attempted, 3))


def check_expo_push(conn):
    rows = conn.execute(
        "SELECT success FROM expo_push_log ORDER BY id DESC LIMIT %s", (EXPO_WINDOW,)).fetchall()
    if not rows:
        return "unknown", "no recent sends", None
    fails = sum(1 for r in rows if not r["success"])
    if fails == len(rows):
        return "red", f"last {len(rows)} sends all failed", 1.0
    return "green", f"{len(rows) - fails}/{len(rows)} recent sends OK", float(round(fails / len(rows), 3))


# Suites. expo_push is passive (reads the log) but evaluated on the 15-min tick.
CHECKS_15MIN = [
    ("bedrock_ping", check_bedrock_ping),
    ("gmail_smtp", check_gmail_smtp),
    ("db_writable", check_db_writable),
    ("disk_space", check_disk_space),
    ("scheduler_notifications", check_scheduler_notifications),
    ("scheduler_calendar_sync", check_scheduler_calendar_sync),
    ("calendar_sync_systemic", check_calendar_sync_systemic),
    ("expo_push", check_expo_push),
]
CHECKS_DAILY = [
    ("bedrock_inference", check_bedrock_inference),
]


# ── Runner: apply results, detect transitions, write incidents, alert ─────────
def _apply_result(conn, name, status, detail, metric, now):
    old = conn.execute("SELECT status FROM health_checks WHERE check_name = %s", (name,)).fetchone()
    old_status = old["status"] if old else "unknown"

    conn.execute("INSERT INTO health_checks (check_name, status) VALUES (%s, 'unknown') "
                 "ON CONFLICT DO NOTHING", (name,))
    sets = "status=%s, detail=%s, metric_value=%s, last_checked_at=%s"
    params = [status, detail, metric, now]
    if status == "green":
        sets += ", last_green_at=%s"; params.append(now)
    elif status == "red":
        sets += ", last_red_at=%s"; params.append(now)
    params.append(name)
    conn.execute(f"UPDATE health_checks SET {sets} WHERE check_name = %s", params)

    if status != old_status:
        cur = conn.execute(
            "INSERT INTO health_incidents (check_name, from_status, to_status, detail, created_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id", (name, old_status, status, detail, now))
        incident_id = cur.fetchone()["id"]
        try:
            note = health_alerts.dispatch(conn, name, old_status, status, detail)
        except Exception as e:  # alerting must never crash the runner
            conn.rollback()
            log.warning("health alert failed for %s: %s", name, e)
            note = f"alert error: {e}"
        if note:
            conn.execute("UPDATE health_incidents SET detail = COALESCE(detail,'') || ' [alert: ' || %s || ']' "
                         "WHERE id = %s", (note, incident_id))


def _run_checks(conn, checks):
    now = _now()
    for name, fn in checks:
        try:
            status, detail, metric = fn(conn)
        except Exception as e:  # a crashing check is red, never kills the runner
            conn.rollback()
            status, detail, metric = "red", f"check crashed: {e}"[:200], None
        _apply_result(conn, name, status, detail, metric, now)
    conn.commit()


def run_health_tick():
    conn = get_conn()
    try:
        _run_checks(conn, CHECKS_15MIN)
    finally:
        conn.close()


def run_health_daily():
    conn = get_conn()
    try:
        _run_checks(conn, CHECKS_DAILY)
    finally:
        conn.close()


def get_health_snapshot(conn) -> dict:
    rows = [dict(r) for r in conn.execute("SELECT * FROM health_checks").fetchall()]
    order = {n: i for i, n in enumerate(CHECK_ORDER)}
    rows.sort(key=lambda r: order.get(r["check_name"], 999))
    statuses = [r["status"] for r in rows]
    overall = "red" if "red" in statuses else ("unknown" if "unknown" in statuses else "green")
    return {"overall": overall, "checks": rows}


# ── Per-check drill-down (admin detail drawer) ────────────────────────────────
ALL_CHECKS = dict(CHECKS_15MIN + CHECKS_DAILY)

# What the metric means and where it goes red, so the UI can spell out
# "443 min vs 420 allowed" instead of making the founder decode the detail string.
THRESHOLDS = {
    "disk_space":              {"metric": "% of data volume used", "red_above": DISK_RED_PCT, "unit": "%"},
    "scheduler_notifications": {"metric": "minutes since last run", "red_above": NOTIF_STALE_MIN, "unit": "min"},
    "scheduler_calendar_sync": {"metric": "minutes since last run", "red_above": CALSYNC_STALE_MIN, "unit": "min"},
}

# Which heartbeat row backs each scheduler-derived check.
_HEARTBEAT_JOB = {
    "scheduler_notifications": "notifications",
    "scheduler_calendar_sync": "calendar_sync",
    "calendar_sync_systemic":  "calendar_sync",
}


def _heartbeat_evidence(conn, job_name):
    row = conn.execute(
        "SELECT job_name, last_run_at, last_success_at, last_error, meta "
        "FROM scheduler_heartbeats WHERE job_name = %s", (job_name,)).fetchone()
    if not row:
        return {"kind": "heartbeat", "job_name": job_name, "last_run_at": None,
                "last_success_at": None, "last_error": None, "meta": None}
    ev = dict(row)
    ev["kind"] = "heartbeat"
    try:
        ev["meta"] = json.loads(ev["meta"]) if ev["meta"] else None
    except Exception:
        ev["meta"] = None
    return ev


def get_check_detail(name: str, conn) -> dict | None:
    """Everything the drawer needs for one sensor, or None for an unknown name."""
    if name not in ALL_CHECKS:
        return None
    check = conn.execute("SELECT * FROM health_checks WHERE check_name = %s", (name,)).fetchone()
    incidents = conn.execute(
        "SELECT * FROM health_incidents WHERE check_name = %s ORDER BY id DESC LIMIT 20",
        (name,)).fetchall()

    evidence = None
    if name in _HEARTBEAT_JOB:
        evidence = _heartbeat_evidence(conn, _HEARTBEAT_JOB[name])
        if name == "calendar_sync_systemic":
            evidence["feeds_connected"] = conn.execute(
                "SELECT COUNT(*) AS count FROM athletes WHERE COALESCE(byga_ics_url,'') != '' "
                "OR COALESCE(playmetrics_ics_url,'') != ''").fetchone()["count"]
    elif name == "expo_push":
        rows = conn.execute(
            "SELECT success, detail, created_at FROM expo_push_log ORDER BY id DESC LIMIT %s",
            (EXPO_WINDOW,)).fetchall()
        evidence = {"kind": "push_log",
                    "sends": [{"success": bool(r["success"]), "detail": r["detail"],
                               "created_at": r["created_at"]} for r in rows]}

    return {
        "check":     dict(check) if check else {"check_name": name, "status": "unknown"},
        "threshold": THRESHOLDS.get(name),
        "incidents": [dict(r) for r in incidents],
        "evidence":  evidence,
    }


def run_single_check(name: str) -> bool:
    """Re-run one check on demand. Returns False for an unknown name."""
    fn = ALL_CHECKS.get(name)
    if fn is None:
        return False
    conn = get_conn()
    try:
        _run_checks(conn, [(name, fn)])
    finally:
        conn.close()
    return True


# ── Instrumentation of the existing scheduler jobs (no logic change inside) ───
def instrument_job(job_name, fn):
    """Wrap an existing scheduler job so it upserts a heartbeat at start
    (last_run_at) and on clean finish (last_success_at); errors record last_error
    and re-raise. Heartbeat writes are best-effort and never mask the job."""
    def wrapper():
        _hb(job_name, run=True)
        try:
            fn()
        except Exception as e:
            _hb(job_name, error=str(e)[:300])
            raise
        _hb(job_name, success=True)
    wrapper.__name__ = f"instrumented_{job_name}"
    return wrapper


def _hb(job_name, run=False, success=False, error=None):
    try:
        conn = get_conn()
        try:
            conn.execute("INSERT INTO scheduler_heartbeats (job_name) VALUES (%s) ON CONFLICT DO NOTHING",
                         (job_name,))
            if run:
                conn.execute("UPDATE scheduler_heartbeats SET last_run_at=%s, last_error=NULL WHERE job_name=%s",
                             (_now(), job_name))
            if success:
                conn.execute("UPDATE scheduler_heartbeats SET last_success_at=%s WHERE job_name=%s",
                             (_now(), job_name))
            if error is not None:
                conn.execute("UPDATE scheduler_heartbeats SET last_error=%s WHERE job_name=%s",
                             (error, job_name))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.debug("heartbeat write failed for %s", job_name, exc_info=True)


def record_expo_send(success: bool, detail: str = ""):
    """Called by the Expo push path (send_expo_push) to log each real send for
    the passive expo_push check. Best-effort."""
    try:
        conn = get_conn()
        try:
            conn.execute("INSERT INTO expo_push_log (success, detail) VALUES (%s, %s)",
                         (1 if success else 0, (detail or "")[:200]))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.debug("expo_push_log write failed", exc_info=True)


def record_calendar_sync_stats(attempted: int, succeeded: int):
    """Called at the end of the calendar-sync tick — feeds calendar_sync_systemic.
    Stored on the calendar_sync heartbeat row's meta. Best-effort."""
    try:
        conn = get_conn()
        try:
            conn.execute("INSERT INTO scheduler_heartbeats (job_name) VALUES ('calendar_sync') "
                         "ON CONFLICT DO NOTHING")
            conn.execute("UPDATE scheduler_heartbeats SET meta=%s WHERE job_name='calendar_sync'",
                         (json.dumps({"attempted": attempted, "succeeded": succeeded, "at": _now()}),))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.debug("calendar sync stats write failed", exc_info=True)


# ── Startup catch-up support (Option B) ──────────────────────────────────────
def calendar_sync_freshness(conn, cadence_min: int = CALSYNC_CADENCE_MIN):
    """Read-only startup classification for the calendar_sync job. Returns a tuple:
        ('initial', None, None)  — no prior successful run recorded
        ('stale',   mins, iso)   — last success older than the 6-h cadence
        ('fresh',   mins, iso)   — last success within the cadence
    Keyed on last_success_at (a job that keeps *running* but never *succeeds* stays
    'stale', so it keeps being retried)."""
    row = conn.execute(
        "SELECT last_success_at FROM scheduler_heartbeats WHERE job_name = 'calendar_sync'"
    ).fetchone()
    last = row["last_success_at"] if row else None
    if not last:
        return "initial", None, None
    mins = _minutes_since(last)
    if mins is None:                       # unparseable → treat as no prior run (run once)
        return "initial", None, None
    return ("stale" if mins > cadence_min else "fresh"), mins, last


def claim_calendar_sync_catchup(conn, cadence_min: int = CALSYNC_CADENCE_MIN) -> bool:
    """Atomically claim the single startup catch-up run for calendar_sync. Returns
    True iff THIS caller won the claim (heartbeat NULL, or stale by > cadence).

    Multi-instance safe: the claim stamps last_run_at as the lock token AND gates on it,
    so a second instance that boots together sees last_run_at already bumped and gets
    False — only one catch-up runs. Gating on last_run_at (not just last_success_at,
    which the claim does not update) is what makes the CAS single-winner. The actual run
    re-stamps last_run/last_success via instrument_job."""
    now = _now()
    cutoff = (datetime.utcnow() - timedelta(minutes=cadence_min)).isoformat()
    conn.execute("INSERT INTO scheduler_heartbeats (job_name) VALUES ('calendar_sync') "
                 "ON CONFLICT DO NOTHING")
    cur = conn.execute(
        "UPDATE scheduler_heartbeats SET last_run_at = %s "
        "WHERE job_name = 'calendar_sync' "
        "  AND (last_success_at IS NULL OR last_success_at <= %s) "  # stale/never succeeded
        "  AND (last_run_at     IS NULL OR last_run_at     <= %s)",   # and not just claimed
        (now, cutoff, cutoff),
    )
    conn.commit()
    return cur.rowcount == 1
