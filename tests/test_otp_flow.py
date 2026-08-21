"""
otp_codes rekeyed to email (auth v2.1 Phase 1).

Covers /api/parents/request-otp and /api/parents/verify-otp, which are
pre-existing, currently-unused-by-any-client endpoints (grepped the mobile
app: zero call sites) being rekeyed from parent_id to email, with a new
5-attempt lockout and a consumed_at audit stamp added.
"""

import hashlib
import os

os.environ["DB_PATH"] = ":memory:"

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM otp_codes")
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


def latest_otp_row(email):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM otp_codes WHERE email = %s ORDER BY created_at DESC LIMIT 1",
            (email.lower(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_otp_row(email, code, *, expires_in_minutes=10, attempts=0, used=0):
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=expires_in_minutes)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO otp_codes (email, code_hash, expires_at, attempts, used) VALUES (%s, %s, %s, %s, %s)",
            (email.lower(), code_hash, expires_at, attempts, used),
        )
        conn.commit()
    finally:
        conn.close()


# --- request-otp: rekeyed to email --------------------------------------

def test_request_otp_creates_row_keyed_by_email(client):
    make_parent("parent1@example.com")
    r = client.post("/api/parents/request-otp", json={"email": "parent1@example.com"})
    assert r.status_code == 200, r.text
    row = latest_otp_row("parent1@example.com")
    assert row is not None
    assert row["attempts"] == 0
    assert row["consumed_at"] is None


def test_request_otp_unknown_email_404(client):
    r = client.post("/api/parents/request-otp", json={"email": "nobody@example.com"})
    assert r.status_code == 404, r.text


def test_request_otp_resend_within_60s_is_rate_limited(client):
    make_parent("parent1@example.com")
    r1 = client.post("/api/parents/request-otp", json={"email": "parent1@example.com"})
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/parents/request-otp", json={"email": "parent1@example.com"})
    assert r2.status_code == 429, r2.text


# --- verify-otp: success path, consumed_at, attempts --------------------

def test_verify_otp_correct_code_succeeds_and_stamps_consumed_at(client):
    make_parent("parent1@example.com")
    insert_otp_row("parent1@example.com", "123456")
    r = client.post("/api/parents/verify-otp", json={"email": "parent1@example.com", "code": "123456"})
    assert r.status_code == 200, r.text
    row = latest_otp_row("parent1@example.com")
    assert row["used"] == 1
    assert row["consumed_at"] is not None


def test_verify_otp_wrong_code_increments_attempts_and_401s(client):
    make_parent("parent1@example.com")
    insert_otp_row("parent1@example.com", "123456")
    r = client.post("/api/parents/verify-otp", json={"email": "parent1@example.com", "code": "000000"})
    assert r.status_code == 401, r.text
    row = latest_otp_row("parent1@example.com")
    assert row["attempts"] == 1
    assert row["used"] == 0


def test_verify_otp_locks_after_5_wrong_attempts_even_with_correct_code(client):
    make_parent("parent1@example.com")
    insert_otp_row("parent1@example.com", "123456")
    for _ in range(5):
        r = client.post("/api/parents/verify-otp", json={"email": "parent1@example.com", "code": "000000"})
        assert r.status_code == 401, r.text
    # 6th call, now with the CORRECT code — still locked out
    r = client.post("/api/parents/verify-otp", json={"email": "parent1@example.com", "code": "123456"})
    assert r.status_code == 401, r.text
    row = latest_otp_row("parent1@example.com")
    assert row["used"] == 0


def test_verify_otp_expired_code_401s(client):
    make_parent("parent1@example.com")
    insert_otp_row("parent1@example.com", "123456", expires_in_minutes=-1)
    r = client.post("/api/parents/verify-otp", json={"email": "parent1@example.com", "code": "123456"})
    assert r.status_code == 401, r.text


def test_verify_otp_unknown_email_404(client):
    r = client.post("/api/parents/verify-otp", json={"email": "nobody@example.com", "code": "123456"})
    assert r.status_code == 404, r.text
