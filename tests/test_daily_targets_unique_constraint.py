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
        cols == {"athlete_id", "target_date"}
        for cols in (
            {
                r["column_name"]
                for r in conn.execute(
                    "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
                    "WHERE tc.table_name = 'daily_targets' AND tc.constraint_type = 'UNIQUE' "
                    "AND tc.constraint_name = %s",
                    (row["constraint_name"],),
                ).fetchall()
            }
            for row in conn.execute(
                "SELECT DISTINCT constraint_name FROM information_schema.table_constraints "
                "WHERE table_name = 'daily_targets' AND constraint_type = 'UNIQUE'"
            ).fetchall()
        )
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
        "SELECT COUNT(*) c FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
        (aid, "2026-08-01"),
    ).fetchone()
    conn.close()
    assert row["c"] == 1  # one row, not two

    # And the row reflects the LATEST call, not the first.
    assert r2.json()["event_type"] == "practice"


# test_migration_dedupes_pre_existing_duplicate_rows was intentionally removed
# during the Postgres migration (migration/postgres-cloud-run): it simulated a
# "never-migrated" DB file missing the UNIQUE(athlete_id, target_date)
# constraint, then replayed the historical SQLite dedup migration to collapse
# duplicates. Under Postgres that premise is structurally impossible — the
# constraint ships in db/postgres/001_baseline.sql, so every database has it
# from creation; there is no unmigrated state and nothing to dedupe. The
# migration brief explicitly rules out replaying db_migrations.py against
# Postgres or reproducing the historical SQLite migration sequence, so this
# scenario has no Postgres equivalent to port to. test_migration_adds_the_
# unique_index above already covers "the constraint exists".
