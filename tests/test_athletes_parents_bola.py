"""BOLA regression tests — GET/PUT /api/athletes/{id} and the parent-scoped
profile/delete routes now require a session token that actually owns the
record, closing the gap tests/test_confirmations_bola.py documents for the
confirmations endpoints (fixed separately in fuel_report.py)."""
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
    keepalive.execute("DELETE FROM account_deletion_requests")
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
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (?, ?, ?, ?)",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), 1),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in)
               VALUES (?, ?, 15, 'girl', 115, 5, 6)""",
            (parent_id, first_name),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _athlete_update_body(athlete_id, **overrides):
    body = {
        "parent_id": 1, "first_name": "Alex", "age": 15, "gender": "girl",
        "weight_lbs": 115, "height_ft": 5, "height_in": 6,
    }
    body.update(overrides)
    return body


# ── GET /api/athletes/{id} ────────────────────────────────────────────────────

def test_get_athlete_requires_a_session(client):
    victim_parent = make_parent("v1@example.com")
    victim_id = make_athlete(victim_parent)
    r = client.get(f"/api/athletes/{victim_id}")
    assert r.status_code == 401


def test_get_athlete_rejects_unrelated_parent(client):
    victim_parent = make_parent("v2@example.com")
    victim_id = make_athlete(victim_parent)
    attacker_parent = make_parent("attacker2@example.com")
    r = client.get(f"/api/athletes/{victim_id}", headers=auth_headers("parent", parent_id=attacker_parent))
    assert r.status_code == 403


def test_get_athlete_allows_owning_parent(client):
    parent_id = make_parent("owner1@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.get(f"/api/athletes/{athlete_id}", headers=auth_headers("parent", parent_id=parent_id))
    assert r.status_code == 200


def test_get_athlete_allows_self(client):
    parent_id = make_parent("owner2@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.get(f"/api/athletes/{athlete_id}", headers=auth_headers("athlete", athlete_id=athlete_id))
    assert r.status_code == 200


# ── PUT /api/athletes/{id} ────────────────────────────────────────────────────

def test_update_athlete_rejects_unrelated_athlete_token(client):
    victim_parent = make_parent("v3@example.com")
    victim_id = make_athlete(victim_parent)
    attacker_id = make_athlete(make_parent("attacker3@example.com"), "Attacker")
    r = client.put(
        f"/api/athletes/{victim_id}",
        json=_athlete_update_body(victim_id, first_name="Hacked"),
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    row = get_conn().execute("SELECT first_name FROM athletes WHERE id=?", (victim_id,)).fetchone()
    assert row["first_name"] != "Hacked"


# ── DELETE /api/parents/{id} ──────────────────────────────────────────────────

def test_delete_parent_account_requires_a_session(client):
    victim_parent = make_parent("v4@example.com")
    r = client.delete(f"/api/parents/{victim_parent}")
    assert r.status_code == 401
    assert get_conn().execute("SELECT id FROM parents WHERE id=?", (victim_parent,)).fetchone()


def test_delete_parent_account_rejects_unrelated_parent(client):
    victim_parent = make_parent("v5@example.com")
    attacker_parent = make_parent("attacker5@example.com")
    r = client.delete(
        f"/api/parents/{victim_parent}",
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert get_conn().execute("SELECT id FROM parents WHERE id=?", (victim_parent,)).fetchone()


def test_delete_parent_account_allows_owner(client):
    """Delete Account no longer deletes in-app (2026-07-27 product decision —
    see test_account_deletion_request.py) — it records the request and the
    owning parent can still submit it; the account itself is untouched here."""
    parent_id = make_parent("owner3@example.com")
    r = client.delete(
        f"/api/parents/{parent_id}",
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 200
    assert r.json()["received"] is True
    assert get_conn().execute("SELECT id FROM parents WHERE id=?", (parent_id,)).fetchone() is not None


# ── PATCH /api/parents/{id}/profile ───────────────────────────────────────────

def test_update_parent_profile_rejects_unrelated_parent(client):
    victim_parent = make_parent("v6@example.com")
    attacker_parent = make_parent("attacker6@example.com")
    r = client.patch(
        f"/api/parents/{victim_parent}/profile",
        json={"full_name": "Hacked Name", "phone": None},
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    row = get_conn().execute("SELECT full_name FROM parents WHERE id=?", (victim_parent,)).fetchone()
    assert row["full_name"] != "Hacked Name"
