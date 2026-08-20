"""Admin Analytics: DB-backed cards + funnel always available; PostHog mocked
both ways (success + unavailable). Dashboard must never depend on PostHog."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth, posthog_client
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


def _configure_posthog(monkeypatch):
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "phx_fake")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "123")
    posthog_client._cache.clear()


@pytest.fixture
def client(monkeypatch):
    keepalive = get_conn()
    init_db()
    run_all()
    _wipe(keepalive)  # clean slate — shared in-memory DB persists across tests
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key")
    monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_PROJECT_ID", raising=False)
    admin_auth._failed_logins.clear()
    posthog_client._cache.clear()
    posthog_client._last_forced.clear()

    # Two families; one athlete connected + has a meal plan → funnel + sync %.
    p1 = keepalive.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES ('A','a@x.com','t',TRUE) RETURNING id").fetchone()["id"]
    a1 = keepalive.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, byga_ics_url) "
        "VALUES (%s, 'Ann', 12, 'F', 90, 5, 2, 'https://byga/a.ics') RETURNING id", (p1,)).fetchone()["id"]
    keepalive.execute("INSERT INTO meal_plans (athlete_id, plan_date, slot_name) VALUES (%s, sqlite_today(), 'lunch')", (a1,))
    keepalive.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, source) "
                      "VALUES (%s, 'M', 'game', sqlite_today(), 'byga')", (a1,))
    keepalive.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, source) "
                      "VALUES (%s, 'M', 'game', sqlite_today(), 'manual')", (a1,))
    p2 = keepalive.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES ('B','b@x.com','t',TRUE) RETURNING id").fetchone()["id"]
    keepalive.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
                      "VALUES (%s, 'Bob', 13, 'M', 100, 5, 4)", (p2,))
    keepalive.commit()

    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {c.post('/api/admin/login', json={'password': PASSWORD}).json()['token']}"})
        yield c
    keepalive.close()


def test_overview_db_cards(client):
    body = client.get("/api/admin/analytics/overview").json()
    assert body["posthog_available"] is False
    assert body["cards"]["families_total"]["value"] == 2
    # 2 athletes, 1 connected → 50%
    assert body["cards"]["sync_adoption"]["percent"] == 50
    assert body["cards"]["sync_adoption"]["connected"] == 1
    assert body["app_health"]["event_sources"] == {"byga": 1, "manual": 1}


def test_overview_posthog_unavailable_is_graceful(client):
    body = client.get("/api/admin/analytics/overview").json()
    assert body["signups_over_time"]["posthog"]["available"] is False
    # DB signup series still present.
    assert isinstance(body["signups_over_time"]["points"], list)


def test_deleted_parents_excluded_from_metrics(client):
    from api.database import get_conn
    conn = get_conn()
    cols = [r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'parents'"
    ).fetchall()]
    if "account_status" not in cols:
        conn.execute("ALTER TABLE parents ADD COLUMN account_status TEXT")  # idempotent across shared-DB tests
    # Mark family B (Bob, no calendar) as hard-deleted.
    conn.execute("UPDATE parents SET account_status = 'hard_deleted' WHERE email = 'b@x.com'")
    conn.commit()
    conn.close()
    ov = client.get("/api/admin/analytics/overview").json()
    assert ov["cards"]["families_total"]["value"] == 1        # was 2
    # Only Ann remains; she is connected → 1/1 = 100%.
    assert ov["cards"]["sync_adoption"]["total"] == 1
    assert ov["cards"]["sync_adoption"]["percent"] == 100
    fn = client.get("/api/admin/analytics/funnel").json()
    assert {s["label"]: s["value"] for s in fn["steps"]}["Signed up"] == 1


def test_funnel_steps_are_db_derived(client):
    body = client.get("/api/admin/analytics/funnel").json()
    labels = [s["label"] for s in body["steps"]]
    assert labels == ["Signed up", "Created athlete", "Connected calendar", "Built meal plan"]
    values = {s["label"]: s["value"] for s in body["steps"]}
    assert values["Signed up"] == 2
    assert values["Created athlete"] == 2
    assert values["Connected calendar"] == 1
    assert values["Built meal plan"] == 1


def test_funnel_counts_uploaded_ics_as_connected(client):
    # Bob has no sync URL but an uploaded .ics event (uid set) → counts as
    # "Connected calendar", matching the Users-page badge.
    from api.database import get_conn
    conn = get_conn()
    aid = conn.execute("SELECT id FROM athletes WHERE first_name='Bob'").fetchone()["id"]
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, uid) "
                 "VALUES (%s, 'M', 'game', sqlite_today(), 'ics-uid-xyz')", (aid,))
    conn.commit()
    conn.close()
    steps = {s["label"]: s["value"] for s in client.get("/api/admin/analytics/funnel").json()["steps"]}
    assert steps["Connected calendar"] == 2   # Ann (auto-sync) + Bob (uploaded .ics)


def test_top_events_unavailable_without_creds(client):
    body = client.get("/api/admin/analytics/events").json()
    assert body["available"] is False
    assert body["reason"] == "PostHog not connected"


def test_retention_falls_back_to_db_wau(client):
    body = client.get("/api/admin/analytics/retention").json()
    assert body["source"] == "db_wau_fallback"
    assert isinstance(body["points"], list) and len(body["points"]) == 8


# ── PostHog success paths (HogQL endpoint mocked) ────────────────────────────
def test_posthog_top_events_success(client, monkeypatch):
    _configure_posthog(monkeypatch)
    monkeypatch.setattr(posthog_client, "_hogql",
                        lambda sql, name="admin": [["app_opened", 12], ["signup_completed", 4]])
    body = client.get("/api/admin/analytics/events").json()
    assert body["available"] is True
    assert body["data"]["rows"][0] == {"event": "app_opened", "count": 12}


def test_posthog_retention_success(client, monkeypatch):
    _configure_posthog(monkeypatch)
    monkeypatch.setattr(posthog_client, "_hogql",
                        lambda sql, name="admin": [["2026-06-23", 3], ["2026-06-30", 5]])
    body = client.get("/api/admin/analytics/retention").json()
    assert body["source"] == "posthog"
    assert body["points"][-1] == {"week_start": "2026-06-30", "active": 5}


def test_discover_lists_events(client, monkeypatch):
    _configure_posthog(monkeypatch)
    monkeypatch.setattr(posthog_client, "_hogql",
                        lambda sql, name="admin": [["signup_completed", 9], ["app_opened", 20]])
    body = client.get("/api/admin/analytics/discover").json()
    assert body["discovered"]["available"] is True
    assert body["discovered"]["data"]["events"][0] == {"event": "signup_completed", "count": 9}
    assert "signup_completed" in body["canonical_events"]


def test_posthog_query_error_is_graceful(client, monkeypatch):
    import requests
    _configure_posthog(monkeypatch)

    class _Resp:
        status_code = 403

    def boom(sql, name="admin"):
        e = requests.HTTPError("403 Forbidden")
        e.response = _Resp()
        raise e

    monkeypatch.setattr(posthog_client, "_hogql", boom)
    ev = client.get("/api/admin/analytics/events").json()
    assert ev["available"] is False
    assert "authentication failed" in ev["reason"]

    ov = client.get("/api/admin/analytics/overview").json()
    assert ov["posthog_available"] is False
    assert ov["posthog_status"]["configured"] is True  # creds set, but query failed

    rt = client.get("/api/admin/analytics/retention").json()
    assert rt["source"] == "db_wau_fallback"  # still falls back to real DB data
