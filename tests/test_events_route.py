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
    }, headers=auth_headers("parent", parent_id=parent_id))
    assert a.status_code == 201, a.text
    return a.json()["id"]


def test_explicit_intensity_is_stored(client):
    aid = _make_athlete(client, "Recreational")
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": "2026-06-21", "intensity": "High",
    }, headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 201, r.text
    assert r.json()["intensity"] == "high"


def test_omitted_intensity_is_derived(client):
    aid = _make_athlete(client, "Elite Club")
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": "2026-06-21",
    }, headers=auth_headers("athlete", athlete_id=aid))
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
    }, headers=auth_headers("athlete", athlete_id=aid))
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
    }, headers=auth_headers("athlete", athlete_id=aid))
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
    }, headers=auth_headers("athlete", athlete_id=aid))
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
    }, headers=auth_headers("athlete", athlete_id=aid))
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    assert client.delete(
        f"/api/events/{eid}", headers=auth_headers("athlete", athlete_id=aid)
    ).status_code == 200


def test_targets_reflect_event_intensity(client):
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)
    # Recreational would derive "low" for a game; send explicit "high" to prove threading
    client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": "2026-07-01", "intensity": "high",
    }, headers=headers)
    r = client.get(f"/api/nutrition/targets/{aid}?date=2026-07-01", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intensity"] == "high"
    # A date with no event -> rest, no intensity -> full band (intensity None)
    r2 = client.get(f"/api/nutrition/targets/{aid}?date=2026-07-02", headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("intensity") is None


# ─── Backend-side duplicate prevention (event_matching.py safety net) ──────────
# The standalone mobile ICS import (utils/icsImport.ts) posts here with no uid
# at all when a VEVENT lacks one, and a brand-new uid every time when the
# source calendar rotates uids on export — client-side pre-checks can't tell
# either case is a repeat. These prove the backend catches both regardless.

def test_repeated_manual_import_no_uid_does_not_duplicate(client):
    """Same event re-submitted with no uid at all (calendar VEVENT had none) —
    must not create a second row."""
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)
    payload = {
        "athlete_id": aid, "event_name": "Team Practice", "event_type": "practice",
        "event_date": "2026-08-25", "start_time": "19:30", "duration_hours": 1.5,
    }
    first = client.post("/api/events/", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    second = client.post("/api/events/", json=payload, headers=headers)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"], "Second POST must return the same row, not insert"

    listing = client.get(f"/api/events/athlete/{aid}", headers=headers)
    matching = [e for e in listing.json() if e["event_name"] == "Team Practice"]
    assert len(matching) == 1, f"Expected 1 event, found {len(matching)}"


def test_repeated_manual_import_rotated_uid_does_not_duplicate(client):
    """Same event re-submitted with a DIFFERENT uid each time (provider rotates
    uids on every export) — must still collapse to one row."""
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)

    for uid in ("rotated-uid-1", "rotated-uid-2", "rotated-uid-3"):
        r = client.post("/api/events/", json={
            "athlete_id": aid, "event_name": "Team Practice", "event_type": "practice",
            "event_date": "2026-08-25", "start_time": "19:30", "duration_hours": 1.5,
            "uid": uid,
        }, headers=headers)
        assert r.status_code == 201, r.text

    listing = client.get(f"/api/events/athlete/{aid}", headers=headers)
    matching = [e for e in listing.json() if e["event_name"] == "Team Practice"]
    assert len(matching) == 1, f"Expected 1 event after 3 rotated-uid imports, found {len(matching)}"


def test_manual_create_tolerates_facility_suffix_drift(client):
    """A re-import where the provider appended a facility/court suffix to the
    name (the confirmed production bug: '...Complex' -> '...Complex #10')
    must still be recognized as the same event."""
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)
    first = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Practice: Twin Creeks Sports Complex",
        "event_type": "practice", "event_date": "2026-08-25", "start_time": "19:30",
        "duration_hours": 1.5,
    }, headers=headers)
    assert first.status_code == 201, first.text

    second = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Practice: Twin Creeks Sports Complex #10",
        "event_type": "practice", "event_date": "2026-08-25", "start_time": "19:30",
        "duration_hours": 1.5,
    }, headers=headers)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]


def test_manual_create_preserves_genuinely_different_same_time_event(client):
    """Two REAL different events for the same athlete at the same date/time
    (different sport/name) must both survive — never merged."""
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)
    a = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Soccer vs Team Alpha", "event_type": "game",
        "event_date": "2026-08-25", "start_time": "19:30", "duration_hours": 1.5,
    }, headers=headers)
    b = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Soccer vs Team Beta", "event_type": "game",
        "event_date": "2026-08-25", "start_time": "19:30", "duration_hours": 1.5,
    }, headers=headers)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] != b.json()["id"], "Different opponents must not be merged"

    listing = client.get(f"/api/events/athlete/{aid}", headers=headers)
    assert len(listing.json()) == 2


def test_repeated_manual_import_5x_stable_count(client):
    """Re-submitting the same event 5 times (rotating uid each time, matching
    real repeated-sync behavior) must never grow past 1 row."""
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)
    ids = set()
    for i in range(5):
        r = client.post("/api/events/", json={
            "athlete_id": aid, "event_name": "Weekly Conditioning", "event_type": "training",
            "event_date": "2026-09-01", "start_time": "17:00", "duration_hours": 1.0,
            "uid": f"cycle-{i}",
        }, headers=headers)
        assert r.status_code == 201, r.text
        ids.add(r.json()["id"])

    assert len(ids) == 1, f"Expected all 5 imports to collapse to 1 row, got ids={ids}"
    listing = client.get(f"/api/events/athlete/{aid}", headers=headers)
    matching = [e for e in listing.json() if e["event_name"] == "Weekly Conditioning"]
    assert len(matching) == 1


def test_ambiguous_existing_duplicates_reject_rather_than_multiply(client):
    """Issue 2: two pre-existing equivalent manual rows (a stale double-import,
    already ambiguous before this request) + one more equivalent submission
    must NOT create a 3rd row, and must NOT arbitrarily pick one of the two
    existing rows to return either — a 409 conflict is the correct outcome,
    same pattern this route already uses for other "can't safely proceed"
    cases (see test_cannot_edit_synced_event)."""
    aid = _make_athlete(client, "Recreational")
    headers = auth_headers("athlete", athlete_id=aid)
    conn = get_conn()
    for suffix in ("1", "2"):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(%s,'Team Practice','practice','2026-09-05','18:00',1.5,%s,'manual')",
            (aid, f"stale-{suffix}"),
        )
    conn.commit()
    conn.close()

    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Team Practice", "event_type": "practice",
        "event_date": "2026-09-05", "start_time": "18:00", "duration_hours": 1.5,
    }, headers=headers)
    assert r.status_code == 409, r.text

    listing = client.get(f"/api/events/athlete/{aid}", headers=headers)
    matching = [e for e in listing.json() if e["event_name"] == "Team Practice"]
    assert len(matching) == 2, f"Expected the existing 2 rows unchanged, got {len(matching)}"
