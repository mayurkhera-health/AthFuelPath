"""
auth v2.1 Phase 6 Gate 3 — flag-gated, dev-only empirical diagnostic logging
for POST /api/auth/google/verify and POST /api/auth/apple/verify.

This exists ONLY to let a person running this backend LOCALLY and driving a
real Google/Apple sign-in from a real iOS device read a few safe facts
(audience match, nonce-claim match, Apple's observed JWT alg, whether
Apple's authorization_code is actually present/usable) from backend logs
after the run. It is OFF by default, gated on the PROVIDER_AUTH_EMPIRICAL_LOGGING
env var (see api/routes/auth.py's _empirical_logging_enabled()), and must
NEVER change any response, DB write, control flow, or error path, and must
NEVER log the raw token, the raw nonce, the authorization code, the refresh
token, or any email/PII.

Three kinds of tests, per the task:
  (a) flag OFF -> zero new log records at all (provable inertness).
  (b) flag ON -> exactly the expected safe-fact log line(s) appear, with the
      right boolean values, for both Google and Apple success cases.
  (c) flag ON -> a genuine NEGATIVE assertion that none of the sensitive
      values used in that same request (raw identity token, raw nonce,
      authorization code, email) appear anywhere in the captured log text.
"""

import logging
import os

os.environ["DB_PATH"] = ":memory:"

from datetime import datetime
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services.google_auth import VerifiedGoogleIdentity
from api.services.apple_auth import VerifiedAppleIdentity, AppleVerificationError

FLAG = "PROVIDER_AUTH_EMPIRICAL_LOGGING"
AUTH_LOGGER = "api.routes.auth"
TEST_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="  # 32 zero bytes, base64
APPLE_VERIFY_FAILED_MESSAGE = "Apple sign-in could not be verified. Please try again."


@pytest.fixture(autouse=True)
def _flag_unset_by_default(monkeypatch):
    """Every test starts with the flag explicitly unset -- tests that want
    it on set it themselves via monkeypatch.setenv. Prevents cross-test
    pollution from whatever the real shell environment happens to have."""
    monkeypatch.delenv(FLAG, raising=False)


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


def issue_challenge(client, provider):
    r = client.post("/api/auth/provider/challenge", json={"provider": provider})
    assert r.status_code == 200, r.text
    return r.json()["challenge_id"], r.json()["nonce"]


def real_jwt_with_alg(alg="HS256", kid="empirical-test-kid"):
    """A syntactically real (but unverified/untrusted -- verify_apple_identity_token
    is mocked in these tests, its actual signature is never checked) JWT
    string, purely so the side-channel jwt.get_unverified_header() parse in
    apple_verify has real header bytes to read alg/kid from."""
    return jwt.encode({"sub": "irrelevant"}, "not-a-real-secret", algorithm=alg, headers={"kid": kid})


# ============================================================================
# (a) Flag OFF -> provably zero new log output / zero behavior change.
# ============================================================================

def test_flag_off_google_verify_emits_no_log_records(client, caplog):
    # Athlete role deliberately, not parent: a successful PARENT login also
    # schedules login_alerts.notify_login as a background task, which in
    # this local/no-AWS-creds test environment produces its OWN unrelated
    # log noise (a pre-existing, non-blocking side effect of that
    # completely separate feature) that would make a bare `caplog.records
    # == []` assertion flaky/misleading. The athlete branch has no such
    # side effect, so it's the clean way to prove THIS change adds zero log
    # output when the flag is off.
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")
    challenge_id, _nonce = issue_challenge(client, "google")
    identity = VerifiedGoogleIdentity(sub="g-sub-1", email="alex@example.com", email_verified=True)

    with caplog.at_level(logging.DEBUG, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_google_id_token", return_value=identity):
            r = client.post(
                "/api/auth/google/verify",
                json={"challenge_id": challenge_id, "id_token": "fake-id-token"},
            )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "athlete"
    assert caplog.records == []


def test_flag_off_apple_verify_direct_link_emits_no_log_records(client, caplog):
    """Case B, exactly-one-owner, direct link -- exercises BOTH log points
    (post-verify and post-exchange) with the flag off; neither may fire.
    Athlete role for the same reason as the Google test above (avoids the
    unrelated parent-only login-alert background-task log noise)."""
    parent_id = make_parent("parent1@example.com")
    athlete_id = make_athlete(parent_id, "Alex")
    make_athlete_login(athlete_id, "alex@example.com")
    challenge_id, _nonce = issue_challenge(client, "apple")
    identity = VerifiedAppleIdentity(sub="a-sub-1", email="alex@example.com", email_verified=True)

    with caplog.at_level(logging.DEBUG, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_apple_identity_token", return_value=identity), \
             patch("api.routes.auth.exchange_authorization_code_for_refresh_token", return_value="raw-refresh"):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": "fake-identity-token",
                    "authorization_code": "fake-auth-code",
                },
            )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "athlete"
    assert caplog.records == []


def test_flag_off_apple_verify_failure_emits_no_log_records(client, caplog):
    """Same inertness guarantee as the two tests above, extended to the
    failure path this task adds (Gate 3 follow-up): verify_apple_identity_token
    raising AppleVerificationError, flag off. Zero new log records, and the
    401 response is the plain pre-existing one -- proving the new
    best-effort log line genuinely does nothing when the flag is off, on
    this path too."""
    challenge_id, _nonce = issue_challenge(client, "apple")
    real_token = real_jwt_with_alg(alg="HS256", kid="failure-inertness-kid")

    with caplog.at_level(logging.DEBUG, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_apple_identity_token", side_effect=AppleVerificationError("bad token")):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": real_token,
                    "authorization_code": "fake-auth-code",
                },
            )
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": APPLE_VERIFY_FAILED_MESSAGE}
    assert caplog.records == []


def test_empirical_logging_enabled_helper_defaults_to_false(monkeypatch):
    from api.routes.auth import _empirical_logging_enabled
    monkeypatch.delenv(FLAG, raising=False)
    assert _empirical_logging_enabled() is False


# ============================================================================
# (b) Flag ON -> exactly the expected safe-fact log line(s), right values.
# ============================================================================

def test_flag_on_google_verify_logs_expected_facts(client, caplog, monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    make_parent("parent1@example.com")
    challenge_id, _nonce = issue_challenge(client, "google")
    identity = VerifiedGoogleIdentity(sub="g-sub-2", email="parent1@example.com", email_verified=True)

    with caplog.at_level(logging.INFO, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_google_id_token", return_value=identity):
            r = client.post(
                "/api/auth/google/verify",
                json={"challenge_id": challenge_id, "id_token": "fake-id-token"},
            )
    assert r.status_code == 200, r.text

    matches = [rec for rec in caplog.records if "provider_auth_empirical google_verify" in rec.getMessage()]
    assert len(matches) == 1, caplog.text
    msg = matches[0].getMessage()
    assert "observed_audience_matches_expected=True" in msg
    assert "email_verified=True" in msg


def test_flag_on_google_verify_logs_email_verified_false(client, caplog, monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    challenge_id, _nonce = issue_challenge(client, "google")
    identity = VerifiedGoogleIdentity(sub="g-sub-3", email="nobody@example.com", email_verified=False)

    with caplog.at_level(logging.INFO, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_google_id_token", return_value=identity):
            r = client.post(
                "/api/auth/google/verify",
                json={"challenge_id": challenge_id, "id_token": "fake-id-token"},
            )
    # No account, no resolve -- the diagnostic log still fires (it happens
    # BEFORE resolve_identity is even called), proving it's independent of
    # the downstream resolution outcome.
    assert r.status_code == 200, r.text
    assert r.json() == {"verified": True, "has_account": False}

    matches = [rec for rec in caplog.records if "provider_auth_empirical google_verify" in rec.getMessage()]
    assert len(matches) == 1, caplog.text
    assert "email_verified=False" in matches[0].getMessage()


def test_flag_on_apple_verify_logs_expected_facts_including_observed_alg(client, caplog, monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    make_parent("parent1@example.com")
    challenge_id, _nonce = issue_challenge(client, "apple")
    real_token = real_jwt_with_alg(alg="HS256", kid="empirical-test-kid")
    identity = VerifiedAppleIdentity(sub="a-sub-2", email="parent1@example.com", email_verified=True)

    with caplog.at_level(logging.INFO, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_apple_identity_token", return_value=identity), \
             patch("api.routes.auth.exchange_authorization_code_for_refresh_token", return_value="raw-refresh-xyz"):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": real_token,
                    "authorization_code": "fake-auth-code",
                },
            )
    assert r.status_code == 200, r.text

    verify_matches = [rec for rec in caplog.records if "provider_auth_empirical apple_verify" in rec.getMessage()]
    assert len(verify_matches) == 1, caplog.text
    verify_msg = verify_matches[0].getMessage()
    assert "observed_alg=HS256" in verify_msg
    assert "authorization_code_present=True" in verify_msg
    assert "nonce_comparison_result=True" in verify_msg

    exchange_matches = [rec for rec in caplog.records if "provider_auth_empirical apple_exchange" in rec.getMessage()]
    assert len(exchange_matches) == 1, caplog.text
    assert "authorization_code_present=True" in exchange_matches[0].getMessage()
    assert "exchange_succeeded=True" in exchange_matches[0].getMessage()


def test_flag_on_apple_verify_case_a_existing_credential_logs_verify_fact_but_not_exchange_fact(client, caplog, monkeypatch):
    """Case A with an already-stored credential never calls the exchange at
    all -- the second (post-exchange) log point must not fire, proving it's
    genuinely conditional on that path actually being taken."""
    monkeypatch.setenv(FLAG, "1")
    parent_id = make_parent("parent1@example.com")
    conn = get_conn()
    try:
        row = conn.execute(
            "INSERT INTO auth_identities "
            "(provider, provider_subject, parent_id, athlete_id, email, email_verified) "
            "VALUES ('apple', %s, %s, NULL, NULL, FALSE) RETURNING id",
            ("already-linked-sub", parent_id),
        ).fetchone()
        auth_identity_id = row["id"]
        conn.execute(
            "INSERT INTO apple_provider_credentials "
            "(auth_identity_id, encrypted_refresh_token, encryption_nonce) VALUES (%s, %s, %s)",
            (auth_identity_id, b"seed-ciphertext", b"seed-nonce12"),
        )
        conn.commit()
    finally:
        conn.close()

    challenge_id, _nonce = issue_challenge(client, "apple")
    identity = VerifiedAppleIdentity(sub="already-linked-sub", email="parent1@example.com", email_verified=True)

    with caplog.at_level(logging.INFO, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_apple_identity_token", return_value=identity), \
             patch("api.routes.auth.exchange_authorization_code_for_refresh_token") as mock_exchange:
            r = client.post(
                "/api/auth/apple/verify",
                json={"challenge_id": challenge_id, "identity_token": "fake-identity-token"},
            )
    assert r.status_code == 200, r.text
    mock_exchange.assert_not_called()

    verify_matches = [rec for rec in caplog.records if "provider_auth_empirical apple_verify" in rec.getMessage()]
    assert len(verify_matches) == 1, caplog.text
    assert "authorization_code_present=False" in verify_matches[0].getMessage()

    exchange_matches = [rec for rec in caplog.records if "provider_auth_empirical apple_exchange" in rec.getMessage()]
    assert exchange_matches == []


def test_flag_on_apple_verify_failure_logs_observed_alg_and_401_is_unchanged(client, caplog, monkeypatch):
    """The operational gap this task closes: verify_apple_identity_token
    raises (e.g. APPLE_ALLOWED_ALGORITHMS genuinely unset for the first
    real-device run, or any other verification failure) BEFORE the existing
    success-gated log line ever runs -- so without this failure-path log
    line, the one fact we need (Apple's observed alg) would never be
    observable on the very first real run. Flag on, a real/parseable JWT
    header, verification fails -> the new log line still fires with the
    correct alg, and the 401 response is byte-identical to the pre-existing
    generic failure response (same status, same and only 'detail' key, same
    message) -- proving this is purely additive logging, not a behavior
    change."""
    monkeypatch.setenv(FLAG, "1")
    challenge_id, _nonce = issue_challenge(client, "apple")
    real_token = real_jwt_with_alg(alg="HS256", kid="failure-test-kid")

    with caplog.at_level(logging.INFO, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_apple_identity_token", side_effect=AppleVerificationError("bad token")):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": real_token,
                    "authorization_code": "fake-auth-code",
                },
            )
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": APPLE_VERIFY_FAILED_MESSAGE}
    assert set(r.json().keys()) == {"detail"}

    matches = [rec for rec in caplog.records if "provider_auth_empirical apple_verify_failed" in rec.getMessage()]
    assert len(matches) == 1, caplog.text
    assert "observed_alg=HS256" in matches[0].getMessage()


def test_flag_on_apple_verify_failure_with_malformed_token_swallows_parse_error_and_401_is_unchanged(client, monkeypatch):
    """The best-effort observed_alg parse must never itself become a new
    failure mode: a malformed/unparseable identity_token (jwt.get_unverified_header
    raising) must be swallowed cleanly, with the caller still getting exactly
    the same 401 they'd have gotten before this change -- no 500, no
    exception escaping the route, no altered response."""
    monkeypatch.setenv(FLAG, "1")
    challenge_id, _nonce = issue_challenge(client, "apple")
    malformed_token = "this-is-not-a-jwt-at-all"

    with patch("api.routes.auth.verify_apple_identity_token", side_effect=AppleVerificationError("bad token")):
        r = client.post(
            "/api/auth/apple/verify",
            json={
                "challenge_id": challenge_id,
                "identity_token": malformed_token,
                "authorization_code": "fake-auth-code",
            },
        )
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": APPLE_VERIFY_FAILED_MESSAGE}


# ============================================================================
# (c) Flag ON -> genuine negative assertion: no sensitive values leak.
# ============================================================================

def test_flag_on_google_verify_log_never_contains_sensitive_values(client, caplog, monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    make_parent("secret-parent@example.com")
    challenge_id, raw_nonce = issue_challenge(client, "google")
    raw_id_token = "super-secret-google-id-token-value"
    identity = VerifiedGoogleIdentity(sub="g-secret-sub-999", email="secret-parent@example.com", email_verified=True)

    with caplog.at_level(logging.DEBUG, logger=AUTH_LOGGER):
        with patch("api.routes.auth.verify_google_id_token", return_value=identity):
            r = client.post(
                "/api/auth/google/verify",
                json={"challenge_id": challenge_id, "id_token": raw_id_token},
            )
    assert r.status_code == 200, r.text

    log_text = caplog.text
    assert raw_id_token not in log_text
    assert raw_nonce not in log_text
    assert "secret-parent@example.com" not in log_text
    assert "g-secret-sub-999" not in log_text


# ============================================================================
# auth v2.1 Phase 6 corrective pass (external review) -- Correction 1: the
# Apple algorithm-observation bootstrap. Before this fix, a bare RuntimeError
# from verify_apple_identity_token (APPLE_ALLOWED_ALGORITHMS genuinely
# unset -- unavoidably the exact state of the very first real-device
# empirical run) skipped past BOTH `except AppleVerificationError:` AND the
# observed_alg diagnostic logging that lived inside it -- meaning the one
# fact we need (Apple's real signing alg) could never be observed. The fix:
# parse observed_alg unconditionally-on-the-flag BEFORE calling
# verify_apple_identity_token at all, so it's captured no matter which of
# the three outcomes (success / AppleVerificationError / RuntimeError)
# follows.
# ============================================================================

APPLE_CONFIG_ERROR_MESSAGE = "Apple sign-in is not available right now. Please try again later."


def test_flag_on_config_runtime_error_still_logs_observed_alg_the_core_bootstrap_proof(client, caplog, monkeypatch):
    """(a) The core "first empirical run must work" proof: flag on,
    APPLE_ALLOWED_ALGORITHMS genuinely unset (simulated here via
    verify_apple_identity_token raising RuntimeError, exactly what
    apple_auth.py's _apple_allowed_algorithms() does when that env var is
    unset), a real parseable JWT header -- the observed_alg log line still
    fires. Before this fix, this was structurally impossible: the RuntimeError
    skipped past both the except-block and its diagnostic logging."""
    monkeypatch.setenv(FLAG, "1")
    challenge_id, _nonce = issue_challenge(client, "apple")
    real_token = real_jwt_with_alg(alg="HS256", kid="bootstrap-proof-kid")

    with caplog.at_level(logging.INFO, logger=AUTH_LOGGER):
        with patch(
            "api.routes.auth.verify_apple_identity_token",
            side_effect=RuntimeError(
                "APPLE_ALLOWED_ALGORITHMS env var is not set — the Apple "
                "identity-token signing algorithm has not been empirically confirmed"
            ),
        ):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": real_token,
                    "authorization_code": "fake-auth-code",
                },
            )

    # (b) the response is the new generic config-error response, NOT the 401
    # verification-failed message.
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": APPLE_CONFIG_ERROR_MESSAGE}
    assert set(r.json().keys()) == {"detail"}

    matches = [
        rec for rec in caplog.records
        if "provider_auth_empirical" in rec.getMessage() and "observed_alg=" in rec.getMessage()
    ]
    assert len(matches) == 1, caplog.text
    assert "observed_alg=HS256" in matches[0].getMessage()
    # Never leaks the missing env var name into the logs either.
    assert "APPLE_ALLOWED_ALGORITHMS" not in caplog.text


def test_flag_off_config_runtime_error_emits_no_empirical_log_lines_but_response_unchanged(client, caplog, monkeypatch):
    """(c) Flag off -> zero new *diagnostic* log lines (the flag only gates
    the provider_auth_empirical-tagged logging, not the response), and the
    response is the same generic config-error response regardless of the
    flag -- proving the flag's inertness extends cleanly to this new path
    too."""
    monkeypatch.delenv(FLAG, raising=False)
    challenge_id, _nonce = issue_challenge(client, "apple")
    real_token = real_jwt_with_alg(alg="HS256", kid="bootstrap-flag-off-kid")

    with caplog.at_level(logging.DEBUG, logger=AUTH_LOGGER):
        with patch(
            "api.routes.auth.verify_apple_identity_token",
            side_effect=RuntimeError("APPLE_ALLOWED_ALGORITHMS env var is not set"),
        ):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": real_token,
                    "authorization_code": "fake-auth-code",
                },
            )
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": APPLE_CONFIG_ERROR_MESSAGE}

    empirical_matches = [rec for rec in caplog.records if "provider_auth_empirical" in rec.getMessage()]
    assert empirical_matches == [], caplog.text


def test_flag_on_config_runtime_error_with_malformed_token_does_not_crash(client, monkeypatch):
    """(d) A malformed identity_token must not crash the config-error path
    either -- the best-effort observed_alg parse (wrapped in its own
    try/except, falling back to None) must never itself become a new
    failure mode, even when the underlying call also happens to fail with a
    RuntimeError."""
    monkeypatch.setenv(FLAG, "1")
    challenge_id, _nonce = issue_challenge(client, "apple")
    malformed_token = "this-is-not-a-jwt-at-all"

    with patch(
        "api.routes.auth.verify_apple_identity_token",
        side_effect=RuntimeError("APPLE_ALLOWED_ALGORITHMS env var is not set"),
    ):
        r = client.post(
            "/api/auth/apple/verify",
            json={
                "challenge_id": challenge_id,
                "identity_token": malformed_token,
                "authorization_code": "fake-auth-code",
            },
        )
    assert r.status_code == 503, r.text
    assert r.json() == {"detail": APPLE_CONFIG_ERROR_MESSAGE}


def test_flag_on_apple_verify_log_never_contains_sensitive_values(client, caplog, monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    make_parent("secret-parent2@example.com")
    challenge_id, raw_nonce = issue_challenge(client, "apple")
    real_token = real_jwt_with_alg()
    raw_auth_code = "super-secret-apple-authorization-code"
    raw_refresh_token = "super-secret-apple-refresh-token-value"
    identity = VerifiedAppleIdentity(sub="a-secret-sub-999", email="secret-parent2@example.com", email_verified=True)

    with caplog.at_level(logging.DEBUG):
        with patch("api.routes.auth.verify_apple_identity_token", return_value=identity), \
             patch("api.routes.auth.exchange_authorization_code_for_refresh_token", return_value=raw_refresh_token):
            r = client.post(
                "/api/auth/apple/verify",
                json={
                    "challenge_id": challenge_id,
                    "identity_token": real_token,
                    "authorization_code": raw_auth_code,
                },
            )
    assert r.status_code == 200, r.text

    log_text = caplog.text
    assert real_token not in log_text
    assert raw_nonce not in log_text
    assert raw_auth_code not in log_text
    assert raw_refresh_token not in log_text
    assert "secret-parent2@example.com" not in log_text
    assert "a-secret-sub-999" not in log_text
