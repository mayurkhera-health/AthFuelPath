"""
Integration tests for the unified auth flow — the parent-vs-athlete model.

These tests pin down WHO can log in and HOW:
  - Parents always have a login (their email IS their account).
  - Athletes have NO email by default; they get one only via
    POST /api/auth/athlete-create-login/{athlete_id}, gated on the parent.
  - POST /api/auth/login resolves either persona from a single email and
    reports role = "parent" | "athlete".

Athletes are inserted directly into the DB rather than through
POST /api/athletes/, which fires a background AI-blueprint (Bedrock) task we
don't want running in a unit test.
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


@pytest.fixture
def client():
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    # clean slate for each test (the in-memory DB persists across the module)
    keepalive.execute("DELETE FROM athlete_logins")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


# --- helpers -------------------------------------------------------------

def make_parent(email, full_name="Test Parent", consent=True):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (%s, %s, %s, %s) RETURNING id",
            (full_name, email.lower(), datetime.utcnow().isoformat(), consent),
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


# --- unified login: parent ----------------------------------------------

def test_login_resolves_parent_with_athletes(client):
    pid = make_parent("parent1@example.com")
    make_athlete(pid, "Alex")
    make_athlete(pid, "Sam")

    r = client.post("/api/auth/login", json={"email": "parent1@example.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["email"] == "parent1@example.com"
    names = sorted(a["first_name"] for a in body["athletes"])
    assert names == ["Alex", "Sam"]


def test_login_parent_is_case_insensitive(client):
    make_parent("parent1@example.com")
    r = client.post("/api/auth/login", json={"email": "Parent1@Example.COM"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "parent"


def test_login_parent_with_no_athletes_returns_empty_list(client):
    make_parent("lonely@example.com")
    r = client.post("/api/auth/login", json={"email": "lonely@example.com"})
    assert r.status_code == 200, r.text
    assert r.json()["athletes"] == []


# --- unified login: athlete ---------------------------------------------

def test_login_resolves_athlete_after_login_created(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")

    # athlete gets their own login through the gated endpoint
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com"},
    )
    assert r.status_code == 200, r.text

    # now the athlete can log in by their own email and is resolved as an athlete
    r = client.post("/api/auth/login", json={"email": "alex@example.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "athlete"
    assert body["athlete"]["first_name"] == "Alex"
    assert "athletes" not in body  # athletes see only themselves


def test_login_unknown_email_404(client):
    r = client.post("/api/auth/login", json={"email": "nobody@example.com"})
    assert r.status_code == 404, r.text


def test_athlete_with_no_login_cannot_log_in(client):
    pid = make_parent("parent1@example.com")
    make_athlete(pid, "Sam")  # exists, but never given a login
    # Sam has no email anywhere, so there is nothing to log in with.
    r = client.post("/api/auth/login", json={"email": "sam@example.com"})
    assert r.status_code == 404, r.text


# --- athlete-create-login: the gates ------------------------------------

def test_create_login_requires_existing_parent(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "ghost@example.com"},
    )
    assert r.status_code == 403, r.text


def test_create_login_requires_athlete_belongs_to_parent(client):
    p1 = make_parent("parent1@example.com")
    p2 = make_parent("parent2@example.com")
    other_kid = make_athlete(p2, "Jordan")  # belongs to parent2
    # parent1 tries to claim parent2's athlete
    r = client.post(
        f"/api/auth/athlete-create-login/{other_kid}",
        json={"email": "jordan@example.com", "parent_email": "parent1@example.com"},
    )
    assert r.status_code == 403, r.text


def test_create_login_rejects_duplicate_for_same_athlete(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    first = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com"},
    )
    assert first.status_code == 200, first.text
    again = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex2@example.com", "parent_email": "parent1@example.com"},
    )
    assert again.status_code == 409, again.text


def test_create_login_rejects_email_already_taken(client):
    pid = make_parent("parent1@example.com")
    a1 = make_athlete(pid, "Alex")
    a2 = make_athlete(pid, "Sam")
    r1 = client.post(
        f"/api/auth/athlete-create-login/{a1}",
        json={"email": "shared@example.com", "parent_email": "parent1@example.com"},
    )
    assert r1.status_code == 200, r1.text
    # second athlete tries to claim the same email
    r2 = client.post(
        f"/api/auth/athlete-create-login/{a2}",
        json={"email": "shared@example.com", "parent_email": "parent1@example.com"},
    )
    assert r2.status_code == 409, r2.text


# --- precedence: parent wins when an email is both ----------------------

def test_parent_takes_precedence_over_athlete_login(client):
    # An email registered as a parent resolves as parent even if the same string
    # somehow exists as an athlete login (parents are checked first).
    pid = make_parent("dual@example.com")
    aid = make_athlete(pid, "Alex")
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)",
            ("dual@example.com", aid),
        )
        conn.commit()
    finally:
        conn.close()

    r = client.post("/api/auth/login", json={"email": "dual@example.com"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "parent"


# --- athlete-claim-lookup: token-free parent/athlete lookup (auth v2.1 Phase 0) ---
# Tightened per 2026-08-20 security review: response is {athletes:[{id,first_name}]}
# ONLY — no parent_name, no age, no full parent/athlete row, no session_token, and
# no distinct error for an unknown email (same 200 {athletes: []} shape either way,
# so the endpoint never discloses whether a given email has an account).

def test_claim_lookup_returns_only_id_and_first_name_no_pii_no_token(client):
    pid = make_parent("parent1@example.com", full_name="Casey Parent")
    make_athlete(pid, "Alex")
    make_athlete(pid, "Sam")

    r = client.post("/api/auth/athlete-claim-lookup", json={"parent_email": "parent1@example.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"athletes"}
    for athlete in body["athletes"]:
        assert set(athlete.keys()) == {"id", "first_name"}
    names = sorted(a["first_name"] for a in body["athletes"])
    assert names == ["Alex", "Sam"]


def test_claim_lookup_is_case_insensitive(client):
    pid = make_parent("parent1@example.com", full_name="Casey Parent")
    make_athlete(pid, "Alex")
    r = client.post("/api/auth/athlete-claim-lookup", json={"parent_email": "Parent1@Example.COM"})
    assert r.status_code == 200, r.text
    assert r.json()["athletes"][0]["first_name"] == "Alex"


def test_claim_lookup_parent_with_no_athletes_returns_empty_list(client):
    make_parent("lonely@example.com")
    r = client.post("/api/auth/athlete-claim-lookup", json={"parent_email": "lonely@example.com"})
    assert r.status_code == 200, r.text
    assert r.json() == {"athletes": []}


def test_claim_lookup_unknown_email_returns_200_empty_list_not_404(client):
    r = client.post("/api/auth/athlete-claim-lookup", json={"parent_email": "nobody@example.com"})
    assert r.status_code == 200, r.text
    assert r.json() == {"athletes": []}


def test_claim_lookup_unknown_email_is_indistinguishable_from_zero_athletes(client):
    # Same exact response shape for "no such parent" and "real parent, no kids yet" —
    # the API contract must not let a caller tell these two cases apart.
    make_parent("lonely@example.com")
    zero_athletes_body = client.post(
        "/api/auth/athlete-claim-lookup", json={"parent_email": "lonely@example.com"}
    ).json()
    unknown_email_body = client.post(
        "/api/auth/athlete-claim-lookup", json={"parent_email": "nobody@example.com"}
    ).json()
    assert zero_athletes_body == unknown_email_body == {"athletes": []}


def test_claim_lookup_athlete_email_is_not_a_parent_match(client):
    # An athlete's own login email must not resolve here — this endpoint only
    # ever looks at the parents table. Same 200 {athletes: []} shape as any
    # other non-match — no distinct error.
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com"},
    )
    r = client.post("/api/auth/athlete-claim-lookup", json={"parent_email": "alex@example.com"})
    assert r.status_code == 200, r.text
    assert r.json() == {"athletes": []}
