"""Route-level BOLA regression — api/routes/calendar.py
(POST/GET/DELETE /api/athletes/{athlete_id}/calendar/sync-url,
GET /api/athletes/{athlete_id}/calendar/sync-status).

Every other athlete-scoped resource has a dedicated *_bola.py test file
(test_meals_bola.py, test_athletes_parents_bola.py, ...); calendar sync had
none despite wiring assert_owns_athlete like everything else. This proves
the route-level ownership check end-to-end (not just the service-layer SSRF
guard, which is already covered by test_ics_sync_ssrf.py /
test_fetch_ics_route_ssrf.py): (A) unauthenticated -> 401, (B) an unrelated
athlete/parent token -> 403 with the stored config left untouched, (C) the
real owner (athlete or parent) still succeeds.

The outbound calendar fetch itself is mocked here (fetch_ics_text /
sync_platform) — SSRF behavior is out of scope for this file.
"""
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services import ics_sync
from tests.conftest import auth_headers


@pytest.fixture
def client(monkeypatch):
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM events")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()

    monkeypatch.setattr(ics_sync, "fetch_ics_text", lambda url: "BEGIN:VCALENDAR\nEND:VCALENDAR")
    monkeypatch.setattr(
        ics_sync, "sync_platform",
        lambda conn, athlete_id, platform, ics_url, competition_level: {
            "inserted": 0, "updated": 0, "deleted": 0, "feed": 0, "error": None,
            "inserted_events": [], "source_upgraded": 0, "ambiguous_skipped": 0,
        },
    )

    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client, email_prefix):
    _counter["n"] += 1
    email = f"{email_prefix}{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    }, headers=auth_headers("parent", parent_id=parent_id))
    assert a.status_code == 201, a.text
    return a.json()["id"], parent_id


def _victim_and_attacker(client, prefix):
    victim_id, victim_parent = _make_athlete(client, f"{prefix}-victim")
    attacker_id, attacker_parent = _make_athlete(client, f"{prefix}-attacker")
    return victim_id, victim_parent, attacker_id, attacker_parent


def _stored_url(athlete_id):
    conn = get_conn()
    row = conn.execute("SELECT byga_ics_url FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
    conn.close()
    return row["byga_ics_url"]


_SYNC_BODY = {"platform": "byga", "ics_url": "https://calendar.byga.example.com/feed.ics"}


# ─── POST /{athlete_id}/calendar/sync-url ──────────────────────────────────

def test_save_sync_url_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker(client, "post1")
    r = client.post(f"/api/athletes/{victim_id}/calendar/sync-url", json=_SYNC_BODY)
    assert r.status_code == 401
    assert _stored_url(victim_id) is None


def test_save_sync_url_rejects_unrelated_athlete_token(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker(client, "post2")
    r = client.post(
        f"/api/athletes/{victim_id}/calendar/sync-url", json=_SYNC_BODY,
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert _stored_url(victim_id) is None


def test_save_sync_url_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker(client, "post3")
    r = client.post(
        f"/api/athletes/{victim_id}/calendar/sync-url", json=_SYNC_BODY,
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert _stored_url(victim_id) is None


def test_save_sync_url_allows_owning_athlete(client):
    victim_id, _, _, _ = _victim_and_attacker(client, "post4")
    r = client.post(
        f"/api/athletes/{victim_id}/calendar/sync-url", json=_SYNC_BODY,
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text
    assert _stored_url(victim_id) == _SYNC_BODY["ics_url"]


def test_save_sync_url_allows_owning_parent(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker(client, "post5")
    r = client.post(
        f"/api/athletes/{victim_id}/calendar/sync-url", json=_SYNC_BODY,
        headers=auth_headers("parent", parent_id=victim_parent),
    )
    assert r.status_code == 200, r.text
    assert _stored_url(victim_id) == _SYNC_BODY["ics_url"]


# ─── GET /{athlete_id}/calendar/sync-status ─────────────────────────────────

def test_sync_status_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker(client, "status1")
    r = client.get(f"/api/athletes/{victim_id}/calendar/sync-status")
    assert r.status_code == 401


def test_sync_status_rejects_unrelated_athlete_token(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker(client, "status2")
    r = client.get(
        f"/api/athletes/{victim_id}/calendar/sync-status",
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403


def test_sync_status_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker(client, "status3")
    r = client.get(
        f"/api/athletes/{victim_id}/calendar/sync-status",
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403


def test_sync_status_allows_owning_athlete(client):
    victim_id, _, _, _ = _victim_and_attacker(client, "status4")
    r = client.get(
        f"/api/athletes/{victim_id}/calendar/sync-status",
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text


def test_sync_status_allows_owning_parent(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker(client, "status5")
    r = client.get(
        f"/api/athletes/{victim_id}/calendar/sync-status",
        headers=auth_headers("parent", parent_id=victim_parent),
    )
    assert r.status_code == 200, r.text


# ─── DELETE /{athlete_id}/calendar/sync-url ────────────────────────────────

def _connect(client, athlete_id, headers):
    r = client.post(f"/api/athletes/{athlete_id}/calendar/sync-url", json=_SYNC_BODY, headers=headers)
    assert r.status_code == 200, r.text


def test_remove_sync_url_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker(client, "del1")
    _connect(client, victim_id, auth_headers("athlete", athlete_id=victim_id))
    r = client.delete(f"/api/athletes/{victim_id}/calendar/sync-url", params={"platform": "byga"})
    assert r.status_code == 401
    assert _stored_url(victim_id) == _SYNC_BODY["ics_url"]


def test_remove_sync_url_rejects_unrelated_athlete_token(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker(client, "del2")
    _connect(client, victim_id, auth_headers("athlete", athlete_id=victim_id))
    r = client.delete(
        f"/api/athletes/{victim_id}/calendar/sync-url", params={"platform": "byga"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert _stored_url(victim_id) == _SYNC_BODY["ics_url"]


def test_remove_sync_url_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker(client, "del3")
    _connect(client, victim_id, auth_headers("athlete", athlete_id=victim_id))
    r = client.delete(
        f"/api/athletes/{victim_id}/calendar/sync-url", params={"platform": "byga"},
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert _stored_url(victim_id) == _SYNC_BODY["ics_url"]


def test_remove_sync_url_allows_owning_athlete(client):
    victim_id, _, _, _ = _victim_and_attacker(client, "del4")
    _connect(client, victim_id, auth_headers("athlete", athlete_id=victim_id))
    r = client.delete(
        f"/api/athletes/{victim_id}/calendar/sync-url", params={"platform": "byga"},
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text
    assert _stored_url(victim_id) is None


def test_remove_sync_url_allows_owning_parent(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker(client, "del5")
    _connect(client, victim_id, auth_headers("athlete", athlete_id=victim_id))
    r = client.delete(
        f"/api/athletes/{victim_id}/calendar/sync-url", params={"platform": "byga"},
        headers=auth_headers("parent", parent_id=victim_parent),
    )
    assert r.status_code == 200, r.text
    assert _stored_url(victim_id) is None
