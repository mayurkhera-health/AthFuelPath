"""Integration tests for intensity on the events route."""

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
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}

def _make_athlete(client, level):
    _counter["n"] += 1
    email = f"intensity{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6, "competition_level": level,
    })
    assert a.status_code == 201, a.text
    return a.json()["id"]


def test_explicit_intensity_is_stored(client):
    aid = _make_athlete(client, "Recreational")
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": "2026-06-21", "intensity": "High",
    })
    assert r.status_code == 201, r.text
    assert r.json()["intensity"] == "high"


def test_omitted_intensity_is_derived(client):
    aid = _make_athlete(client, "Elite Club")
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": "2026-06-21",
    })
    assert r.status_code == 201, r.text
    assert r.json()["intensity"] == "high"  # Elite Club game


def test_venue_location_round_trips(client):
    aid = _make_athlete(client, "Recreational")
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Practice", "event_type": "practice",
        "event_date": "2026-06-23",
        "venue_name": "Mustang Soccer Complex",
        "address": "1 Camino Ramon, San Ramon, CA",
        "latitude": 37.78, "longitude": -121.98,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["venue_name"] == "Mustang Soccer Complex"
    assert body["address"] == "1 Camino Ramon, San Ramon, CA"
    assert body["latitude"] == 37.78 and body["longitude"] == -121.98

    # Update only the coordinates; venue_name must be preserved (partial update).
    u = client.put(
        f"/api/events/{body['id']}", json={"latitude": 38.0, "longitude": -122.0},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert u.status_code == 200, u.text
    assert u.json()["latitude"] == 38.0
    assert u.json()["venue_name"] == "Mustang Soccer Complex"


def test_rest_event_derives_low_for_elite(client):
    aid = _make_athlete(client, "Elite Club")
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Yoga", "event_type": "rest",
        "event_date": "2026-06-22",
    })
    assert r.status_code == 201, r.text
    assert r.json()["intensity"] == "low"


def _insert_synced_event(aid, source, uid):
    """Insert a synced event straight into the (shared in-memory) DB — the API has
    no route that sets a non-manual source, which is the whole point of read-only."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, "
        "duration_hours, uid, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (aid, "Synced Game", "game", "2026-07-15", "18:30", 1.5, uid, source),
    )
    conn.commit()
    return conn.execute("SELECT id FROM events WHERE uid = %s", (uid,)).fetchone()["id"]


def test_cannot_edit_synced_event(client):
    aid = _make_athlete(client, "Recreational")
    eid = _insert_synced_event(aid, "byga", "byga-123")
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.put(f"/api/events/{eid}", json={"event_name": "Hacked"}, headers=headers)
    assert r.status_code == 409, r.text
    assert "Cannot edit" in r.json()["detail"]
    # Unchanged in the DB.
    assert client.get(f"/api/events/{eid}", headers=headers).json()["event_name"] == "Synced Game"


def test_cannot_delete_synced_event(client):
    aid = _make_athlete(client, "Recreational")
    eid = _insert_synced_event(aid, "playmetrics", "pm-456")
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.delete(f"/api/events/{eid}", headers=headers)
    assert r.status_code == 409, r.text
    assert "Cannot delete" in r.json()["detail"]
    assert client.get(f"/api/events/{eid}", headers=headers).status_code == 200  # still there


def test_can_edit_manual_event(client):
    aid = _make_athlete(client, "Recreational")
    created = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Private Coaching", "event_type": "training",
        "event_date": "2026-07-15", "start_time": "19:00",
    })
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    r = client.put(
        f"/api/events/{eid}", json={"event_name": "Private Coaching (moved)"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    assert r.json()["event_name"] == "Private Coaching (moved)"


def test_can_delete_manual_event(client):
    aid = _make_athlete(client, "Recreational")
    created = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "One-time Training", "event_type": "training",
        "event_date": "2026-07-14", "start_time": "17:00",
    })
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    assert client.delete(
        f"/api/events/{eid}", headers=auth_headers("athlete", athlete_id=aid)
    ).status_code == 200


def test_targets_reflect_event_intensity(client):
    aid = _make_athlete(client, "Recreational")
    # Recreational would derive "low" for a game; send explicit "high" to prove threading
    client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": "2026-07-01", "intensity": "high",
    })
    r = client.get(f"/api/nutrition/targets/{aid}?date=2026-07-01")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intensity"] == "high"
    # A date with no event -> rest, no intensity -> full band (intensity None)
    r2 = client.get(f"/api/nutrition/targets/{aid}?date=2026-07-02")
    assert r2.status_code == 200, r2.text
    assert r2.json().get("intensity") is None
