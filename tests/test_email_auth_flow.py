"""
POST /api/auth/email/request and POST /api/auth/email/verify (auth v2.1
Phase 2). The whole point of these two endpoints: an unverified caller who
only knows an email address must never be able to tell, from either
endpoint's response, whether that email has an AthFuelPath account — and
must never be able to obtain a session without first proving ownership of
the email via a correct OTP.
"""

import hashlib
import os

os.environ["DB_PATH"] = ":memory:"

from datetime import datetime, timedelta
from unittest.mock import patch

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


# --- /email/request: neutral, non-enumerating ---------------------------

def test_email_request_existing_account_returns_200_and_sends_otp(client):
    make_parent("parent1@example.com")
    r = client.post("/api/auth/email/request", json={"email": "parent1@example.com"})
    assert r.status_code == 200, r.text
    assert latest_otp_row("parent1@example.com") is not None


def test_email_request_nonexistent_email_also_returns_200_and_sends_otp(client):
    r = client.post("/api/auth/email/request", json={"email": "nobody@example.com"})
    assert r.status_code == 200, r.text
    assert latest_otp_row("nobody@example.com") is not None


def test_email_request_response_is_byte_identical_for_existing_vs_nonexistent_email(client):
    make_parent("parent1@example.com")
    r1 = client.post("/api/auth/email/request", json={"email": "parent1@example.com"})
    r2 = client.post("/api/auth/email/request", json={"email": "somebody-else@example.com"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()


def test_email_request_does_not_create_a_parent_account(client):
    r = client.post("/api/auth/email/request", json={"email": "nobody@example.com"})
    assert r.status_code == 200, r.text
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM parents WHERE lower(email) = %s", ("nobody@example.com",)
        ).fetchone()
    finally:
        conn.close()
    assert row is None


def test_email_request_inherits_60s_resend_rate_limit(client):
    r1 = client.post("/api/auth/email/request", json={"email": "nobody@example.com"})
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/auth/email/request", json={"email": "nobody@example.com"})
    assert r2.status_code == 429, r2.text


def test_email_request_gmail_failure_returns_502(client):
    with patch("api.routes.auth.issue_otp", side_effect=__import__("api.services.otp_auth", fromlist=["OtpDeliveryFailed"]).OtpDeliveryFailed()):
        r = client.post("/api/auth/email/request", json={"email": "nobody@example.com"})
    assert r.status_code == 502, r.text


def test_email_request_gmail_failure_cleans_up_otp_row(client):
    with patch("api.services.otp_auth.send_otp_email", return_value=False):
        r = client.post("/api/auth/email/request", json={"email": "nobody@example.com"})
    assert r.status_code == 502, r.text
    assert latest_otp_row("nobody@example.com") is None
