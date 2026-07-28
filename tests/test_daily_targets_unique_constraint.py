"""Regression tests for H23: daily_targets had no UNIQUE(athlete_id,
target_date), so INSERT OR REPLACE silently inserted a new row instead of
replacing on every recalculation, and readers with no ORDER BY got an
unspecified row once duplicates existed."""
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def _make_athlete(client, n):
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"targets{n}@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    })
    return a.json()["id"]


def test_migration_adds_the_unique_index(client):
    conn = get_conn()
    found = any(
        {r["name"] for r in conn.execute(f"PRAGMA index_info('{idx['name']}')").fetchall()}
        == {"athlete_id", "target_date"}
        for idx in conn.execute("PRAGMA index_list(daily_targets)").fetchall()
    )
    conn.close()
    assert found


def test_migration_is_idempotent(client):
    run_all()  # must not raise, already applied once by the client fixture


def test_recalculating_targets_twice_updates_in_place_not_duplicates(client):
    """Core regression: the route's write used to insert a brand-new row on
    every call for the same athlete/day instead of replacing it."""
    aid = _make_athlete(client, 1)
    headers = auth_headers("athlete", athlete_id=aid)
    r1 = client.get(f"/api/nutrition/targets/{aid}?date=2026-08-01&event_type=game", headers=headers)
    assert r1.status_code == 200, r1.text
    r2 = client.get(f"/api/nutrition/targets/{aid}?date=2026-08-01&event_type=practice", headers=headers)
    assert r2.status_code == 200, r2.text

    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) c FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
        (aid, "2026-08-01"),
    ).fetchone()
    conn.close()
    assert row["c"] == 1  # one row, not two

    # And the row reflects the LATEST call, not the first.
    assert r2.json()["event_type"] == "practice"


def test_migration_dedupes_pre_existing_duplicate_rows(tmp_path):
    """Simulate the pre-fix bug state (two rows for the same athlete/day, as
    the old INSERT OR REPLACE would have left behind) against a fresh, never-
    migrated DB file, then confirm the migration collapses them to the most
    recently inserted row. Uses a real temp DB file (not the shared in-memory
    test DB) so daily_targets starts out truly unmigrated."""
    db_file = str(tmp_path / "dedupe_test.db")
    old_db_path = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = db_file
    try:
        init_db()  # original schema only — no UNIQUE(athlete_id, target_date) yet
        conn = get_conn()
        conn.execute("PRAGMA foreign_keys=OFF")  # no real athlete row needed for this schema-only test
        conn.execute(
            "INSERT INTO daily_targets (athlete_id, target_date, event_type, total_calories) VALUES (1, '2026-08-02', 'rest', 1000)"
        )
        conn.execute(
            "INSERT INTO daily_targets (athlete_id, target_date, event_type, total_calories) VALUES (1, '2026-08-02', 'game', 2500)"
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) c FROM daily_targets").fetchone()["c"]
        conn.close()
        assert before == 2  # duplicate state successfully simulated

        run_all()  # includes _add_intensity_to_daily_targets, a real prerequisite in production order

        conn = get_conn()
        rows = conn.execute("SELECT event_type, total_calories FROM daily_targets").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "game"  # the higher-id (later-inserted) row survives
    finally:
        if old_db_path is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = old_db_path
