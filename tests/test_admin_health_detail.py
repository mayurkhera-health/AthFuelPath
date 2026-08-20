"""Phase-1 health drill-down: per-check detail endpoint, incident filtering,
and single-check re-run. Externals stubbed as in test_admin_health.py."""

import os
os.environ["DB_PATH"] = ":memory:"

import json

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth, bedrock_client, health_service
from api.routes import admin_health
from api.main import app

PASSWORD = "s3cret-admin"


def _wipe(conn):
    conn.commit()
    tables = [
        r["table_name"]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name != 'schema_migrations'"
        ).fetchall()
    ]
    if tables:
        conn.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
    conn.commit()


@pytest.fixture
def client(monkeypatch):
    keepalive = get_conn()
    init_db()
    run_all()
    _wipe(keepalive)
    with keepalive.cursor() as cur:
        cur.executemany(
            "INSERT INTO health_checks (check_name, status) VALUES (%s, 'unknown') "
            "ON CONFLICT (check_name) DO NOTHING",
            [(n,) for n in health_service.CHECK_ORDER])
    keepalive.commit()

    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key")
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_ALERT_PARENT_ID", raising=False)
    monkeypatch.delenv("ADMIN_ALERT_EMAIL", raising=False)
    monkeypatch.setattr(bedrock_client, "is_configured", lambda: False)
    admin_auth._failed_logins.clear()
    admin_health._last_run["t"] = 0.0
    admin_health._last_single_run.clear()

    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {c.post('/api/admin/login', json={'password': PASSWORD}).json()['token']}"})
        yield c
    keepalive.close()


def _seed_incidents(conn):
    # chronological insert order, as production writes them (endpoint sorts by id DESC)
    _exec_retry(conn, "INSERT INTO health_incidents (check_name, from_status, to_status, detail, created_at) VALUES (%s, %s, %s, %s, %s)",
                ("scheduler_calendar_sync", "red", "green", "tick 3m ago", "2026-07-01T09:00:00"))
    _exec_retry(conn, "INSERT INTO health_incidents (check_name, from_status, to_status, detail, created_at) VALUES (%s, %s, %s, %s, %s)",
                ("expo_push", "unknown", "green", "10/10 recent sends OK", "2026-07-04T10:00:00"))
    _exec_retry(conn, "INSERT INTO health_incidents (check_name, from_status, to_status, detail, created_at) VALUES (%s, %s, %s, %s, %s)",
                ("scheduler_calendar_sync", "green", "red", "last run 443 min ago (> 420)", "2026-07-05T03:12:00"))
    conn.commit()


def _exec_retry(conn, sql, params):
    # The app's startup catch-up thread can briefly hold a write lock on the
    # shared DB — retry instead of flaking.
    import psycopg, time as _t
    for _ in range(50):
        try:
            conn.execute(sql, params)
            return
        except psycopg.errors.OperationalError:
            conn.rollback()
            _t.sleep(0.05)
    conn.execute(sql, params)


# ── incidents filter ───────────────────────────────────────────────────────────

def test_incidents_filter_by_check_name(client):
    conn = get_conn()
    _seed_incidents(conn); conn.close()
    body = client.get("/api/admin/health/incidents?check_name=scheduler_calendar_sync").json()
    assert len(body["items"]) == 2
    assert all(i["check_name"] == "scheduler_calendar_sync" for i in body["items"])
    # unfiltered still returns everything
    assert len(client.get("/api/admin/health/incidents").json()["items"]) == 3


# ── per-check detail ───────────────────────────────────────────────────────────

def test_detail_requires_auth():
    with TestClient(app) as anon:
        assert anon.get("/api/admin/health/checks/db_writable").status_code == 401


def test_detail_unknown_check_404(client):
    assert client.get("/api/admin/health/checks/not_a_check").status_code == 404


def test_detail_basic_shape_and_incidents(client):
    conn = get_conn()
    _seed_incidents(conn); conn.close()
    body = client.get("/api/admin/health/checks/scheduler_calendar_sync").json()
    assert body["check"]["check_name"] == "scheduler_calendar_sync"
    assert [i["created_at"] for i in body["incidents"]] == ["2026-07-05T03:12:00", "2026-07-01T09:00:00"]
    # threshold spelled out so the UI can say "443 min vs 420 allowed"
    assert body["threshold"]["red_above"] == health_service.CALSYNC_STALE_MIN


def test_detail_scheduler_includes_heartbeat_evidence(client):
    conn = get_conn()
    _exec_retry(conn,
        "INSERT INTO scheduler_heartbeats (job_name, last_run_at, last_success_at, last_error, meta) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at, "
        "last_success_at = EXCLUDED.last_success_at, last_error = EXCLUDED.last_error, meta = EXCLUDED.meta",
        ("calendar_sync", "2026-07-05T02:00:00", "2026-07-04T20:00:00", "boom: provider 503", json.dumps({"attempted": 3, "succeeded": 2})))
    conn.commit(); conn.close()
    body = client.get("/api/admin/health/checks/scheduler_calendar_sync").json()
    ev = body["evidence"]
    assert ev["kind"] == "heartbeat"
    assert ev["last_run_at"] == "2026-07-05T02:00:00"
    assert ev["last_error"] == "boom: provider 503"
    assert ev["meta"] == {"attempted": 3, "succeeded": 2}


def test_detail_expo_push_includes_recent_sends(client):
    conn = get_conn()
    _exec_retry(conn, "INSERT INTO expo_push_log (success, detail, created_at) VALUES (%s, %s, %s)",
                (1, "ok", "2026-07-05T01:00:00"))
    _exec_retry(conn, "INSERT INTO expo_push_log (success, detail, created_at) VALUES (%s, %s, %s)",
                (0, "DeviceNotRegistered", "2026-07-05T02:00:00"))
    conn.commit(); conn.close()
    body = client.get("/api/admin/health/checks/expo_push").json()
    ev = body["evidence"]
    assert ev["kind"] == "push_log"
    assert len(ev["sends"]) == 2
    assert ev["sends"][0]["detail"] == "DeviceNotRegistered"   # newest first
    assert ev["sends"][0]["success"] is False


def test_detail_simple_probe_has_no_evidence(client):
    body = client.get("/api/admin/health/checks/db_writable").json()
    assert body["evidence"] is None


# ── single-check re-run ────────────────────────────────────────────────────────

def test_run_single_check_updates_only_that_check(client):
    r = client.post("/api/admin/health/run?check_name=db_writable")
    assert r.status_code == 200
    body = r.json()
    checks = {c["check_name"]: c for c in body["checks"]}
    assert checks["db_writable"]["status"] == "green"
    assert checks["db_writable"]["last_checked_at"] is not None
    # other checks untouched
    assert checks["disk_space"]["status"] == "unknown"
    assert checks["disk_space"]["last_checked_at"] is None


def test_run_single_check_unknown_404(client):
    assert client.post("/api/admin/health/run?check_name=nope").status_code == 404


def test_run_single_check_rate_limited_per_check(client):
    assert client.post("/api/admin/health/run?check_name=db_writable").status_code == 200
    assert client.post("/api/admin/health/run?check_name=db_writable").status_code == 429
    # a different check is not blocked by db_writable's cooldown
    assert client.post("/api/admin/health/run?check_name=disk_space").status_code == 200


def test_full_run_still_works_and_rate_limits(client):
    assert client.post("/api/admin/health/run").status_code == 200
    assert client.post("/api/admin/health/run").status_code == 429
