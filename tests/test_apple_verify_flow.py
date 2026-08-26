"""
POST /api/auth/apple/verify (auth v2.1 Phase 6, plan A.8/C.3) — THE most
critical part of Phase 6.

Apple NEVER calls resolve_identity() — its auto-link INSERT would create an
auth_identities mapping before any Apple credential exists, which is exactly
the bug the plan's round-4 correction closed. Instead apple_verify:
  - Case A: a direct, read-only exact-match SELECT on (provider='apple',
    provider_subject).
  - Case B: the read-only _resolve_exactly_one_owner() building block.
Every first-time write path performs its mandatory synchronous
authorization_code -> refresh_token exchange BEFORE any auth_identities or
apple_pending_links row is created, and Case B's two inserts (auth_identities
+ apple_provider_credentials) happen in ONE transaction, committed or rolled
back together.

These tests mock verify_apple_identity_token and
exchange_authorization_code_for_refresh_token at the route-module level
(already tested against real crypto/HTTP semantics in tests/test_apple_auth.py)
to exercise the ROUTE's orchestration logic — challenge consumption,
Case A/B branching, atomicity, and session minting.
"""

import base64
import os

os.environ["DB_PATH"] = ":memory:"

from datetime import datetime
from unittest.mock import patch

import psycopg
import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services.apple_auth import AppleVerificationError, VerifiedAppleIdentity
from api.services.provider_credential_crypto import decrypt_refresh_token
from api.services.session_auth import verify_session_token

APPLE_VERIFY_MSG = "Apple sign-in could not be verified. Please try again."
APPLE_EXCHANGE_MSG = "Apple sign-in could not be completed. Please try again."
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


def seed_apple_identity(*, parent_id=None, athlete_id=None, provider_subject):
    """Directly inserts an auth_identities row for provider='apple' —
    bypasses apple_verify's own atomic orchestration entirely, used only to
    put the DB into a specific pre-existing state for a test."""
    conn = get_conn()
    try:
        row = conn.execute(
            "INSERT INTO auth_identities "
            "(provider, provider_subject, parent_id, athlete_id, email, email_verified) "
            "VALUES ('apple', %s, %s, %s, NULL, FALSE) RETURNING id",
            (provider_subject, parent_id, athlete_id),
        ).fetchone()
        conn.commit()
        return row["id"]
    finally:
        conn.close()


def seed_apple_credential(auth_identity_id, ciphertext=b"seed-ciphertext", nonce=b"seed-nonce12"):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO apple_provider_credentials "
            "(auth_identity_id, encrypted_refresh_token, encryption_nonce) VALUES (%s, %s, %s)",
            (auth_identity_id, ciphertext, nonce),
        )
        conn.commit()
    finally:
        conn.close()


def count_auth_identities(provider="apple", provider_subject=None):
    conn = get_conn()
    try:
        if provider_subject is not None:
            return conn.execute(
                "SELECT COUNT(*) AS c FROM auth_identities WHERE provider = %s AND provider_subject = %s",
                (provider, provider_subject),
            ).fetchone()["c"]
        return conn.execute(
            "SELECT COUNT(*) AS c FROM auth_identities WHERE provider = %s", (provider,)
        ).fetchone()["c"]
    finally:
        conn.close()


def count_apple_credentials():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM apple_provider_credentials").fetchone()["c"]
    finally:
        conn.close()


def count_pending_links():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM apple_pending_links").fetchone()["c"]
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


def get_credential_for_auth_identity(auth_identity_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM apple_provider_credentials WHERE auth_identity_id = %s", (auth_identity_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_pending_link_by_subject(provider_subject):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM apple_pending_links WHERE provider_subject = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (provider_subject,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def issue_challenge(client, provider="apple"):
    r = client.post("/api/auth/provider/challenge", json={"provider": provider})
    assert r.status_code == 200, r.text
    return r.json()["challenge_id"]


def apple_identity(sub="apple-sub-1", email="parent1@example.com", email_verified=True):
    return VerifiedAppleIdentity(sub=sub, email=email, email_verified=email_verified)


def call_apple_verify(client, challenge_id, *, identity=None, verify_error=None,
                       authorization_code="fake-auth-code", exchange_return="raw-refresh-token-abc",
                       exchange_error=None):
    verify_target = "api.routes.auth.verify_apple_identity_token"
    exchange_target = "api.routes.auth.exchange_authorization_code_for_refresh_token"

    verify_patch = (
        patch(verify_target, side_effect=verify_error) if verify_error is not None
        else patch(verify_target, return_value=identity)
    )
    exchange_patch = (
        patch(exchange_target, side_effect=exchange_error) if exchange_error is not None
        else patch(exchange_target, return_value=exchange_return)
    )

    body = {"challenge_id": challenge_id, "identity_token": "fake-identity-token"}
    if authorization_code is not None:
        body["authorization_code"] = authorization_code

    with verify_patch, exchange_patch:
        return client.post("/api/auth/apple/verify", json=body)


# ============================================================================
# The 6 required critical atomicity tests (plan Part H, 4th-round correction)
# ============================================================================

def test_direct_first_time_apple_exchange_failure_creates_zero_apple_auth_identity_rows(client):
    """Case B, exactly-one-owner match, mocked exchange raises
    AppleVerificationError -> 502, and NOT ONE auth_identities row for
    provider='apple' exists afterward -- proves the exchange-before-mapping-
    creation ordering."""
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        identity=apple_identity(sub="never-linked-sub", email="parent1@example.com"),
        exchange_error=AppleVerificationError("exchange failed"),
    )
    assert r.status_code == 502, r.text
    assert r.json() == {"detail": APPLE_EXCHANGE_MSG}
    assert count_auth_identities("apple") == 0


def test_missing_authorization_code_on_hide_my_email_path_creates_zero_pending_link_rows(client):
    """Case B, NoExistingAccount, no authorization_code in the request ->
    502, and apple_pending_links stays completely empty -- proves the
    Hide-My-Email path never creates a credential-less pending link."""
    # No make_parent() call -- this Apple identity has no matching owner.
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        identity=apple_identity(sub="no-owner-sub", email="nobody@example.com"),
        authorization_code=None,
    )
    assert r.status_code == 502, r.text
    assert r.json() == {"detail": APPLE_EXCHANGE_MSG}
    assert count_pending_links() == 0


def test_successful_direct_first_apple_link_creates_auth_identity_and_credential_atomically(client):
    """Case B, exactly-one-owner, successful mocked exchange -> exactly one
    new auth_identities row AND exactly one new apple_provider_credentials
    row, correctly cross-referenced, session minted."""
    parent_id = make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        identity=apple_identity(sub="first-link-sub", email="parent1@example.com"),
        exchange_return="raw-refresh-token-first-link",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["id"] == parent_id
    assert body["session_token"]

    assert count_auth_identities("apple", "first-link-sub") == 1
    identity_row = get_auth_identity("first-link-sub")
    assert identity_row["parent_id"] == parent_id

    assert count_apple_credentials() == 1
    credential_row = get_credential_for_auth_identity(identity_row["id"])
    assert credential_row is not None
    assert bytes(credential_row["encrypted_refresh_token"])
    assert bytes(credential_row["encryption_nonce"])
    plaintext = decrypt_refresh_token(
        bytes(credential_row["encrypted_refresh_token"]), bytes(credential_row["encryption_nonce"])
    )
    assert plaintext == "raw-refresh-token-first-link"


def test_credential_db_insert_failure_rolls_back_newly_created_apple_auth_identity(client):
    """Simulates the apple_provider_credentials INSERT failing (a genuine
    UniqueViolation) after the auth_identities INSERT would otherwise have
    succeeded, within _create_apple_identity_with_credential's single
    transaction -- proves the whole transaction rolls back, not just a
    sequential-with-a-hope pair of statements."""
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)

    real_execute = psycopg.Connection.execute

    def flaky_execute(self, query, *args, **kwargs):
        text = str(query)
        if "INSERT INTO apple_provider_credentials" in text:
            raise psycopg.errors.UniqueViolation("simulated conflict on apple_provider_credentials")
        return real_execute(self, query, *args, **kwargs)

    with patch.object(psycopg.Connection, "execute", flaky_execute):
        r = call_apple_verify(
            client, challenge_id,
            identity=apple_identity(sub="rollback-sub", email="parent1@example.com"),
        )

    assert r.status_code == 409, r.text
    assert "session_token" not in r.text
    assert count_auth_identities("apple", "rollback-sub") == 0
    assert count_apple_credentials() == 0


def test_existing_exact_apple_identity_with_missing_credential_does_not_mint_session_until_credential_capture_succeeds(client):
    """Case A, missing-credential branch: seed an auth_identities row for
    (apple, sub) with NO apple_provider_credentials row. Calling apple_verify
    with no authorization_code -> 502, no session, existing row untouched.
    Retrying with a valid authorization_code and a mocked-successful
    exchange -> credential now created, session IS minted."""
    parent_id = make_parent("parent1@example.com")
    auth_identity_id = seed_apple_identity(parent_id=parent_id, provider_subject="defensive-coverage-sub")
    assert count_apple_credentials() == 0

    # First attempt: no authorization_code.
    challenge_id_1 = issue_challenge(client)
    r1 = call_apple_verify(
        client, challenge_id_1,
        identity=apple_identity(sub="defensive-coverage-sub", email="parent1@example.com"),
        authorization_code=None,
    )
    assert r1.status_code == 502, r1.text
    assert "session_token" not in r1.text
    assert count_apple_credentials() == 0
    untouched = get_auth_identity("defensive-coverage-sub")
    assert untouched["id"] == auth_identity_id
    assert untouched["parent_id"] == parent_id

    # Retry: valid authorization_code, successful exchange.
    challenge_id_2 = issue_challenge(client)
    r2 = call_apple_verify(
        client, challenge_id_2,
        identity=apple_identity(sub="defensive-coverage-sub", email="parent1@example.com"),
        exchange_return="raw-refresh-token-retry",
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["role"] == "parent"
    assert body["session_token"]
    assert count_apple_credentials() == 1
    credential_row = get_credential_for_auth_identity(auth_identity_id)
    assert credential_row is not None
    # Still exactly the one identity row -- no second one was created.
    assert count_auth_identities("apple", "defensive-coverage-sub") == 1


def test_concurrent_credential_store_race_is_treated_as_benign_not_a_500(client):
    """Case A's missing-credential branch: _has_stored_apple_credential's
    check and _store_apple_credential's insert each open their own separate
    connection with no shared transaction/locking between them (TOCTOU) --
    a genuine gap given apple_provider_credentials.auth_identity_id is
    NOT NULL UNIQUE. Two concurrent requests for the same not-yet-stored
    Apple identity (e.g. a client retry-on-timeout) can both pass the check,
    both perform the external exchange, and then race on the insert.
    Simulates this request LOSING that race -- its own insert hits a
    genuine UniqueViolation because another concurrent request's insert
    already won. That must be treated as benign, not an uncaught 500: this
    request still succeeds with a session minted, exactly as if its own
    insert had gone through."""
    parent_id = make_parent("parent1@example.com")
    auth_identity_id = seed_apple_identity(parent_id=parent_id, provider_subject="race-sub")
    assert count_apple_credentials() == 0

    real_execute = psycopg.Connection.execute

    def flaky_execute(self, query, *args, **kwargs):
        text = str(query)
        if "INSERT INTO apple_provider_credentials" in text:
            raise psycopg.errors.UniqueViolation(
                "simulated concurrent request already stored this credential first"
            )
        return real_execute(self, query, *args, **kwargs)

    challenge_id = issue_challenge(client)
    with patch.object(psycopg.Connection, "execute", flaky_execute):
        r = call_apple_verify(
            client, challenge_id,
            identity=apple_identity(sub="race-sub", email="parent1@example.com"),
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["id"] == parent_id
    assert body["session_token"]
    # Still exactly the one identity row -- no second one was created, and
    # this request never persisted its own credential (the simulated
    # concurrent winner's row is what would exist in a real race).
    assert count_auth_identities("apple", "race-sub") == 1
    untouched = get_auth_identity("race-sub")
    assert untouched["id"] == auth_identity_id


def test_successful_pending_link_creation_always_contains_encrypted_credential_material(client):
    """Hide-My-Email path, successful mocked exchange -> the resulting
    apple_pending_links row's encrypted_refresh_token/encryption_nonce are
    both non-null and non-empty IMMEDIATELY upon creation."""
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        identity=apple_identity(sub="hide-my-email-sub", email="privaterelay@privaterelay.appleid.com"),
        exchange_return="raw-refresh-token-relay",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "verified": True, "has_account": False,
        "apple_linkable": True, "pending_link_id": body["pending_link_id"],
    }
    assert body["pending_link_id"]

    pending = get_pending_link_by_subject("hide-my-email-sub")
    assert pending is not None
    assert pending["encrypted_refresh_token"] is not None
    assert bytes(pending["encrypted_refresh_token"])
    assert pending["encryption_nonce"] is not None
    assert bytes(pending["encryption_nonce"])
    plaintext = decrypt_refresh_token(
        bytes(pending["encrypted_refresh_token"]), bytes(pending["encryption_nonce"])
    )
    assert plaintext == "raw-refresh-token-relay"


# ============================================================================
# Additional required coverage (Part H)
# ============================================================================

def test_apple_verification_error_returns_401_generic_message(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_apple_verify(client, challenge_id, verify_error=AppleVerificationError("bad token"))
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": APPLE_VERIFY_MSG}
    assert "session_token" not in r.text


def test_apple_verification_error_401_response_is_byte_identical_with_empirical_logging_flag_on(client, monkeypatch):
    """Gate 3 follow-up (this task): apple_verify now also does a best-effort
    observed_alg log on this same failure path when
    PROVIDER_AUTH_EMPIRICAL_LOGGING is on. That log line must be purely
    additive -- explicitly confirm the 401 response (status code + full JSON
    body) is identical whether the flag is off or on, i.e. the new logging
    never alters what the caller receives."""
    make_parent("parent1@example.com")

    monkeypatch.delenv("PROVIDER_AUTH_EMPIRICAL_LOGGING", raising=False)
    challenge_id_off = issue_challenge(client)
    r_off = call_apple_verify(client, challenge_id_off, verify_error=AppleVerificationError("bad token"))

    monkeypatch.setenv("PROVIDER_AUTH_EMPIRICAL_LOGGING", "1")
    challenge_id_on = issue_challenge(client)
    r_on = call_apple_verify(client, challenge_id_on, verify_error=AppleVerificationError("bad token"))

    assert r_off.status_code == r_on.status_code == 401
    assert r_off.json() == r_on.json() == {"detail": APPLE_VERIFY_MSG}
    assert r_off.headers["content-type"] == r_on.headers["content-type"]


def test_consumed_challenge_cannot_authenticate_a_second_request(client):
    parent_id = make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    first = call_apple_verify(
        client, challenge_id, identity=apple_identity(sub="replay-sub", email="parent1@example.com"),
    )
    assert first.status_code == 200, first.text

    second = call_apple_verify(
        client, challenge_id, identity=apple_identity(sub="replay-sub", email="parent1@example.com"),
    )
    assert second.status_code == 401, second.text
    assert "session_token" not in second.text
    # Only the first call's identity/credential were ever created.
    assert count_auth_identities("apple", "replay-sub") == 1


def test_challenge_for_wrong_provider_is_rejected(client):
    make_parent("parent1@example.com")
    google_challenge_id = issue_challenge(client, provider="google")
    r = call_apple_verify(client, google_challenge_id, identity=apple_identity())
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text


def test_subsequent_apple_login_with_existing_credential_does_not_re_exchange_even_with_fresh_code(client):
    """Once an Apple identity has a stored credential, no exchange is
    attempted at all -- regardless of whether authorization_code is present
    in the request."""
    parent_id = make_parent("parent1@example.com")
    auth_identity_id = seed_apple_identity(parent_id=parent_id, provider_subject="already-linked-sub")
    seed_apple_credential(auth_identity_id)

    challenge_id = issue_challenge(client)
    exchange_target = "api.routes.auth.exchange_authorization_code_for_refresh_token"
    with patch(exchange_target) as mock_exchange:
        r = call_apple_verify(
            client, challenge_id,
            identity=apple_identity(sub="already-linked-sub", email="parent1@example.com"),
            authorization_code="a-fresh-code-that-should-be-ignored",
        )
    assert r.status_code == 200, r.text
    assert r.json()["session_token"]
    mock_exchange.assert_not_called()
    # No second credential row was created.
    assert count_apple_credentials() == 1


def test_ambiguous_owner_returns_409_before_any_exchange_is_attempted(client):
    """Checked BEFORE the exchange -- no reason to spend an Apple API
    round-trip on a request that 409s regardless."""
    make_parent("dual@example.com")
    other_parent_id = make_parent("someone-else@example.com")
    other_athlete_id = make_athlete(other_parent_id, "Alex")
    make_athlete_login(other_athlete_id, "dual@example.com")

    challenge_id = issue_challenge(client)
    exchange_target = "api.routes.auth.exchange_authorization_code_for_refresh_token"
    with patch(exchange_target) as mock_exchange:
        r = call_apple_verify(
            client, challenge_id, identity=apple_identity(sub="ambiguous-sub", email="dual@example.com"),
        )
    assert r.status_code == 409, r.text
    assert r.json() == {"detail": "Something went wrong. Please contact support."}
    mock_exchange.assert_not_called()
    assert count_auth_identities("apple") == 0
    assert count_pending_links() == 0


def test_no_account_and_unverified_email_falls_through_to_hide_my_email_path(client):
    """An Apple email that comes back unverified from the token still routes
    through the Hide-My-Email path (mirrors resolve_identity()'s own
    email_verified gating) rather than silently auto-linking."""
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        identity=apple_identity(sub="unverified-email-sub", email="parent1@example.com", email_verified=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_account"] is False
    assert body["apple_linkable"] is True
    assert count_auth_identities("apple") == 0


def test_full_name_is_never_persisted_anywhere_in_the_response_or_db(client):
    # VerifiedAppleIdentity structurally has no fullName field at all --
    # this proves apple_verify's response never leaks one even indirectly.
    # parents.full_name legitimately appears as the "parent" object's
    # full_name key (the resolved parent's own name) -- what must never
    # appear is an Apple-supplied fullName under any key/casing.
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        identity=apple_identity(sub="no-name-sub", email="parent1@example.com"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # "fullName" (Apple's camelCase field) must never appear as a key
    # anywhere in the response, at any nesting level -- only the
    # legitimate, pre-existing "full_name" key (the resolved parent's own
    # stored name) is allowed to appear.
    assert "fullName" not in body
    assert "fullName" not in body["parent"]
    assert body["parent"]["full_name"] == "Test Parent"


def test_no_client_supplied_email_alone_produces_a_session(client):
    r = client.post(
        "/api/auth/apple/verify",
        json={"challenge_id": "junk", "identity_token": "junk-not-a-real-token"},
    )
    assert r.status_code == 401, r.text
    assert "session_token" not in r.text


def test_provider_verification_happens_before_any_owner_resolution(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    with patch("api.routes.auth._resolve_exactly_one_owner") as mock_resolve:
        r = call_apple_verify(client, challenge_id, verify_error=AppleVerificationError("bad"))
    assert r.status_code == 401, r.text
    mock_resolve.assert_not_called()


def test_apple_verify_never_calls_resolve_identity():
    """Structural guard, not just a behavioral one: apple_verify's own
    compiled bytecode must never reference the resolve_identity name at all
    (A.8's load-bearing design constraint) -- checked via co_names (actual
    identifier usage) rather than source text, since the function's own
    docstring legitimately mentions "resolve_identity()" in prose."""
    from api.routes.auth import apple_verify
    assert "resolve_identity" not in apple_verify.__code__.co_names


def test_issued_apple_session_token_is_valid_against_require_session(client):
    parent_id = make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id, identity=apple_identity(sub="valid-session-sub", email="parent1@example.com"),
    )
    token = r.json()["session_token"]
    identity = verify_session_token(token)
    assert identity["role"] == "parent"
    assert identity["parent_id"] == parent_id


# ============================================================================
# auth v2.1 Phase 6 corrective pass (external review) -- Correction 1:
# verify_apple_identity_token's own _apple_allowed_algorithms() raises a bare
# RuntimeError (not AppleVerificationError) when APPLE_ALLOWED_ALGORITHMS is
# unset -- a DEPLOYMENT config problem, not a bad sign-in attempt. Before
# this fix, `except AppleVerificationError:` alone let this propagate as a
# raw, unhandled 500. It must instead become a controlled, GENERIC response,
# distinct from the 401 verification-failed message (reusing that message
# would misrepresent a server config problem as a real auth decision).
# ============================================================================

APPLE_CONFIG_ERROR_MSG = "Apple sign-in is not available right now. Please try again later."


def test_apple_verify_config_runtime_error_returns_generic_503_not_401(client):
    challenge_id = issue_challenge(client)
    r = call_apple_verify(
        client, challenge_id,
        verify_error=RuntimeError(
            "APPLE_ALLOWED_ALGORITHMS env var is not set — the Apple identity-token "
            "signing algorithm has not been empirically confirmed"
        ),
    )
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": APPLE_CONFIG_ERROR_MSG}
    # Distinct from the 401 verification-failed message -- a config problem
    # must never be represented as a real authentication decision.
    assert r.json()["detail"] != APPLE_VERIFY_MSG
    # Never leaks which env var is missing or any other internal detail.
    assert "APPLE_ALLOWED_ALGORITHMS" not in r.text


def test_apple_verify_config_runtime_error_happens_before_any_owner_resolution(client):
    make_parent("parent1@example.com")
    challenge_id = issue_challenge(client)
    with patch("api.routes.auth._resolve_exactly_one_owner") as mock_resolve:
        r = call_apple_verify(client, challenge_id, verify_error=RuntimeError("config missing"))
    assert r.status_code == 503, r.text
    mock_resolve.assert_not_called()
