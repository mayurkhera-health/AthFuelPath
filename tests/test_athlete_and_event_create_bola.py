"""BOLA/auth regression tests — POST /api/athletes/ and POST /api/events/
(Security Hardening Pass 1, items 1-2). Both endpoints previously had zero
authentication: POST /api/athletes/ never verified the caller owned
data.parent_id, and POST /api/events/ never verified the caller owned
data.athlete_id. Covers (A) unauthenticated -> 401, (B)/(C) an attacker
cannot create records under a family they don't own, (D) the real owner
still succeeds, preserving all prior business logic (age gate, consent
gate, RETURNING the created row).
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


def make_parent(email, consent=True):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), consent),
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


def _athlete_body(parent_id, **overrides):
    body = {
        "parent_id": parent_id, "first_name": "New Kid", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 4,
    }
    body.update(overrides)
    return body


def _event_body(athlete_id, **overrides):
    body = {
        "athlete_id": athlete_id, "event_name": "Practice", "event_type": "practice",
        "event_date": "2026-08-10",
    }
    body.update(overrides)
    return body


# ── POST /api/athletes/ ───────────────────────────────────────────────────────

def test_create_athlete_requires_a_session(client):
    victim_parent = make_parent("createath1@example.com")
    r = client.post("/api/athletes/", json=_athlete_body(victim_parent))
    assert r.status_code == 401
    assert get_conn().execute(
        "SELECT id FROM athletes WHERE parent_id=%s", (victim_parent,)
    ).fetchone() is None


def test_create_athlete_rejects_unrelated_parent_token(client):
    """The core BOLA case: an attacker who is logged in as THEIR OWN parent
    account must not be able to create an athlete profile under someone
    else's parent_id."""
    victim_parent = make_parent("createath2-victim@example.com")
    attacker_parent = make_parent("createath2-attacker@example.com")
    r = client.post(
        "/api/athletes/", json=_athlete_body(victim_parent),
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT id FROM athletes WHERE parent_id=%s", (victim_parent,)
    ).fetchone() is None


def test_create_athlete_rejects_an_athlete_token_entirely(client):
    """An athlete session (not a parent session) can never create a sibling
    profile — assert_owns_parent requires role == 'parent'."""
    parent_id = make_parent("createath3@example.com")
    existing_athlete = make_athlete(parent_id)
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id),
        headers=auth_headers("athlete", athlete_id=existing_athlete),
    )
    assert r.status_code == 403


def test_create_athlete_allows_owning_parent(client):
    parent_id = make_parent("createath4@example.com")
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 201, r.text
    assert r.json()["parent_id"] == parent_id


def test_create_athlete_still_requires_confirmed_consent(client):
    """Preserve existing business logic: the parent-consent gate still
    applies even for the owning parent."""
    parent_id = make_parent("createath5@example.com", consent=False)
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 403


# ── POST /api/events/ ─────────────────────────────────────────────────────────

def test_create_event_requires_a_session(client):
    victim_parent = make_parent("createev1@example.com")
    victim_athlete = make_athlete(victim_parent)
    r = client.post("/api/events/", json=_event_body(victim_athlete))
    assert r.status_code == 401
    assert get_conn().execute(
        "SELECT id FROM events WHERE athlete_id=%s", (victim_athlete,)
    ).fetchone() is None


def test_create_event_rejects_unrelated_athlete_token(client):
    victim_parent = make_parent("createev2-victim@example.com")
    victim_athlete = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent("createev2-attacker@example.com")
    attacker_athlete = make_athlete(attacker_parent, "Attacker")
    r = client.post(
        "/api/events/", json=_event_body(victim_athlete),
        headers=auth_headers("athlete", athlete_id=attacker_athlete),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT id FROM events WHERE athlete_id=%s", (victim_athlete,)
    ).fetchone() is None


def test_create_event_allows_owning_athlete(client):
    parent_id = make_parent("createev3@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert r.json()["athlete_id"] == athlete_id


def test_create_event_allows_owning_parent(client):
    parent_id = make_parent("createev4@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/events/", json=_event_body(athlete_id),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 201, r.text
