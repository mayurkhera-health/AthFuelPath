"""
POST /api/auth/apple/link-existing (auth v2.1 Phase 6, plan A.8/C.4).

Completes the Hide-My-Email path: a verified Apple identity with a
successfully-captured encrypted refresh token (already sitting in
apple_pending_links, created by apple/verify) gets bound to an EXISTING
parent account only after that parent proves ownership of their email via a
genuine, freshly-verified OTP -- typing an email alone can never link
anything. Explicitly parent-scoped: an athlete has no independent
OTP-receiving email channel in this architecture.

Transactional: pending-link consumption + the new auth_identities row + the
new apple_provider_credentials row (copied straight from the pending
record -- NO second exchange) all happen in one transaction, committed or
rolled back together.
"""

import base64
import hashlib
import os

os.environ["DB_PATH"] = ":memory:"

from datetime import datetime, timedelta
from unittest.mock import patch

import psycopg
import pytest
from fastapi.testclient import TestClient

from fastapi import HTTPException

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.routes import auth as auth_routes
from api.routes.auth import _consume_pending_link_and_create_apple_identity
from api.services.provider_credential_crypto import encrypt_refresh_token, decrypt_refresh_token
from api.services.session_auth import verify_session_token

TEST_KEY_B64 = base64.b64encode(b"0" * 32).decode()


@pytest.fixture(autouse=True)
def _provider_credential_key(monkeypatch):
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", TEST_KEY_B64)


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


def seed_pending_link(
    *, provider_subject="apple-pending-sub", email_from_token="privaterelay@example.com",
    email_verified_from_token=True, raw_refresh_token="raw-refresh-token-pending",
    expires_in_minutes=10, consumed_at=None, pending_link_id="test-pending-link-id",
):
    ciphertext, nonce = encrypt_refresh_token(raw_refresh_token)
    conn = get_conn()
    try:
        # expires_at computed via Postgres's own now() + interval, not a
        # Python-computed isoformat() string -- expires_at is TIMESTAMPTZ and
        # this session's timezone is not guaranteed to be UTC, so a naive
        # Python datetime would be silently (mis)interpreted in that session
        # timezone instead of UTC.
        conn.execute(
            "INSERT INTO apple_pending_links "
            "(pending_link_id, provider_subject, email_from_token, email_verified_from_token, "
            "encrypted_refresh_token, encryption_nonce, expires_at, consumed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s), %s)",
            (
                pending_link_id, provider_subject, email_from_token, email_verified_from_token,
                ciphertext, nonce, expires_in_minutes, consumed_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return pending_link_id


def get_pending_link(pending_link_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM apple_pending_links WHERE pending_link_id = %s", (pending_link_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_auth_identities(provider="apple"):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM auth_identities WHERE provider = %s", (provider,)
        ).fetchone()["c"]
    finally:
        conn.close()


def get_auth_identity(provider_subject):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM auth_identities WHERE provider = 'apple' AND provider_subject = %s",
            (provider_subject,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_apple_credentials():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM apple_provider_credentials").fetchone()["c"]
    finally:
        conn.close()


def get_credential_for_auth_identity(auth_identity_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM apple_provider_credentials WHERE auth_identity_id = %s", (auth_identity_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def call_link_existing(client, *, pending_link_id, email, code):
    return client.post(
        "/api/auth/apple/link-existing",
        json={"pending_link_id": pending_link_id, "email": email, "code": code},
    )


# --- Happy path --------------------------------------------------------

def test_successful_link_creates_auth_identity_and_copies_credential_without_re_exchange(client):
    parent_id = make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(
        provider_subject="link-sub-1", raw_refresh_token="raw-token-for-link-sub-1",
    )
    insert_otp_row("parent1@example.com", "123456")

    exchange_target = "api.services.apple_auth.exchange_authorization_code_for_refresh_token"
    with patch(exchange_target) as mock_exchange:
        r = call_link_existing(
            client, pending_link_id=pending_link_id, email="parent1@example.com", code="123456",
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["id"] == parent_id
    assert body["session_token"]
    mock_exchange.assert_not_called()  # no second exchange -- copied straight from the pending row

    assert count_auth_identities("apple") == 1
    identity_row = get_auth_identity("link-sub-1")
    assert identity_row["parent_id"] == parent_id

    assert count_apple_credentials() == 1
    credential = get_credential_for_auth_identity(identity_row["id"])
    plaintext = decrypt_refresh_token(
        bytes(credential["encrypted_refresh_token"]), bytes(credential["encryption_nonce"]),
    )
    assert plaintext == "raw-token-for-link-sub-1"


def test_issued_session_token_is_valid_against_require_session(client):
    parent_id = make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="link-sub-session")
    insert_otp_row("parent1@example.com", "654321")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="654321")
    token = r.json()["session_token"]
    identity = verify_session_token(token)
    assert identity["role"] == "parent"
    assert identity["parent_id"] == parent_id


# --- OTP required -----------------------------------------------------

def test_missing_otp_never_sent_returns_401_no_session_no_linkage(client):
    make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="no-otp-sub")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="000000")
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text
    assert count_auth_identities("apple") == 0
    pending = get_pending_link(pending_link_id)
    assert pending["consumed_at"] is None


def test_wrong_otp_code_returns_401_pending_link_left_unconsumed_and_retriable(client):
    make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="wrong-otp-sub")
    insert_otp_row("parent1@example.com", "123456")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="000000")
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text
    pending = get_pending_link(pending_link_id)
    assert pending["consumed_at"] is None

    # Retriable: the correct code still works afterward.
    r2 = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="123456")
    assert r2.status_code == 200, r2.text


def test_typing_email_alone_with_no_valid_otp_can_never_link_anything(client):
    make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="no-real-otp-sub")
    # No insert_otp_row() call at all -- no code was ever issued.
    r = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="123456")
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text
    assert count_auth_identities("apple") == 0


# --- Pending-link expiry/consumption -------------------------------------

def test_expired_pending_link_cannot_be_used(client):
    make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="expired-sub", expires_in_minutes=-1)
    insert_otp_row("parent1@example.com", "123456")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="123456")
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text
    assert count_auth_identities("apple") == 0


def test_unknown_pending_link_id_returns_401(client):
    make_parent("parent1@example.com")
    insert_otp_row("parent1@example.com", "123456")
    r = call_link_existing(client, pending_link_id="does-not-exist", email="parent1@example.com", code="123456")
    assert r.status_code == 401, r.text


def test_already_consumed_pending_link_cannot_be_reused(client):
    parent_id = make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="already-consumed-sub")
    insert_otp_row("parent1@example.com", "111111")
    first = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="111111")
    assert first.status_code == 200, first.text

    insert_otp_row("parent1@example.com", "222222")
    second = call_link_existing(client, pending_link_id=pending_link_id, email="parent1@example.com", code="222222")
    assert second.status_code == 401, second.text
    assert "session_token" not in second.text
    # Still exactly one identity row from the first, successful call.
    assert count_auth_identities("apple") == 1


def test_pending_link_that_expires_between_lookup_and_final_consume_is_rejected(client):
    """auth v2.1 Phase 6 corrective pass (external review): the final atomic
    UPDATE in _consume_pending_link_and_create_apple_identity must re-check
    expires_at, not just consumed_at. Proves the actual race, not just an
    already-expired row: the pending link is valid (not expired, not
    consumed) at apple_link_existing's own initial SELECT, then is forced to
    expire in between that SELECT and the final consuming UPDATE, by
    interleaving through _resolve_exactly_one_parent_owner (the one call
    that runs between those two points in the real endpoint)."""
    make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="race-expiry-sub")
    insert_otp_row("parent1@example.com", "123456")

    real_resolve = auth_routes._resolve_exactly_one_parent_owner

    def expire_row_then_resolve(email, conn=None):
        # At this point apple_link_existing's initial SELECT (WHERE
        # consumed_at IS NULL AND expires_at > now()) has already run and
        # found the row valid. Force it to expire right here, before the
        # final atomic UPDATE runs.
        conn.execute(
            "UPDATE apple_pending_links SET expires_at = now() - interval '1 minute' "
            "WHERE pending_link_id = %s",
            (pending_link_id,),
        )
        return real_resolve(email, conn=conn)

    with patch.object(
        auth_routes, "_resolve_exactly_one_parent_owner", side_effect=expire_row_then_resolve,
    ):
        r = call_link_existing(
            client, pending_link_id=pending_link_id, email="parent1@example.com", code="123456",
        )

    assert r.status_code == 401, r.text
    assert r.json() == {
        "detail": "This sign-in attempt has expired. Please try Continue with Apple again."
    }
    assert "session_token" not in r.text
    assert count_auth_identities("apple") == 0
    assert count_apple_credentials() == 0
    pending = get_pending_link(pending_link_id)
    # Rejected by the WHERE clause -- never actually consumed.
    assert pending["consumed_at"] is None


def test_consume_pending_link_where_clause_rejects_a_row_expired_after_being_read(client):
    """Isolates the WHERE clause itself (not the route, not the earlier
    SELECT): a pending-link dict that looks valid (as if just read) is
    passed directly to _consume_pending_link_and_create_apple_identity, but
    the underlying row's expires_at has already passed by the time this
    call's own UPDATE runs. Proves expires_at > now() in that UPDATE -- not
    some earlier check -- is what causes the rejection."""
    parent_id = make_parent("parent2@example.com")
    pending_link_id = seed_pending_link(provider_subject="direct-race-sub")

    conn = get_conn()
    try:
        pending_d = conn.execute(
            "SELECT * FROM apple_pending_links WHERE pending_link_id = %s", (pending_link_id,)
        ).fetchone()
        pending_d = dict(pending_d)
        assert pending_d["consumed_at"] is None  # still looks valid to the caller

        # Now expire it out from under the caller, simulating the row
        # expiring between when it was read and this consume call.
        conn.execute(
            "UPDATE apple_pending_links SET expires_at = now() - interval '1 minute' "
            "WHERE pending_link_id = %s",
            (pending_link_id,),
        )
        conn.commit()

        with pytest.raises(HTTPException) as exc_info:
            _consume_pending_link_and_create_apple_identity(conn, pending_d, parent_id)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == (
            "This sign-in attempt has expired. Please try Continue with Apple again."
        )
    finally:
        conn.close()

    assert count_auth_identities("apple") == 0
    assert count_apple_credentials() == 0


# --- Email resolution ----------------------------------------------------

_LINK_EXISTING_401_MESSAGE = "We couldn't verify that account. Please check the email and try again."


def test_no_matching_parent_account_returns_401_generic_message(client):
    pending_link_id = seed_pending_link(provider_subject="no-parent-sub")
    insert_otp_row("nobody@example.com", "123456")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="nobody@example.com", code="123456")
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": _LINK_EXISTING_401_MESSAGE}
    assert count_auth_identities("apple") == 0


def test_athlete_only_email_is_rejected_this_flow_is_parent_scoped(client):
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")
    pending_link_id = seed_pending_link(provider_subject="athlete-email-sub")
    insert_otp_row("alex@example.com", "123456")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="alex@example.com", code="123456")
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": _LINK_EXISTING_401_MESSAGE}
    assert count_auth_identities("apple") == 0


def test_ambiguous_email_returns_401_generic_message(client):
    make_parent("dual@example.com")
    other_parent_id = make_parent("someone-else@example.com")
    other_athlete_id = make_athlete(other_parent_id, "Alex")
    make_athlete_login(other_athlete_id, "dual@example.com")
    pending_link_id = seed_pending_link(provider_subject="ambiguous-link-sub")
    insert_otp_row("dual@example.com", "123456")
    r = call_link_existing(client, pending_link_id=pending_link_id, email="dual@example.com", code="123456")
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": _LINK_EXISTING_401_MESSAGE}
    assert count_auth_identities("apple") == 0


# --- Transactional fail-closed --------------------------------------------

def test_transactional_failure_rolls_back_everything_pending_link_stays_retriable(client):
    """Simulates the apple_provider_credentials INSERT failing (a genuine
    UniqueViolation) inside _consume_pending_link_and_create_apple_identity's
    single transaction -- proves the pending-link consumption, the new
    auth_identities row, AND the new apple_provider_credentials row are all
    rolled back together, not left in a partial state."""
    make_parent("parent1@example.com")
    pending_link_id = seed_pending_link(provider_subject="tx-fail-sub")
    insert_otp_row("parent1@example.com", "123456")

    real_execute = psycopg.Connection.execute

    def flaky_execute(self, query, *args, **kwargs):
        text = str(query)
        if "INSERT INTO apple_provider_credentials" in text:
            raise psycopg.errors.UniqueViolation("simulated conflict on apple_provider_credentials")
        return real_execute(self, query, *args, **kwargs)

    with patch.object(psycopg.Connection, "execute", flaky_execute):
        r = call_link_existing(
            client, pending_link_id=pending_link_id, email="parent1@example.com", code="123456",
        )

    assert r.status_code == 409, r.text
    assert "session_token" not in r.text
    assert count_auth_identities("apple") == 0
    assert count_apple_credentials() == 0
    pending = get_pending_link(pending_link_id)
    # Rolled back -- the pending link's own consumption was undone too.
    assert pending["consumed_at"] is None
