"""Admin System Health endpoints: auth gating, snapshot shape, on-demand run +
rate limit, incidents. Externals stubbed so a run touches no network."""

import os
os.environ["DB_PATH"] = ":memory:"

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
    for n in health_service.CHECK_ORDER:
        keepalive.execute(
            "INSERT INTO health_checks (check_name, status) VALUES (%s, 'unknown') "
            "ON CONFLICT (check_name) DO NOTHING",
            (n,))
    keepalive.commit()

    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key")
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_ALERT_PARENT_ID", raising=False)
    monkeypatch.delenv("ADMIN_ALERT_EMAIL", raising=False)
    monkeypatch.setattr(bedrock_client, "is_configured", lambda: False)  # no AWS calls
    admin_auth._failed_logins.clear()
    admin_health._last_run["t"] = 0.0  # reset the run rate-limiter

    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {c.post('/api/admin/login', json={'password': PASSWORD}).json()['token']}"})
        yield c
    keepalive.close()


def test_health_endpoints_require_token():
    with TestClient(app) as anon:
        assert anon.get("/api/admin/health").status_code == 401
        assert anon.get("/api/admin/health/incidents").status_code == 401
        assert anon.post("/api/admin/health/run").status_code == 401


def test_snapshot_lists_all_checks_with_overall(client):
    body = client.get("/api/admin/health").json()
    assert body["overall"] in ("green", "red", "unknown")
    names = {c["check_name"] for c in body["checks"]}
    assert names == set(health_service.CHECK_ORDER)   # all 9 present
    assert body["overall"] == "unknown"               # nothing checked yet


def test_run_now_executes_then_rate_limits(client):
    r1 = client.post("/api/admin/health/run")
    assert r1.status_code == 200
    checks = {c["check_name"]: c for c in r1.json()["checks"]}
    assert checks["db_writable"]["status"] == "green"      # a real probe ran
    assert checks["db_writable"]["last_checked_at"] is not None
    # second immediate run is throttled
    assert client.post("/api/admin/health/run").status_code == 429


def test_incidents_endpoint_returns_transitions(client):
    client.post("/api/admin/health/run")   # unknown -> green/red transitions recorded
    body = client.get("/api/admin/health/incidents?limit=50").json()
    assert isinstance(body["items"], list)
    assert any(i["check_name"] == "db_writable" and i["to_status"] == "green" for i in body["items"])
