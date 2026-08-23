"""
GET /api/auth/session (auth v2.1 Phase 3). Restore an existing session from
the AthFuelPath bearer token alone — no email involved anywhere in this
handler. This lets the mobile app skip OTP/login on launch while the stored
token is still valid.
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
from api.services.session_auth import mint_session_token


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM athlete_logins")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def make_parent(email, full_name="Test Parent"):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (%s, %s, %s, %s) RETURNING id",
            (full_name, email.lower(), datetime.utcnow().isoformat(), True),
        )
        row = cur.fetchone()
        conn.commit()
        return row["id"]
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in)
               VALUES (%s, %s, 14, 'Boy', 120, 5, 6) RETURNING id""",
            (parent_id, first_name),
        )
        row = cur.fetchone()
        conn.commit()
        return row["id"]
    finally:
        conn.close()


def make_athlete_login(athlete_id, email):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)",
            (email.lower(), athlete_id),
        )
        conn.commit()
    finally:
        conn.close()


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_parent_token_restores_parent_session(client):
    parent_id = make_parent("parent1@example.com")
    make_athlete(parent_id, "Alex")
    token = mint_session_token(role="parent", parent_id=parent_id)
    r = client.get("/api/auth/session", headers=auth_header(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["id"] == parent_id
    assert len(body["athletes"]) == 1


def test_valid_athlete_token_restores_athlete_session(client):
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")
    token = mint_session_token(role="athlete", athlete_id=athlete_id, parent_id=parent_id)
    r = client.get("/api/auth/session", headers=auth_header(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "athlete"
    assert body["athlete"]["id"] == athlete_id
    assert body["email"] == "alex@example.com"


def test_expired_token_401s(client):
    parent_id = make_parent("parent1@example.com")
    token = mint_session_token(role="parent", parent_id=parent_id, ttl_seconds=-10)
    r = client.get("/api/auth/session", headers=auth_header(token))
    assert r.status_code == 401, r.text


def test_malformed_token_401s(client):
    r = client.get("/api/auth/session", headers=auth_header("not-a-real-token"))
    assert r.status_code == 401, r.text


def test_no_token_401s(client):
    r = client.get("/api/auth/session")
    assert r.status_code == 401, r.text


def test_email_alone_cannot_restore_a_session(client):
    make_parent("parent1@example.com")
    # No Authorization header at all — an email-only attempt (e.g. as a query
    # param) must be rejected exactly the same as no credentials at all.
    r = client.get("/api/auth/session?email=parent1@example.com")
    assert r.status_code == 401, r.text


def test_deleted_parent_account_401s_not_500(client):
    parent_id = make_parent("parent1@example.com")
    token = mint_session_token(role="parent", parent_id=parent_id)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM parents WHERE id = %s", (parent_id,))
        conn.commit()
    finally:
        conn.close()
    r = client.get("/api/auth/session", headers=auth_header(token))
    assert r.status_code == 401, r.text


def test_deleted_athlete_account_401s_not_500(client):
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")
    token = mint_session_token(role="athlete", athlete_id=athlete_id, parent_id=parent_id)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM athletes WHERE id = %s", (athlete_id,))
        conn.commit()
    finally:
        conn.close()
    r = client.get("/api/auth/session", headers=auth_header(token))
    assert r.status_code == 401, r.text
