"""Regression test: GET /api/athletes/{id}/weekly-report used to leak a raw
Python ValueError string (from date.fromisoformat() deep inside
build_weekly_report) as the `detail` of a 404 for a malformed week_start —
indistinguishable from a genuine "athlete not found" 404. Now validated at
the route boundary and returns a clean 400 instead.
"""
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


def _make_athlete(client):
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": "weeklyreport@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    }, headers=auth_headers("parent", parent_id=pid))
    return a.json()["id"]


def test_malformed_week_start_returns_clean_400_not_a_raw_exception(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.get(
        f"/api/reports/{aid}/weekly-report", params={"week_start": "not-a-date"}, headers=headers,
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "not-a-date" in detail
    assert "Invalid isoformat" not in detail  # the old raw Python exception text


def test_malformed_week_start_400s_before_touching_ownership_or_athlete_lookup(client):
    """A malformed week_start is a client error regardless of who's asking or
    which athlete — it must 400 even for an athlete_id that doesn't exist,
    not get confused with the (also-404) athlete-not-found case."""
    r = client.get(
        "/api/reports/999999/weekly-report", params={"week_start": "not-a-date"},
        headers=auth_headers("parent", parent_id=1),
    )
    assert r.status_code == 400, r.text


def test_nonexistent_athlete_with_a_valid_week_start_still_404s(client):
    r = client.get(
        "/api/reports/999999/weekly-report", params={"week_start": "2026-06-14"},
        headers=auth_headers("parent", parent_id=1),
    )
    assert r.status_code == 404, r.text
