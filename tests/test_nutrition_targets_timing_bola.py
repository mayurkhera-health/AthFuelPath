"""BOLA/auth regression tests — GET /api/nutrition/targets/{athlete_id} and
GET /api/nutrition/timing/{athlete_id} (Security Hardening Pass 1, item 5).
Both were previously unauthenticated; /targets also writes (upserts
daily_targets) on every call, so an attacker could both read and mutate an
arbitrary athlete's nutrition data.
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
    keepalive.execute("DELETE FROM daily_targets")
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


# ── GET /api/nutrition/targets/{athlete_id} ──────────────────────────────────

def test_get_targets_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("targets1")
    r = client.get(f"/api/nutrition/targets/{victim_id}")
    assert r.status_code == 401
    assert get_conn().execute(
        "SELECT id FROM daily_targets WHERE athlete_id=%s", (victim_id,)
    ).fetchone() is None, "must not upsert targets before the auth check"


def test_get_targets_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("targets2")
    r = client.get(f"/api/nutrition/targets/{victim_id}", headers=auth_headers("athlete", athlete_id=attacker_id))
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT id FROM daily_targets WHERE athlete_id=%s", (victim_id,)
    ).fetchone() is None


def test_get_targets_allows_owner(client):
    victim_id, _ = _victim_and_attacker("targets3")
    r = client.get(f"/api/nutrition/targets/{victim_id}", headers=auth_headers("athlete", athlete_id=victim_id))
    assert r.status_code == 200, r.text


# ── GET /api/nutrition/timing/{athlete_id} ───────────────────────────────────

def test_get_timing_requires_a_session(client):
    victim_id, _ = _victim_and_attacker("timing1")
    r = client.get(f"/api/nutrition/timing/{victim_id}")
    assert r.status_code == 401


def test_get_timing_rejects_unrelated_athlete_token(client):
    victim_id, attacker_id = _victim_and_attacker("timing2")
    r = client.get(f"/api/nutrition/timing/{victim_id}", headers=auth_headers("athlete", athlete_id=attacker_id))
    assert r.status_code == 403


def test_get_timing_allows_owner(client):
    victim_id, _ = _victim_and_attacker("timing3")
    r = client.get(f"/api/nutrition/timing/{victim_id}", headers=auth_headers("athlete", athlete_id=victim_id))
    assert r.status_code == 200, r.text
