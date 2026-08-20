"""BOLA/auth regression tests — api/routes/meals.py (Security Hardening Pass 1).

Every endpoint in this file had zero authentication before this pass: any
caller could read/write/delete meal-log data for an arbitrary athlete_id, and
the two AI-backed analysis endpoints were open to unmetered cost abuse. This
file proves: (A) unauthenticated -> 401, (B) an unrelated parent cannot
touch another family's meal data, (D) the real owner still succeeds, and
(F) the AI-backed endpoints never invoke the AI service before the ownership
check passes. DELETE is special-cased: the request carries only meal_id, so
ownership is proven by resolving the meal's athlete_id from the DB first.
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
    keepalive.execute("DELETE FROM meal_logs")
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


def make_meal(athlete_id, description="Chicken and rice"):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO meal_logs (athlete_id, log_method, description) "
            "VALUES (%s, 'text', %s) RETURNING id",
            (athlete_id, description),
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


# ── POST /api/meals/ (log_meal) ──────────────────────────────────────────────

def test_log_meal_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("logmeal1")
    r = client.post("/api/meals/", json={"athlete_id": victim_id, "log_method": "text", "description": "Hack"})
    assert r.status_code == 401
    assert get_conn().execute("SELECT id FROM meal_logs WHERE athlete_id=%s", (victim_id,)).fetchone() is None


def test_log_meal_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("logmeal2")
    r = client.post(
        "/api/meals/", json={"athlete_id": victim_id, "log_method": "text", "description": "Hack"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert get_conn().execute("SELECT id FROM meal_logs WHERE athlete_id=%s", (victim_id,)).fetchone() is None


def test_log_meal_allows_owner(client):
    victim_id, _ = _victim_and_attacker("logmeal3")
    r = client.post(
        "/api/meals/", json={"athlete_id": victim_id, "log_method": "text", "description": "Legit meal"},
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 201, r.text


# ── GET /api/meals/athlete/{athlete_id} ──────────────────────────────────────

def test_get_meals_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("getmeals1")
    r = client.get(f"/api/meals/athlete/{victim_id}")
    assert r.status_code == 401


def test_get_meals_rejects_unrelated_parent(client):
    victim_id, _ = _victim_and_attacker("getmeals2")
    attacker_parent = make_parent("getmeals2-attacker-parent@example.com")
    r = client.get(f"/api/meals/athlete/{victim_id}", headers=auth_headers("parent", parent_id=attacker_parent))
    assert r.status_code == 403


def test_get_meals_allows_owning_parent(client):
    victim_parent = make_parent("getmeals3-parent@example.com")
    victim_id = make_athlete(victim_parent)
    r = client.get(f"/api/meals/athlete/{victim_id}", headers=auth_headers("parent", parent_id=victim_parent))
    assert r.status_code == 200


# ── DELETE /api/meals/{meal_id} — ownership resolved via the meal record ────

def test_delete_meal_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("delmeal1")
    meal_id = make_meal(victim_id)
    r = client.delete(f"/api/meals/{meal_id}")
    assert r.status_code == 401
    assert get_conn().execute("SELECT id FROM meal_logs WHERE id=%s", (meal_id,)).fetchone() is not None


def test_delete_meal_rejects_unrelated_athlete_by_resolving_meal_ownership(client):
    """The request only carries meal_id — the route must look up the meal's
    athlete_id itself before checking ownership, not trust a client-supplied one."""
    victim_id, attacker_id = _victim_and_attacker("delmeal2")
    meal_id = make_meal(victim_id)
    r = client.delete(f"/api/meals/{meal_id}", headers=auth_headers("athlete", athlete_id=attacker_id))
    assert r.status_code == 403
    assert get_conn().execute("SELECT id FROM meal_logs WHERE id=%s", (meal_id,)).fetchone() is not None


def test_delete_meal_allows_owner(client):
    victim_id, _ = _victim_and_attacker("delmeal3")
    meal_id = make_meal(victim_id)
    r = client.delete(f"/api/meals/{meal_id}", headers=auth_headers("athlete", athlete_id=victim_id))
    assert r.status_code == 200, r.text
    assert get_conn().execute("SELECT id FROM meal_logs WHERE id=%s", (meal_id,)).fetchone() is None


def test_delete_unknown_meal_still_404s_without_leaking_ownership_info(client):
    victim_id, _ = _victim_and_attacker("delmeal4")
    r = client.delete("/api/meals/999999999", headers=auth_headers("athlete", athlete_id=victim_id))
    assert r.status_code == 404


# ── POST /api/meals/analyze-photo — AI cost-abuse guard ─────────────────────

def test_analyze_photo_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("photo1")
    r = client.post("/api/meals/analyze-photo", json={
        "athlete_id": victim_id, "image_base64": "x" * 200,
    })
    assert r.status_code == 401


def test_analyze_photo_rejects_unrelated_athlete_before_calling_ai(client, monkeypatch):
    victim_id, attacker_id = _victim_and_attacker("photo2")
    calls = []
    import api.services.photo_meal_analyzer as photo_meal_analyzer
    monkeypatch.setattr(photo_meal_analyzer, "analyze_photo", lambda *a, **k: calls.append(1))
    r = client.post(
        "/api/meals/analyze-photo",
        json={"athlete_id": victim_id, "image_base64": "x" * 200},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert calls == [], "AI photo analysis must never run before the ownership check passes"


# ── POST /api/meals/analyze-voice — AI cost-abuse guard ──────────────────────

def test_analyze_voice_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("voice1")
    r = client.post("/api/meals/analyze-voice", json={
        "athlete_id": victim_id, "transcription": "chicken and rice",
    })
    assert r.status_code == 401


def test_analyze_voice_rejects_unrelated_athlete_before_calling_ai(client, monkeypatch):
    victim_id, attacker_id = _victim_and_attacker("voice2")
    calls = []
    import api.services.voice_meal_analyzer as voice_meal_analyzer
    monkeypatch.setattr(voice_meal_analyzer, "analyze_voice", lambda *a, **k: calls.append(1))
    r = client.post(
        "/api/meals/analyze-voice",
        json={"athlete_id": victim_id, "transcription": "chicken and rice"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert calls == [], "AI voice analysis must never run before the ownership check passes"
