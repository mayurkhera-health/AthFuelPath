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


def _make_parent_and_athlete(client):
    _counter["n"] += 1
    email = f"activity{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 14, "gender": "boy",
        "weight_lbs": 120, "height_ft": 5, "height_in": 4,
    })
    return a.json()["id"]


def test_create_event_stores_activity_type(client):
    aid = _make_parent_and_athlete(client)
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Speed work", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
        "activity_type": "speed_sprint",
    })
    assert r.status_code == 201, r.text
    assert r.json()["activity_type"] == "speed_sprint"


def test_create_event_activity_type_defaults_null(client):
    aid = _make_parent_and_athlete(client)
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Mystery", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
    })
    assert r.status_code == 201
    assert r.json()["activity_type"] is None


def test_patch_tags_activity_type(client):
    aid = _make_parent_and_athlete(client)
    ev = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Mystery", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
    }).json()
    r = client.patch(
        f"/api/events/{ev['id']}/activity-type", json={"activity_type": "game"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    assert r.json()["activity_type"] == "game"


def test_patch_rejects_invalid_activity_type(client):
    aid = _make_parent_and_athlete(client)
    ev = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "X", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
    }).json()
    r = client.patch(
        f"/api/events/{ev['id']}/activity-type", json={"activity_type": "bogus"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 422


def test_patch_unknown_event_returns_404(client):
    aid = _make_parent_and_athlete(client)
    r = client.patch(
        "/api/events/99999/activity-type", json={"activity_type": "game"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 404
