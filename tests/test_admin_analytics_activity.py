"""Analytics additions: live activity feed (PostHog + batched name resolution)
and the DB-sourced calendar-platform breakdown."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth, posthog_client
from api.routes.admin_analytics import calendar_platform_breakdown
from api.main import app

PASSWORD = "s3cret-admin"


def _wipe(conn):
    conn.commit()
    tables = [r["table_name"] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name != 'schema_migrations'"
    ).fetchall()]
    if tables:
        conn.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
    conn.commit()


@pytest.fixture
def ctx(monkeypatch):
    ka = get_conn()
    init_db()
    run_all()
    _wipe(ka)
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key")
    admin_auth._failed_logins.clear()
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {c.post('/api/admin/login', json={'password': PASSWORD}).json()['token']}"})
        yield c, ka
    ka.close()


def _parent(conn, name, email):
    return conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (%s, %s, 't', TRUE) RETURNING id",
        (name, email)).fetchone()["id"]


def _athlete(conn, pid, *, byga=None, playmetrics=None):
    return conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, "
        "byga_ics_url, playmetrics_ics_url) VALUES (%s, 'Kid', 12, 'M', 90, 5, 2, %s, %s) RETURNING id",
        (pid, byga, playmetrics)).fetchone()["id"]


# ── posthog_client.recent_activity ───────────────────────────────────────────
def _configure(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "1")
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "phx_test")
    posthog_client._cache.clear()
    posthog_client._last_forced.clear()


def test_recent_activity_filters_noise_and_limits(monkeypatch):
    _configure(monkeypatch)
    captured = {}
    def fake(sql, name="admin"):
        captured["sql"] = sql
        return [["meal_plan_viewed", "2026-07-03T10:00:00Z", 1]]
    monkeypatch.setattr(posthog_client, "_hogql", fake)

    res = posthog_client.recent_activity(limit=20)
    assert res["available"] is True
    sql = captured["sql"]
    for ev in posthog_client.ACTIVITY_EVENTS:      # all 7 action events present
        assert f"'{ev}'" in sql
    assert "app_opened" not in sql                 # noise/lifecycle event excluded
    assert "$autocapture" not in sql and "$screen" not in sql
    assert "LIMIT 20" in sql
    assert res["data"]["rows"][0]["event"] == "meal_plan_viewed"


def test_recent_activity_is_cached(monkeypatch):
    _configure(monkeypatch)
    calls = {"n": 0}
    def fake(sql, name="admin"):
        calls["n"] += 1
        return []
    monkeypatch.setattr(posthog_client, "_hogql", fake)
    posthog_client.recent_activity(20)
    posthog_client.recent_activity(20)             # served from the 60s cache
    assert calls["n"] == 1


def test_recent_activity_degrades_when_unconfigured(monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_ID", raising=False)
    monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)
    res = posthog_client.recent_activity(20)
    assert res["available"] is False and "reason" in res


# ── /analytics/activity endpoint ─────────────────────────────────────────────
def test_activity_requires_token():
    with TestClient(app) as anon:
        assert anon.get("/api/admin/analytics/activity").status_code == 401


def test_activity_resolves_names_with_unknown_fallback(ctx, monkeypatch):
    c, ka = ctx
    pid = _parent(ka, "Sarah Lee", "sarah@x.com")
    ka.commit()
    monkeypatch.setattr(posthog_client, "recent_activity", lambda limit=20, force=False: {
        "available": True, "as_of": "2026-07-03T10:00:00Z",
        "data": {"rows": [
            {"event": "meal_plan_viewed", "timestamp": "2026-07-03T10:00:00Z", "parent_id": pid},
            {"event": "problem_reported", "timestamp": "2026-07-03T09:00:00Z", "parent_id": 99999},
            {"event": "calendar_connected", "timestamp": "2026-07-03T08:00:00Z", "parent_id": None},
        ]},
    })
    body = c.get("/api/admin/analytics/activity").json()
    assert body["available"] is True
    names = [r["parent_first"] for r in body["rows"]]
    assert names == ["Sarah", "Unknown", "Unknown"]   # resolved, id-not-in-db, no-id


def test_activity_degrades_gracefully(ctx, monkeypatch):
    c, _ = ctx
    monkeypatch.setattr(posthog_client, "recent_activity",
                        lambda limit=20, force=False: {"available": False, "reason": "PostHog not connected"})
    assert c.get("/api/admin/analytics/activity").json() == {"available": False, "reason": "PostHog not connected"}


# ── calendar_platform_breakdown ──────────────────────────────────────────────
def test_calendar_breakdown_counts_and_byga_priority(ctx):
    c, ka = ctx
    a = _parent(ka, "Byga Fam", "a@x.com"); _athlete(ka, a, byga="https://byga/a.ics")
    b = _parent(ka, "PM Fam", "b@x.com"); _athlete(ka, b, playmetrics="https://pm/b.ics")
    d = _parent(ka, "Both Fam", "d@x.com"); _athlete(ka, d, byga="https://byga/d.ics", playmetrics="https://pm/d.ics")
    e = _parent(ka, "No Cal Fam", "e@x.com"); _athlete(ka, e)          # athlete, no url
    _parent(ka, "No Athlete Fam", "f@x.com")                           # no athlete at all
    ka.commit()

    r = calendar_platform_breakdown(ka)
    assert r["byga"] == 2            # a + d (both-set → BYGA wins)
    assert r["playmetrics"] == 1     # b only
    assert r["not_connected"] == 2   # e (no url) + f (no athlete)
    assert r["total_families"] == 5
    assert r["byga"] + r["playmetrics"] + r["not_connected"] == r["total_families"]
    assert r["source"] == "db"


def test_calendar_breakdown_in_overview_response(ctx):
    c, ka = ctx
    a = _parent(ka, "Byga Fam", "a@x.com"); _athlete(ka, a, byga="https://byga/a.ics")
    ka.commit()
    body = c.get("/api/admin/analytics/overview").json()
    assert body["calendar_platform"]["byga"] == 1
    assert body["calendar_platform"]["source"] == "db"
