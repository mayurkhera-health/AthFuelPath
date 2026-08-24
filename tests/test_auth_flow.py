"""
Integration tests for the unified auth flow — the parent-vs-athlete model.

These tests pin down WHO can log in and HOW:
  - Parents always have a login (their email IS their account).
  - Athletes have NO email by default; they get one only via
    POST /api/auth/athlete-create-login/{athlete_id}, gated on the parent.
  - Email-only login (POST /api/auth/login, POST /api/parents/login) was
    retired in auth v2.1 Phase 4; both now 404/405 (see the "legacy ...
    endpoint is gone" tests below). Real login goes through the
    OTP-verified POST /api/auth/email/request + /email/verify flow, which
    resolves either persona from a verified email and reports
    role = "parent" | "athlete".

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
from api.services.session_auth import verify_session_token
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
    keepalive.execute("DELETE FROM otp_codes")
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


def _verified_code_for(email, *, expires_in_minutes=10):
    """Insert a real, matchable OTP row for `email` directly (bypassing
    Gmail), mirroring the pattern in tests/test_email_auth_flow.py, so
    tests can supply genuine proof instead of bypassing the gate."""
    import hashlib
    from datetime import datetime, timedelta
    from api.database import get_conn
    code = "654321"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=expires_in_minutes)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO otp_codes (email, code_hash, expires_at) VALUES (%s, %s, %s)",
            (email.lower(), code_hash, expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    return code


# --- athlete-create-login: the gates ------------------------------------

def test_create_login_requires_existing_parent(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    code = _verified_code_for("ghost@example.com")
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "ghost@example.com", "code": code},
    )
    assert r.status_code == 403, r.text


def test_create_login_requires_athlete_belongs_to_parent(client):
    p1 = make_parent("parent1@example.com")
    p2 = make_parent("parent2@example.com")
    other_kid = make_athlete(p2, "Jordan")  # belongs to parent2
    # parent1 tries to claim parent2's athlete
    code = _verified_code_for("parent1@example.com")
    r = client.post(
        f"/api/auth/athlete-create-login/{other_kid}",
        json={"email": "jordan@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert r.status_code == 403, r.text


def test_create_login_rejects_duplicate_for_same_athlete(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    code = _verified_code_for("parent1@example.com")
    first = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert first.status_code == 200, first.text
    code2 = _verified_code_for("parent1@example.com")
    again = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex2@example.com", "parent_email": "parent1@example.com", "code": code2},
    )
    assert again.status_code == 409, again.text


def test_create_login_rejects_email_already_taken(client):
    pid = make_parent("parent1@example.com")
    a1 = make_athlete(pid, "Alex")
    a2 = make_athlete(pid, "Sam")
    code = _verified_code_for("parent1@example.com")
    r1 = client.post(
        f"/api/auth/athlete-create-login/{a1}",
        json={"email": "shared@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert r1.status_code == 200, r1.text
    # second athlete tries to claim the same email
    code2 = _verified_code_for("parent1@example.com")
    r2 = client.post(
        f"/api/auth/athlete-create-login/{a2}",
        json={"email": "shared@example.com", "parent_email": "parent1@example.com", "code": code2},
    )
    assert r2.status_code == 409, r2.text


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


# --- legacy email-only login routes are gone (auth v2.1 Phase 4) --------

def test_legacy_unified_login_endpoint_is_gone(client):
    r = client.post("/api/auth/login", json={"email": "anyone@example.com"})
    assert r.status_code == 404, r.text


def test_legacy_parents_login_endpoint_is_gone(client):
    # Not a clean 404: parents.py's GET/DELETE /{parent_id} use an untyped
    # (string) path param, so they partially match the path "/login" too —
    # pre-existing, unrelated to this deletion. Starlette reports 405
    # (method not allowed on the matched path) rather than 404 in that case.
    # Either way, no route accepts POST here anymore, so no session is
    # ever minted from this path — the property this test exists to prove.
    r = client.post("/api/parents/login", json={"email": "anyone@example.com"})
    assert r.status_code == 405, r.text


# --- athlete-create-login: mandatory verified parent OTP gate (auth v2.1 Phase 4) ---

def test_claim_parent_email_knowledge_alone_cannot_authorize(client):
    """Knowing the parent's email is not enough without a real OTP."""
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": "000000"},
    )
    assert r.status_code == 401, r.text
    conn = get_conn()
    try:
        row = conn.execute("SELECT 1 FROM athlete_logins WHERE athlete_id = %s", (aid,)).fetchone()
    finally:
        conn.close()
    assert row is None


def test_claim_correct_athlete_email_alone_cannot_authorize(client):
    """A code issued to the ATHLETE's own new email (not the parent's) must
    not authorize the claim — verification is against parent_email only."""
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    code = _verified_code_for("alex@example.com")  # issued to the athlete's email, not the parent's
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert r.status_code == 401, r.text


def test_claim_wrong_parent_otp_cannot_authorize(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    _verified_code_for("parent1@example.com")  # issues "654321"; submit a different code
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": "111111"},
    )
    assert r.status_code == 401, r.text


def test_claim_expired_parent_otp_cannot_authorize(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    code = _verified_code_for("parent1@example.com", expires_in_minutes=-1)
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert r.status_code == 401, r.text


def test_claim_already_used_parent_otp_cannot_authorize_again(client):
    pid = make_parent("parent1@example.com")
    aid1 = make_athlete(pid, "Alex")
    aid2 = make_athlete(pid, "Sam")
    code = _verified_code_for("parent1@example.com")
    first = client.post(
        f"/api/auth/athlete-create-login/{aid1}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/auth/athlete-create-login/{aid2}",
        json={"email": "sam@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert second.status_code == 401, second.text


def test_claim_valid_parent_otp_authorizes_the_selected_athlete(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    code = _verified_code_for("parent1@example.com")
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert r.status_code == 200, r.text
    conn = get_conn()
    try:
        row = conn.execute("SELECT 1 FROM athlete_logins WHERE athlete_id = %s", (aid,)).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_claim_success_issues_only_an_athlete_session_never_a_parent_session(client):
    pid = make_parent("parent1@example.com")
    aid = make_athlete(pid, "Alex")
    code = _verified_code_for("parent1@example.com")
    r = client.post(
        f"/api/auth/athlete-create-login/{aid}",
        json={"email": "alex@example.com", "parent_email": "parent1@example.com", "code": code},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "athlete"
    assert "parent" not in body
    identity = verify_session_token(body["session_token"])
    assert identity["role"] == "athlete"
    assert identity["athlete_id"] == aid
