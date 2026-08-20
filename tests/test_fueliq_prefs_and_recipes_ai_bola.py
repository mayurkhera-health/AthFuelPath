"""BOLA/auth regression tests — Security Hardening Pass 1, items 6-7:
  PATCH /api/notifications/fueliq-prefs
  POST  /api/recipes/generate   (AI-backed)
  POST  /api/recipes/swap       (AI-backed)

All three were previously unauthenticated. The two recipe endpoints call an
AI/model service — item F requires proving the ownership check runs BEFORE
that call, both for BOLA protection and cost-abuse prevention.
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
    keepalive.execute("DELETE FROM fueliq_notification_prefs")
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


def make_athlete(parent_id, first_name="Alex", allergies="peanuts"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, allergies)
               VALUES (%s, %s, 15, 'girl', 115, 5, 6, %s) RETURNING id""",
            (parent_id, first_name, allergies),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def _victim_and_attacker(email_prefix):
    victim_parent = make_parent(f"{email_prefix}-victim@example.com")
    victim_athlete = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent(f"{email_prefix}-attacker@example.com")
    attacker_athlete = make_athlete(attacker_parent, "Attacker")
    return victim_athlete, attacker_athlete


# ── PATCH /api/notifications/fueliq-prefs ────────────────────────────────────

def test_fueliq_prefs_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("fqprefs1")
    r = client.patch("/api/notifications/fueliq-prefs", json={"athlete_id": victim_id, "morning_enabled": False})
    assert r.status_code == 401
    assert get_conn().execute(
        "SELECT athlete_id FROM fueliq_notification_prefs WHERE athlete_id=%s", (victim_id,)
    ).fetchone() is None


def test_fueliq_prefs_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("fqprefs2")
    r = client.patch(
        "/api/notifications/fueliq-prefs",
        json={"athlete_id": victim_id, "morning_enabled": False},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT athlete_id FROM fueliq_notification_prefs WHERE athlete_id=%s", (victim_id,)
    ).fetchone() is None


def test_fueliq_prefs_allows_owner(client):
    victim_id, _ = _victim_and_attacker("fqprefs3")
    r = client.patch(
        "/api/notifications/fueliq-prefs",
        json={"athlete_id": victim_id, "morning_enabled": False},
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text


# ── POST /api/recipes/generate — AI cost-abuse guard ─────────────────────────

def test_recipe_generate_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("recgen1")
    r = client.post("/api/recipes/generate", json={"athlete_id": victim_id, "category": "halftime"})
    assert r.status_code == 401


def test_recipe_generate_rejects_unrelated_athlete_before_calling_ai(client, monkeypatch):
    victim_id, attacker_id = _victim_and_attacker("recgen2")
    calls = []
    import api.services.recipe_generator as recipe_generator
    monkeypatch.setattr(recipe_generator, "generate_recipe", lambda *a, **k: calls.append(1))
    r = client.post(
        "/api/recipes/generate", json={"athlete_id": victim_id, "category": "halftime"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert calls == [], "recipe generation must never call the AI service before the ownership check passes"


# ── POST /api/recipes/swap — AI cost-abuse guard ─────────────────────────────

def test_recipe_swap_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("recswap1")
    r = client.post("/api/recipes/swap", json={
        "athlete_id": victim_id, "disliked_recipe": "R011", "meal_timing_category": "halftime",
    })
    assert r.status_code == 401


def test_recipe_swap_rejects_unrelated_athlete_before_calling_ai(client, monkeypatch):
    victim_id, attacker_id = _victim_and_attacker("recswap2")
    calls = []
    import api.services.claude_ai as claude_ai
    monkeypatch.setattr(claude_ai, "prompt4_recipe_swap", lambda *a, **k: calls.append(1))
    r = client.post(
        "/api/recipes/swap",
        json={"athlete_id": victim_id, "disliked_recipe": "R011", "meal_timing_category": "halftime"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert calls == [], "recipe swap must never call the AI service before the ownership check passes"
