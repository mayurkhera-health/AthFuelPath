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


def test_verify_otp_matches_either_of_two_outstanding_valid_codes(client):
    make_parent("parent1@example.com")
    insert_otp_row("parent1@example.com", "111111")  # older
    insert_otp_row("parent1@example.com", "222222")  # newer
    # The OLDER code must still work even though a newer one was issued later.
    r = client.post("/api/parents/verify-otp", json={"email": "parent1@example.com", "code": "111111"})
    assert r.status_code == 200, r.text


# --- deployment safety: email is nullable, not NOT NULL ------------------
#
# The migration adds `email` as nullable (not NOT NULL) specifically so the
# currently-deployed Phase 0 Cloud Run revision — which still inserts
# otp_codes rows with no email value at all — keeps working during a
# rolling deploy where the old revision and the new schema are briefly
# live together. These tests prove that property directly against the
# real schema, independent of any application code path.

def _insert_legacy_phase0_row(parent_id, code, *, expires_in_minutes=10):
    """Simulate exactly what the currently-deployed Phase 0 revision's
    INSERT statement does: parent_id + code_hash + expires_at only, no
    email column at all."""
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=expires_in_minutes)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO otp_codes (parent_id, code_hash, expires_at) VALUES (%s, %s, %s)",
            (parent_id, code_hash, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_legacy_phase0_row_with_no_email_remains_valid_after_migration(client):
    parent_id = make_parent("parent1@example.com")
    # Must not raise (would violate a NOT NULL constraint on email if one
    # existed) — this is the core deployment-safety property.
    _insert_legacy_phase0_row(parent_id, "999999")

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM otp_codes WHERE parent_id = %s ORDER BY created_at DESC LIMIT 1",
            (parent_id,),
        ).fetchone()
    finally:
        conn.close()
    row = dict(row)
    assert row["email"] is None
    assert row["parent_id"] == parent_id
    assert row["attempts"] == 0  # DEFAULT 0 still applies to legacy inserts


def test_legacy_row_is_backfilled_to_normalized_email_by_migration_sql(client):
    parent_id = make_parent("Parent1@Example.com")
    _insert_legacy_phase0_row(parent_id, "999999")

    # Re-run the exact backfill statement from
    # db/postgres/002_otp_codes_email.sql to prove it correctly normalizes
    # (lowercases) and populates email for a pre-existing, email-less row.
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE otp_codes o
            SET email = lower(p.email)
            FROM parents p
            WHERE o.parent_id = p.id AND o.email IS NULL
            """
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM otp_codes WHERE parent_id = %s ORDER BY created_at DESC LIMIT 1",
            (parent_id,),
        ).fetchone()
    finally:
        conn.close()
    assert dict(row)["email"] == "parent1@example.com"
