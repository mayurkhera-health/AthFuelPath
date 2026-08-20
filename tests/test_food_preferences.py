"""Onboarding-wizard `food_preferences` field:
migration (idempotent + column add) and create/read round-trip through the API."""

import os
os.environ["DB_PATH"] = ":memory:"

import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all, _add_food_preferences_to_athletes
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


# ── Migration ────────────────────────────────────────────────────────────────

def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_food_preferences_migration_adds_column():
    conn = _mk_conn()
    conn.execute("CREATE TABLE athletes (id INTEGER PRIMARY KEY)")
    _add_food_preferences_to_athletes(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()}
    assert "food_preferences" in cols


def test_food_preferences_migration_is_idempotent():
    conn = _mk_conn()
    conn.execute("CREATE TABLE athletes (id INTEGER PRIMARY KEY)")
    _add_food_preferences_to_athletes(conn)
    _add_food_preferences_to_athletes(conn)  # second run must not raise
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    assert cols.count("food_preferences") == 1


# ── Create + read round-trip ─────────────────────────────────────────────────

@pytest.fixture
def client():
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    # An athlete can only be created under a consent-confirmed parent.
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO parents (full_name, email, consent_confirmed, consent_timestamp) "
        "VALUES (%s, %s, TRUE, %s) RETURNING id",
        ("Test Parent", f"fp-{uuid.uuid4().hex}@test.com", "2026-06-24T00:00:00Z"),
    )
    parent_id = cur.fetchone()["id"]
    conn.commit()
    with TestClient(app) as c:
        c.parent_id = parent_id
        yield c
    keepalive.close()


def _athlete_payload(parent_id, **overrides):
    body = {
        "parent_id": parent_id,
        "first_name": "Sam",
        "age": 15,
        "gender": "male",
        "weight_lbs": 130.0,
        "height_ft": 5,
        "height_in": 6.0,
        "position": "Midfielder",
        "competition_level": "competitive_club",
        "season_phase": "in_season",
        "allergies": "peanuts",
        "dietary_restrictions": None,
        "food_preferences": "prefers crunchy textures, dislikes mushy foods",
        "sweat_profile": "moderate",
    }
    body.update(overrides)
    return body


def test_food_preferences_round_trips_create_and_get(client):
    pref = "prefers crunchy textures, dislikes mushy foods"
    r = client.post("/api/athletes/", json=_athlete_payload(client.parent_id))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["food_preferences"] == pref

    got = client.get(
        f"/api/athletes/{created['id']}",
        headers=auth_headers("athlete", athlete_id=created["id"]),
    )
    assert got.status_code == 200, got.text
    assert got.json()["food_preferences"] == pref


def test_food_preferences_nullable_on_create(client):
    r = client.post("/api/athletes/", json=_athlete_payload(client.parent_id, food_preferences=None))
    assert r.status_code == 201, r.text
    assert r.json()["food_preferences"] is None
