"""
POST /api/auth/google/verify (auth v2.1 Phase 6, plan C.2).

Google's flow is explicitly unchanged/unweakened by this phase: it verifies
the challenge + ID token server-side, then hands straight to the unchanged
resolve_identity(), exactly as email_auth_verify already does for the email
provider. These tests exercise the ROUTE logic (challenge consumption,
resolve/no-resolve branching, session minting) — they mock
verify_google_id_token itself (already tested against real crypto semantics
in tests/test_google_auth.py), never the DB/resolver layer.
"""

import os

os.environ["DB_PATH"] = ":memory:"

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services.google_auth import GoogleVerificationError, VerifiedGoogleIdentity
from api.services.session_auth import verify_session_token

GOOGLE_MSG = "Google sign-in could not be verified. Please try again."


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


def make_parent(email, full_name="Test Parent"):
    from datetime import datetime
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (full_name, email.lower(), datetime.utcnow().isoformat(), True),
        )
        row_id = cur.fetchone()["id"]
        conn.commit()
        return row_id
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
            "VALUES (%s, %s, 14, 'Boy', 120, 5, 6) RETURNING id",
            (parent_id, first_name),
        )
        row_id = cur.fetchone()["id"]
        conn.commit()
        return row_id
    finally:
        conn.close()


def make_athlete_login(athlete_id, email):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)", (email.lower(), athlete_id)
        )
        conn.commit()
    finally:
        conn.close()


def count_auth_identities(provider="google"):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM auth_identities WHERE provider = %s", (provider,)
        ).fetchone()["c"]
    finally:
        conn.close()


def get_auth_identity(provider, provider_subject):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM auth_identities WHERE provider = %s AND provider_subject = %s",
            (provider, provider_subject),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def issue_challenge(client, provider="google"):
    r = client.post("/api/auth/provider/challenge", json={"provider": provider})
    assert r.status_code == 200, r.text
    return r.json()["challenge_id"]


def google_identity(sub="google-sub-1", email="parent1@example.com", email_verified=True):
    return VerifiedGoogleIdentity(sub=sub, email=email, email_verified=email_verified)


def call_google_verify(client, challenge_id, identity=None, error=None):
    target = "api.routes.auth.verify_google_id_token"
    if error is not None:
        with patch(target, side_effect=error):
            return client.post(
                "/api/auth/google/verify",
                json={"challenge_id": challenge_id, "id_token": "fake-id-token"},
            )
    with patch(target, return_value=identity):
        return client.post(
            "/api/auth/google/verify",
            json={"challenge_id": challenge_id, "id_token": "fake-id-token"},
        )


# --- Happy paths -----------------------------------------------------------

def test_valid_credential_resolves_existing_parent(client):
    parent_id = make_parent("parent1@example.com")
    make_athlete(parent_id, "Alex")
    challenge_id = issue_challenge(client)
    r = call_google_verify(client, challenge_id, identity=google_identity(email="parent1@example.com"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["email"] == "parent1@example.com"
    assert body["session_token"]
    identity = verify_session_token(body["session_token"])
    assert identity["role"] == "parent"
    assert identity["parent_id"] == parent_id


def test_valid_credential_resolves_existing_athlete(client):
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")
    challenge_id = issue_challenge(client)
    r = call_google_verify(
        client, challenge_id,
        identity=google_identity(sub="google-athlete-sub", email="alex@example.com"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "athlete"
    assert body["athlete"]["first_name"] == "Alex"
    assert body["session_token"]


def test_stable_sub_saved_as_auth_identity_row(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    call_google_verify(client, challenge_id, identity=google_identity(sub="stable-sub-xyz"))
    row = get_auth_identity("google", "stable-sub-xyz")
    assert row is not None
    assert row["parent_id"] is not None


def test_subsequent_login_uses_exact_subject_mapping_not_email(client):
    parent_id = make_parent("parent1@example.com")
    challenge_id_1 = issue_challenge(client)
    call_google_verify(client, challenge_id_1, identity=google_identity(sub="fixed-sub", email="parent1@example.com"))

    # Second login: same sub, but a DIFFERENT (unverified) email in the
    # token -- the exact (provider, provider_subject) match must still be
    # authoritative and resolve to the same parent, never re-decided by email.
    challenge_id_2 = issue_challenge(client)
    r = call_google_verify(
        client, challenge_id_2,
        identity=google_identity(sub="fixed-sub", email="totally-different@example.com", email_verified=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["id"] == parent_id
    # Still exactly one google auth_identities row for this sub.
    assert count_auth_identities("google") == 1


def test_changed_email_does_not_relink_to_a_different_owner(client):
    parent1_id = make_parent("parent1@example.com")
    make_parent("parent2@example.com")
    challenge_id_1 = issue_challenge(client)
    call_google_verify(client, challenge_id_1, identity=google_identity(sub="fixed-sub-2", email="parent1@example.com"))

    challenge_id_2 = issue_challenge(client)
    r = call_google_verify(
        client, challenge_id_2,
        identity=google_identity(sub="fixed-sub-2", email="parent2@example.com"),
    )
    assert r.status_code == 200, r.text
    # Still resolves to parent1 (the original mapping), never parent2.
    assert r.json()["parent"]["id"] == parent1_id


# --- Verification failures --------------------------------------------

def test_google_verification_error_returns_401_generic_message(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_google_verify(client, challenge_id, error=GoogleVerificationError("bad token"))
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": GOOGLE_MSG}
    assert "session_token" not in r.text


# --- Challenge handling --------------------------------------------------

def test_consumed_challenge_cannot_authenticate_a_second_request(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    first = call_google_verify(client, challenge_id, identity=google_identity())
    assert first.status_code == 200, first.text

    second = call_google_verify(client, challenge_id, identity=google_identity())
    assert second.status_code == 401, second.text
    assert "session_token" not in second.text


def test_challenge_for_wrong_provider_is_rejected(client):
    make_parent("parent1@example.com")
    apple_challenge_id = issue_challenge(client, provider="apple")
    r = call_google_verify(client, apple_challenge_id, identity=google_identity())
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text


def test_unknown_challenge_id_is_rejected(client):
    r = call_google_verify(client, "not-a-real-challenge-id", identity=google_identity())
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text


# --- No-account / ambiguous -----------------------------------------------

def test_unverified_email_cannot_auto_link_falls_through_to_no_account(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_google_verify(
        client, challenge_id,
        identity=google_identity(email="parent1@example.com", email_verified=False),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"verified": True, "has_account": False}
    assert count_auth_identities("google") == 0


def test_no_account_returns_verified_no_session_creates_nothing(client):
    challenge_id = issue_challenge(client)
    r = call_google_verify(client, challenge_id, identity=google_identity(email="nobody@example.com"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["has_account"] is False
    assert "session_token" not in body
    assert count_auth_identities("google") == 0


def test_ambiguous_owner_returns_409_generic_message_creates_nothing(client):
    parent_id = make_parent("dual@example.com")
    other_parent_id = make_parent("someone-else@example.com")
    other_athlete_id = make_athlete(other_parent_id, "Alex")
    make_athlete_login(other_athlete_id, "dual@example.com")

    challenge_id = issue_challenge(client)
    r = call_google_verify(client, challenge_id, identity=google_identity(email="dual@example.com"))

    assert r.status_code == 409, r.text
    assert r.json() == {"detail": "Something went wrong. Please contact support."}
    body_text = r.text.lower()
    assert "parent" not in body_text
    assert "athlete" not in body_text
    assert "dual@example.com" not in body_text
    assert str(parent_id) not in r.text
    assert str(other_parent_id) not in r.text
    assert str(other_athlete_id) not in r.text
    assert count_auth_identities("google") == 0


# --- Owner already linked to a different subject (Phase 6 corrective pass) -

def test_owner_already_linked_to_different_google_subject_returns_409_generic_message(client):
    """Parent owner case. A parent already has an existing (google,
    subject_A) mapping. A NEW verified Google identity for subject_B, whose
    email resolves to that SAME parent, must fail closed with the same
    generic 409 as the ambiguous-identity case above -- never a raw 500,
    never a new identity row, never a session."""
    parent_id = make_parent("parent1@example.com")
    challenge_id_1 = issue_challenge(client)
    first = call_google_verify(
        client, challenge_id_1,
        identity=google_identity(sub="google-subject-A", email="parent1@example.com"),
    )
    assert first.status_code == 200, first.text

    challenge_id_2 = issue_challenge(client)
    r = call_google_verify(
        client, challenge_id_2,
        identity=google_identity(sub="google-subject-B", email="parent1@example.com"),
    )

    assert r.status_code == 409, r.text
    assert r.json() == {"detail": "Something went wrong. Please contact support."}
    assert "session_token" not in r.text
    body_text = r.text.lower()
    assert "parent" not in body_text
    assert "google-subject" not in body_text
    assert str(parent_id) not in r.text
    # Only the original mapping exists -- subject_B's insert never landed.
    assert count_auth_identities("google") == 1
    assert get_auth_identity("google", "google-subject-B") is None


def test_owner_already_linked_to_different_google_subject_athlete_case_returns_409(client):
    """Same conflict, athlete owner case."""
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")

    challenge_id_1 = issue_challenge(client)
    first = call_google_verify(
        client, challenge_id_1,
        identity=google_identity(sub="google-athlete-subject-A", email="alex@example.com"),
    )
    assert first.status_code == 200, first.text

    challenge_id_2 = issue_challenge(client)
    r = call_google_verify(
        client, challenge_id_2,
        identity=google_identity(sub="google-athlete-subject-B", email="alex@example.com"),
    )

    assert r.status_code == 409, r.text
    assert r.json() == {"detail": "Something went wrong. Please contact support."}
    assert "session_token" not in r.text
    assert count_auth_identities("google") == 1
    assert get_auth_identity("google", "google-athlete-subject-B") is None


# --- Adversarial -----------------------------------------------------------

def test_no_client_supplied_email_alone_produces_a_session(client):
    # Junk request with no valid challenge_id/id_token at all -- proves a
    # bare client-asserted email can never itself mint a session.
    r = client.post(
        "/api/auth/google/verify",
        json={"challenge_id": "junk", "id_token": "junk-not-a-real-token"},
    )
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text


def test_provider_verification_happens_before_resolve_identity(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    with patch("api.routes.auth.resolve_identity") as mock_resolve:
        r = call_google_verify(client, challenge_id, error=GoogleVerificationError("bad"))
    assert r.status_code == 401, r.text
    mock_resolve.assert_not_called()
