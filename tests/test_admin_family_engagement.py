"""Family detail Tier-2 engagement block: meal/water logs, streak, pantry usage,
blueprint, athlete login, push reachability."""

import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth
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


def _iso(days_ago=0):
    return (datetime.utcnow() - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def ctx(monkeypatch):
    ka = get_conn()
    init_db()
    run_all()
    _wipe(ka)
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key")
    admin_auth._failed_logins.clear()

    pid = ka.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed, created_at) "
        "VALUES ('Purvi Shah', 'p@x.com', %s, TRUE, %s) RETURNING id", (_iso(2), _iso(2))).fetchone()["id"]
    aid = ka.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, "
        "blueprint_json) VALUES (%s, 'Mehr', 17, 'female', 105, 5, 2, '{\"x\":1}') RETURNING id", (pid,)).fetchone()["id"]

    ka.execute("INSERT INTO meal_logs (athlete_id, logged_at, log_method, description) VALUES (%s, %s, 'text', 'oats')",
               (aid, _iso(1)))
    ka.execute("INSERT INTO meal_logs (athlete_id, logged_at, log_method, description) VALUES (%s, %s, 'text', 'rice')",
               (aid, _iso(0)))
    ka.execute("INSERT INTO water_logs (athlete_id, log_date, cups) VALUES (%s, sqlite_today(), 5)", (aid,))
    ka.execute("INSERT INTO pantry_list_items (athlete_id, week_start, food_id, name, checked) "
               "VALUES (%s, '2026-06-29', 'banana_ripe', 'Banana', 1)", (aid,))
    ka.execute("INSERT INTO pantry_list_items (athlete_id, week_start, food_id, name, checked) "
               "VALUES (%s, '2026-06-29', 'oats_dry', 'Oats', 0)", (aid,))
    ka.execute("INSERT INTO athlete_logins (email, athlete_id, created_at) VALUES ('mehr@x.com', %s, %s)",
               (aid, _iso(1)))
    ka.execute("INSERT INTO expo_push_tokens (athlete_id, parent_id, token, platform) "
               "VALUES (NULL, %s, 'ExponentPushToken[p]', 'ios')", (pid,))
    ka.execute("INSERT INTO expo_push_tokens (athlete_id, parent_id, token, platform) "
               "VALUES (%s, NULL, 'ExponentPushToken[a]', 'ios')", (aid,))
    ka.execute("INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token, sent_at) "
               "VALUES (%s, 'pre_game', sqlite_today(), 'parent', 'ExponentPushToken[p]', %s)", (aid, _iso(0)))
    ka.commit()

    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {c.post('/api/admin/login', json={'password': PASSWORD}).json()['token']}"})
        yield c, pid, aid
    ka.close()


def test_family_detail_includes_engagement_block(ctx):
    c, pid, aid = ctx
    d = c.get(f"/api/admin/users/{pid}").json()
    a = next(x for x in d["athletes"] if x["id"] == aid)
    eng = a["engagement"]

    assert eng["meal_logs"]["total"] == 2
    assert eng["meal_logs"]["last_at"] is not None
    assert eng["water_logs"]["total"] == 1
    assert eng["streak"] >= 0
    assert eng["pantry"]["latest_week_start"] == "2026-06-29"
    assert eng["pantry"]["item_count"] == 2
    assert eng["pantry"]["checked_count"] == 1
    assert eng["blueprint_generated"] is True
    assert eng["athlete_login"]["exists"] is True
    assert eng["athlete_login"]["email"] == "mehr@x.com"
    assert eng["push"]["tokens"] == 1                 # athlete's own token
    assert eng["push"]["last_push_at"] is not None


def test_family_detail_parent_push_tokens(ctx):
    c, pid, aid = ctx
    d = c.get(f"/api/admin/users/{pid}").json()
    assert d["parent"]["push_tokens"] == 1


def test_family_detail_parent_push_devices_detail(ctx):
    c, pid, aid = ctx
    d = c.get(f"/api/admin/users/{pid}").json()
    devices = d["parent"]["push_devices"]
    assert len(devices) == 1
    assert devices[0]["platform"] == "ios"
    assert "created_at" in devices[0]
    assert "token" not in devices[0]   # never expose the raw push token


def test_engagement_empty_for_fresh_athlete(ctx):
    c, pid, _ = ctx
    ka = get_conn()
    aid2 = ka.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, 'Zed', 12, 'male', 90, 4, 8) RETURNING id", (pid,)).fetchone()["id"]
    ka.commit(); ka.close()
    d = c.get(f"/api/admin/users/{pid}").json()
    a = next(x for x in d["athletes"] if x["id"] == aid2)
    eng = a["engagement"]
    assert eng["meal_logs"]["total"] == 0
    assert eng["pantry"]["latest_week_start"] is None
    assert eng["blueprint_generated"] is False
    assert eng["athlete_login"]["exists"] is False
    assert eng["push"]["tokens"] == 0
