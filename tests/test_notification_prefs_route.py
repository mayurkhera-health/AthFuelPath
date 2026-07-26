"""Integration tests for PATCH /api/notifications/prefs — the real backend
for the Training/Game Day + Quiet Hours switches on the mobile Settings
screens (previously AsyncStorage-only, never reaching the server)."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app


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
    email = f"prefs{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    })
    assert a.status_code == 201, a.text
    return a.json()["id"], parent_id


def test_upsert_creates_a_new_row(client):
    athlete_id, _ = _make_athlete(client)
    r = client.patch("/api/notifications/prefs", json={
        "profile_type": "athlete", "profile_id": athlete_id,
        "training_days": False, "game_days": True,
        "quiet_hours_enabled": True, "quiet_start": "21:00", "quiet_end": "06:30",
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


def test_upsert_updates_an_existing_row_in_place(client):
    athlete_id, _ = _make_athlete(client)
    client.patch("/api/notifications/prefs", json={
        "profile_type": "athlete", "profile_id": athlete_id, "training_days": True,
    })
    r = client.patch("/api/notifications/prefs", json={
        "profile_type": "athlete", "profile_id": athlete_id, "training_days": False,
    })
    assert r.status_code == 200, r.text

    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) c, MAX(training_days) t FROM notification_prefs WHERE profile_type='athlete' AND profile_id=?",
        (athlete_id,),
    ).fetchone()
    conn.close()
    assert row["c"] == 1  # upsert, not a duplicate row
    assert row["t"] == 0  # latest value wins


def test_athlete_and_parent_are_independent_profiles(client):
    athlete_id, parent_id = _make_athlete(client)
    client.patch("/api/notifications/prefs", json={
        "profile_type": "athlete", "profile_id": athlete_id, "quiet_hours_enabled": False,
    })
    r = client.patch("/api/notifications/prefs", json={
        "profile_type": "parent", "profile_id": parent_id, "quiet_hours_enabled": True,
    })
    assert r.status_code == 200, r.text

    from api.services.notification_service import get_notification_prefs
    conn = get_conn()
    athlete_prefs = get_notification_prefs("athlete", athlete_id, conn)
    parent_prefs = get_notification_prefs("parent", parent_id, conn)
    conn.close()
    assert athlete_prefs["quiet_hours_enabled"] is False
    assert parent_prefs["quiet_hours_enabled"] is True


def test_unknown_athlete_id_404s(client):
    r = client.patch("/api/notifications/prefs", json={
        "profile_type": "athlete", "profile_id": 999999,
    })
    assert r.status_code == 404


def test_invalid_profile_type_400s(client):
    r = client.patch("/api/notifications/prefs", json={
        "profile_type": "coach", "profile_id": 1,
    })
    assert r.status_code == 400
