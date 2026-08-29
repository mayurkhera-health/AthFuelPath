"""Manual event duration_hours bounds (Security Item 6, N3) —
POST /api/events/ and PUT /api/events/{id}.

EventCreate/EventUpdate.duration_hours was a bare Optional[float] with no
bound, unlike the ICS-import path (api/services/ics_sync.py) which already
clamps synced-event durations to [0.5, 8.0]. An unbounded or negative
manually-entered duration feeds directly and linearly into the hydration
estimate (api/services/weather.py, api/services/nutrition_calc.calc_hydration)
with no ceiling — producing an absurd or negative fluid recommendation, a
safety-relevant number for a youth sports app.

Fixed by applying the SAME [0.5, 8.0] bound to the client-facing manual
event routes — aligning, not changing, the existing sanity range. Invalid
values are rejected (422), never silently clamped. None remains valid
(duration is optional — e.g. a rest day has none).
"""
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

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
    keepalive.execute("DELETE FROM events")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def make_parent(email):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), True),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in)
               VALUES (%s, %s, 15, 'girl', 115, 5, 6) RETURNING id""",
            (parent_id, first_name),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def _event_count(athlete_id) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM events WHERE athlete_id = %s", (athlete_id,)
        ).fetchone()["c"]
    finally:
        conn.close()


def _event_body(athlete_id, **overrides):
    body = {
        "athlete_id": athlete_id, "event_name": "Practice", "event_type": "practice",
        "event_date": "2026-08-10",
    }
    body.update(overrides)
    return body


# ─── POST /api/events/ (EventCreate) ────────────────────────────────────────

def test_create_event_accepts_no_duration(client):
    parent_id = make_parent("evt-none@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert r.json()["duration_hours"] is None


@pytest.mark.parametrize("value", [0.5, 8.0])
def test_create_event_accepts_boundary_duration(client, value):
    parent_id = make_parent(f"evt-boundary-{value}@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id, duration_hours=value, event_date=f"2026-08-{11 if value == 0.5 else 12}"),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert r.json()["duration_hours"] == value


@pytest.mark.parametrize("value", [-1, 0])
def test_create_event_rejects_negative_or_zero_duration(client, value):
    parent_id = make_parent(f"evt-reject-low-{value}@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id, duration_hours=value),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 422, r.text
    assert _event_count(athlete_id) == 0


def test_create_event_rejects_duration_over_max(client):
    parent_id = make_parent("evt-reject-high@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id, duration_hours=100),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 422, r.text
    assert _event_count(athlete_id) == 0


@pytest.mark.parametrize("value", [1.0, 1.5, 2.0])
def test_create_event_accepts_normal_durations(client, value):
    parent_id = make_parent(f"evt-normal-{value}@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id, duration_hours=value, event_date="2026-08-15"),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert r.json()["duration_hours"] == value


# ─── PUT /api/events/{id} (EventUpdate) ─────────────────────────────────────

def _create_event(client, athlete_id, **overrides):
    r = client.post(
        "/api/events/", json=_event_body(athlete_id, **overrides),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_update_event_accepts_none_duration(client):
    parent_id = make_parent("put-evt-none@example.com")
    athlete_id = make_athlete(parent_id)
    event_id = _create_event(client, athlete_id, duration_hours=1.5)
    r = client.put(
        f"/api/events/{event_id}", json={},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("value", [0.5, 8.0])
def test_update_event_accepts_boundary_duration(client, value):
    parent_id = make_parent(f"put-evt-boundary-{value}@example.com")
    athlete_id = make_athlete(parent_id)
    event_id = _create_event(client, athlete_id, duration_hours=1.5)
    r = client.put(
        f"/api/events/{event_id}", json={"duration_hours": value},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200, r.text
    assert r.json()["duration_hours"] == value


@pytest.mark.parametrize("value", [-1, 0])
def test_update_event_rejects_negative_or_zero_duration(client, value):
    parent_id = make_parent(f"put-evt-reject-low-{value}@example.com")
    athlete_id = make_athlete(parent_id)
    event_id = _create_event(client, athlete_id, duration_hours=1.5)
    r = client.put(
        f"/api/events/{event_id}", json={"duration_hours": value},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 422, r.text


def test_update_event_rejects_duration_over_max(client):
    parent_id = make_parent("put-evt-reject-high@example.com")
    athlete_id = make_athlete(parent_id)
    event_id = _create_event(client, athlete_id, duration_hours=1.5)
    r = client.put(
        f"/api/events/{event_id}", json={"duration_hours": 100},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("value", [1.0, 1.5, 2.0])
def test_update_event_accepts_normal_durations(client, value):
    parent_id = make_parent(f"put-evt-normal-{value}@example.com")
    athlete_id = make_athlete(parent_id)
    event_id = _create_event(client, athlete_id, duration_hours=1.5)
    r = client.put(
        f"/api/events/{event_id}", json={"duration_hours": value},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200, r.text
    assert r.json()["duration_hours"] == value
