"""Action Hub: attention feed from real signals, metrics, heatmap, auth."""

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


def _hub(c):
    return c.get("/api/admin/action-hub").json()


def test_requires_token():
    with TestClient(app) as anon:
        assert anon.get("/api/admin/action-hub").status_code == 401


def test_attention_feed_from_real_signals(ctx):
    c, ka = ctx
    # a red health check (error), a never-connected family (warning), a report (warning)
    # (health_checks rows are no longer pre-seeded by run_all() in Postgres mode —
    # insert the row this raw UPDATE targets before updating it)
    ka.execute("INSERT INTO health_checks (check_name, status) VALUES ('disk_space', 'unknown') "
               "ON CONFLICT (check_name) DO NOTHING")
    ka.execute("UPDATE health_checks SET status='red', detail='84% used' WHERE check_name='disk_space'")
    old = (datetime.utcnow() - timedelta(days=5)).isoformat()
    pid = ka.execute("INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed, created_at) "
                     "VALUES ('Old Fam', 'o@x.com', 't', TRUE, %s) RETURNING id", (old,)).fetchone()["id"]
    ka.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
               "VALUES (%s, 'Kid', 12, 'M', 90, 5, 2)", (pid,))
    ka.execute("INSERT INTO problem_reports (description) VALUES ('crash on save')")
    ka.commit()

    body = _hub(c)
    cats = [a["category"] for a in body["attention"]]
    assert "System health" in cats          # red check
    assert "Onboarding" in cats              # never-connected family
    assert "Problem reports" in cats         # this-week report
    # errors first
    assert body["attention"][0]["severity"] == "error"
    assert body["urgent_count"] == 1         # only the red health check is an error here
    # the family alert carries a navigate action with the parent id
    fam = next(a for a in body["attention"] if a["category"] == "Onboarding")
    assert fam["action"]["section"] == "users" and fam["action"]["id"] == pid


def test_nothing_wrong_is_empty_feed(ctx):
    c, _ = ctx
    body = _hub(c)
    assert body["attention"] == [] and body["urgent_count"] == 0


def test_metrics_and_heatmap_shape(ctx):
    c, ka = ctx
    pid = ka.execute("INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('A','a@x.com','t',TRUE) RETURNING id").fetchone()["id"]
    aid = ka.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
                     "VALUES (%s, 'K', 12, 'M', 90, 5, 2) RETURNING id", (pid,)).fetchone()["id"]
    ka.execute("INSERT INTO meal_logs (athlete_id, log_method) VALUES (%s, 'text')", (aid,))
    ka.commit()
    body = _hub(c)
    labels = [m["label"] for m in body["metrics"]]
    assert labels == ["Families", "New this month", "Active this week", "Calendar adoption"]
    assert body["heatmap"]["weeks"] == 8
    assert isinstance(body["heatmap"]["points"], list)
    assert body["heatmap"]["max"] >= 1       # one athlete active today
