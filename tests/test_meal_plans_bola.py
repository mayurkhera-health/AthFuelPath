"""BOLA/auth regression tests — api/routes/meal_plans.py (Security Hardening
Pass 1). Every endpoint here had zero authentication before this pass,
including an AI-backed POST /generate open to cost abuse. Covers: (A)
unauthenticated -> 401, (B) an unrelated parent cannot touch another
family's meal plan, (D) the real owner still succeeds, (F) the AI-backed
/generate endpoint never invokes Claude before the ownership check passes.
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
    keepalive.execute("DELETE FROM meal_plans")
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


def _victim_and_attacker(email_prefix):
    victim_parent = make_parent(f"{email_prefix}-victim@example.com")
    victim_athlete = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent(f"{email_prefix}-attacker@example.com")
    attacker_athlete = make_athlete(attacker_parent, "Attacker")
    return victim_athlete, attacker_athlete


# ── GET /api/meal-plans/{athlete_id} ─────────────────────────────────────────

def test_get_meal_plan_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("plan-get1")
    r = client.get(f"/api/meal-plans/{victim_id}")
    assert r.status_code == 401


def test_get_meal_plan_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("plan-get2")
    r = client.get(f"/api/meal-plans/{victim_id}", headers=auth_headers("athlete", athlete_id=attacker_id))
    assert r.status_code == 403


def test_get_meal_plan_allows_owner(client):
    victim_id, _ = _victim_and_attacker("plan-get3")
    r = client.get(f"/api/meal-plans/{victim_id}", headers=auth_headers("athlete", athlete_id=victim_id))
    assert r.status_code == 200, r.text


# ── PUT /api/meal-plans/{athlete_id}/slot ────────────────────────────────────

def test_set_slot_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("plan-set1")
    r = client.put(f"/api/meal-plans/{victim_id}/slot", json={
        "plan_date": "2026-08-01", "slot_name": "everyday_lunch", "recipe_id": "R011",
    })
    assert r.status_code == 401


def test_set_slot_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("plan-set2")
    r = client.put(
        f"/api/meal-plans/{victim_id}/slot",
        json={"plan_date": "2026-08-01", "slot_name": "everyday_lunch", "recipe_id": "R011"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT id FROM meal_plans WHERE athlete_id=%s", (victim_id,)
    ).fetchone() is None


# ── DELETE /api/meal-plans/{athlete_id}/slot ─────────────────────────────────

def test_clear_slot_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("plan-clear1")
    r = client.delete(f"/api/meal-plans/{victim_id}/slot?plan_date=2026-08-01&slot_name=everyday_lunch")
    assert r.status_code == 401


def test_clear_slot_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("plan-clear2")
    r = client.delete(
        f"/api/meal-plans/{victim_id}/slot?plan_date=2026-08-01&slot_name=everyday_lunch",
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403


# ── POST /api/meal-plans/{athlete_id}/log-slot ───────────────────────────────

def test_log_slot_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("plan-log1")
    r = client.post(f"/api/meal-plans/{victim_id}/log-slot", json={
        "plan_date": "2026-08-01", "slot_name": "everyday_lunch",
    })
    assert r.status_code == 401


def test_log_slot_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("plan-log2")
    r = client.post(
        f"/api/meal-plans/{victim_id}/log-slot",
        json={"plan_date": "2026-08-01", "slot_name": "everyday_lunch"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403


# ── POST /api/meal-plans/generate — AI cost-abuse guard ──────────────────────

def test_generate_plan_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("plan-gen1")
    r = client.post("/api/meal-plans/generate", json={"athlete_id": victim_id, "week_start": "2026-08-02"})
    assert r.status_code == 401


def test_generate_plan_rejects_unrelated_athlete_before_calling_ai(client, monkeypatch):
    victim_id, attacker_id = _victim_and_attacker("plan-gen2")
    calls = []
    import api.services.claude_ai as claude_ai
    monkeypatch.setattr(claude_ai, "prompt6_weekly_meal_plan", lambda *a, **k: calls.append(1))
    r = client.post(
        "/api/meal-plans/generate",
        json={"athlete_id": victim_id, "week_start": "2026-08-02"},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert calls == [], "AI meal-plan generation must never run before the ownership check passes"
