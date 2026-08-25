"""
POST /api/auth/provider/challenge (auth v2.1 Phase 6, plan A.6/C.1).

A server-issued, single-use, short-lived nonce challenge that replaces a
mobile-generated nonce as the authoritative replay-protection mechanism for
Google/Apple sign-in. No auth is required to issue a challenge — it reveals
nothing about any account, it's purely {challenge_id, provider, raw_nonce,
expires_at, consumed_at NULL}.

Also covers A.11's opportunistic cleanup, piggybacked on this endpoint's own
entry point: expired provider_auth_challenges rows and expired *unconsumed*
apple_pending_links rows are swept on every call; already-consumed pending
links are left alone.
"""

import base64
import os

os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app

TEST_KEY_B64 = base64.b64encode(b"0" * 32).decode()


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM provider_auth_challenges")
    keepalive.execute("DELETE FROM apple_provider_credentials")
    keepalive.execute("DELETE FROM apple_pending_links")
    keepalive.execute("DELETE FROM auth_identities")
    keepalive.execute("DELETE FROM otp_codes")
    keepalive.execute("DELETE FROM athlete_logins")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def get_challenge_row(challenge_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM provider_auth_challenges WHERE challenge_id = %s", (challenge_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_challenges():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM provider_auth_challenges").fetchone()["c"]
    finally:
        conn.close()


def insert_expired_challenge(provider="google"):
    # NOTE: expires_at is inserted via Postgres's own `now() - interval`,
    # not a Python-computed isoformat() string -- this session's timezone is
    # not guaranteed to be UTC, and a naive Python datetime written into a
    # TIMESTAMPTZ column gets (mis)interpreted in that session timezone
    # rather than UTC, which would silently produce a non-expired row here.
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO provider_auth_challenges (challenge_id, provider, raw_nonce, expires_at) "
            "VALUES (%s, %s, %s, now() - interval '1 minute')",
            ("expired-challenge-id", provider, "some-raw-nonce"),
        )
        conn.commit()
    finally:
        conn.close()


def insert_pending_link(pending_link_id, *, expires_offset_minutes, consumed_at=None):
    """expires_offset_minutes: negative = already expired, positive = still
    valid. Computed via Postgres's own now() + interval, for the same
    TIMESTAMPTZ/session-timezone reason as insert_expired_challenge above."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO apple_pending_links "
            "(pending_link_id, provider_subject, email_from_token, email_verified_from_token, "
            "encrypted_refresh_token, encryption_nonce, expires_at, consumed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s), %s)",
            (pending_link_id, "some-apple-sub", "someone@example.com", True,
             b"fake-ciphertext", b"fake-nonce-12", expires_offset_minutes, consumed_at),
        )
        conn.commit()
    finally:
        conn.close()


def count_pending_links():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM apple_pending_links").fetchone()["c"]
    finally:
        conn.close()


# --- Happy path ------------------------------------------------------------

def test_provider_challenge_google_returns_challenge_id_and_nonce(client):
    r = client.post("/api/auth/provider/challenge", json={"provider": "google"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["challenge_id"]
    assert body["nonce"]
    assert body["challenge_id"] != body["nonce"]


def test_provider_challenge_apple_returns_challenge_id_and_nonce(client):
    r = client.post("/api/auth/provider/challenge", json={"provider": "apple"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["challenge_id"]
    assert body["nonce"]


def test_provider_challenge_creates_db_row_with_correct_shape(client):
    r = client.post("/api/auth/provider/challenge", json={"provider": "google"})
    body = r.json()
    row = get_challenge_row(body["challenge_id"])
    assert row is not None
    assert row["provider"] == "google"
    assert row["raw_nonce"] == body["nonce"]
    assert row["consumed_at"] is None
    assert row["expires_at"] is not None


def test_provider_challenge_two_calls_produce_different_ids_and_nonces(client):
    r1 = client.post("/api/auth/provider/challenge", json={"provider": "google"}).json()
    r2 = client.post("/api/auth/provider/challenge", json={"provider": "google"}).json()
    assert r1["challenge_id"] != r2["challenge_id"]
    assert r1["nonce"] != r2["nonce"]


# --- Validation --------------------------------------------------------

def test_provider_challenge_rejects_unsupported_provider(client):
    r = client.post("/api/auth/provider/challenge", json={"provider": "facebook"})
    assert r.status_code == 422, r.text
    assert count_challenges() == 0


def test_provider_challenge_rejects_missing_provider_field(client):
    r = client.post("/api/auth/provider/challenge", json={})
    assert r.status_code == 422, r.text


# --- A.11 opportunistic cleanup -----------------------------------------

def test_provider_challenge_cleans_up_expired_challenges(client):
    insert_expired_challenge(provider="google")
    assert count_challenges() == 1
    client.post("/api/auth/provider/challenge", json={"provider": "apple"})
    # The expired row is gone; only the newly-created one remains.
    assert count_challenges() == 1
    row = get_challenge_row("expired-challenge-id")
    assert row is None


def test_provider_challenge_cleans_up_expired_unconsumed_pending_links(client):
    insert_pending_link("expired-unconsumed", expires_offset_minutes=-1, consumed_at=None)
    assert count_pending_links() == 1
    client.post("/api/auth/provider/challenge", json={"provider": "google"})
    assert count_pending_links() == 0


def test_provider_challenge_does_not_clean_up_expired_but_consumed_pending_links(client):
    # Consumed pending links (successfully completed Apple links) are
    # intentionally left alone by cleanup — they're inert once consumed.
    insert_pending_link(
        "expired-but-consumed", expires_offset_minutes=-1, consumed_at=datetime.utcnow().isoformat(),
    )
    assert count_pending_links() == 1
    client.post("/api/auth/provider/challenge", json={"provider": "google"})
    assert count_pending_links() == 1


def test_provider_challenge_does_not_clean_up_unexpired_pending_links(client):
    insert_pending_link("not-expired-yet", expires_offset_minutes=10, consumed_at=None)
    assert count_pending_links() == 1
    client.post("/api/auth/provider/challenge", json={"provider": "google"})
    assert count_pending_links() == 1
