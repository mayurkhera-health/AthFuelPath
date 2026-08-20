"""Regression tests for api/routes/water.py — no test coverage existed for
this route before. Covers: cups upper bound, date format validation, the
GET/POST existence-check asymmetry, and the stale unclamped-value response.
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


_counter = {"n": 0}


def _make_athlete(client):
    _counter["n"] += 1
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"water{_counter['n']}@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    }, headers=auth_headers("parent", parent_id=pid))
    return a.json()["id"]


def test_valid_log_persists_and_returns_the_same_value(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post("/api/water-log/", json={"athlete_id": aid, "cups": 6, "date": "2026-06-14"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["cups"] == 6


def test_cups_above_upper_bound_is_rejected(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post("/api/water-log/", json={"athlete_id": aid, "cups": 999, "date": "2026-06-14"}, headers=headers)
    assert r.status_code == 422, r.text


def test_negative_cups_is_rejected(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post("/api/water-log/", json={"athlete_id": aid, "cups": -1, "date": "2026-06-14"}, headers=headers)
    assert r.status_code == 422, r.text


def test_malformed_date_is_rejected_instead_of_silently_vanishing(client):
    """Regression: a malformed date used to be accepted and stored — the
    entry then never matched get_water_today()'s real-ISO-date query, so it
    silently vanished from every subsequent GET with no error anywhere."""
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post("/api/water-log/", json={"athlete_id": aid, "cups": 4, "date": "06/14/2026"}, headers=headers)
    assert r.status_code == 422, r.text


def test_get_today_requires_athlete_existence_like_post_does(client):
    """Regression: GET .../today had no existence check at all, unlike POST's
    explicit 404 — a nonexistent athlete_id silently returned {"cups": 0}
    instead of erroring, hiding the difference from a genuine zero-cups day."""
    r = client.get(
        "/api/water-log/999999/today",
        headers=auth_headers("parent", parent_id=1),
    )
    assert r.status_code == 404, r.text


def test_get_today_reflects_logged_value(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    from datetime import date
    today = str(date.today())
    client.post("/api/water-log/", json={"athlete_id": aid, "cups": 3, "date": today}, headers=headers)
    r = client.get(f"/api/water-log/{aid}/today", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["cups"] == 3


def test_get_today_accepts_a_client_supplied_local_date(client):
    """Timezone Invariant: 'today' must be resolvable to the CLIENT's local
    date, not the server's UTC date. A client past its local midnight but
    before UTC midnight (or vice versa) needs to ask for a specific date."""
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    client.post("/api/water-log/", json={"athlete_id": aid, "cups": 5, "date": "2026-06-14"}, headers=headers)
    r = client.get(f"/api/water-log/{aid}/today?date=2026-06-14", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"athlete_id": aid, "date": "2026-06-14", "cups": 5}


def test_get_today_with_no_date_param_still_defaults_to_server_today(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    from datetime import date
    today = str(date.today())
    client.post("/api/water-log/", json={"athlete_id": aid, "cups": 2, "date": today}, headers=headers)
    r = client.get(f"/api/water-log/{aid}/today", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"athlete_id": aid, "date": today, "cups": 2}


def test_get_today_rejects_malformed_date_param(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.get(f"/api/water-log/{aid}/today?date=06/14/2026", headers=headers)
    assert r.status_code == 400, r.text
