"""
api/services/google_auth.py (auth v2.1 Phase 6, Part B.1).

verify_google_id_token() wraps google.oauth2.id_token.verify_oauth2_token
with two things that library call does NOT do on its own:
  1. An audience ALLOWLIST check (GOOGLE_ALLOWED_AUDIENCES, a set — not a
     single hardcoded value, per plan A.4) — verify_oauth2_token is called
     without an `audience` argument (so its own single-value audience check
     is skipped), and this module checks idinfo['aud'] against the allowlist
     itself.
  2. A nonce-claim check via the separately-factored, swappable
     _google_nonce_matches() (plan A.6) — verify_oauth2_token does not check
     nonce at all.

We cannot obtain a real Google-issued token in a test environment, so these
tests mock google.oauth2.id_token.verify_oauth2_token's return value
directly — the standard, correct way to test code that wraps a
verification library call, without re-testing the library's own internals.
This mirrors this repo's existing precedent of patching verification
call-sites directly (see tests/test_email_auth_flow.py's
`patch("api.routes.auth.resolve_identity", ...)`).
"""
import hashlib
import logging
import os
from unittest.mock import patch

import google.auth.exceptions
import pytest

from api.services.google_auth import (
    GoogleVerificationError,
    VerifiedGoogleIdentity,
    _google_allowed_audiences,
    _google_nonce_matches,
    verify_google_id_token,
)

APPROVED_WEB_CLIENT_ID = "approved-web-client-id.apps.googleusercontent.com"
OTHER_AUDIENCE = "some-other-client-id.apps.googleusercontent.com"
RAW_NONCE = "test-raw-challenge-nonce-abc123"


@pytest.fixture(autouse=True)
def _google_allowed_audiences_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_AUDIENCES", APPROVED_WEB_CLIENT_ID)


def _idinfo(**overrides):
    base = {
        "sub": "1234567890",
        "email": "athlete-parent@example.com",
        "email_verified": True,
        "aud": APPROVED_WEB_CLIENT_ID,
        "iss": "https://accounts.google.com",
        "nonce": RAW_NONCE,
    }
    base.update(overrides)
    return base


# --- verify_google_id_token ---------------------------------------------


def test_valid_token_matching_nonce_and_allowlisted_audience_returns_identity():
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        return_value=_idinfo(),
    ):
        identity = verify_google_id_token("fake-id-token", RAW_NONCE)

    assert identity == VerifiedGoogleIdentity(
        sub="1234567890",
        email="athlete-parent@example.com",
        email_verified=True,
    )


def test_audience_not_in_allowlist_raises():
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        return_value=_idinfo(aud=OTHER_AUDIENCE),
    ):
        with pytest.raises(GoogleVerificationError):
            verify_google_id_token("fake-id-token", RAW_NONCE)


def test_audience_is_approved_web_client_id_succeeds_positive_control():
    """Proves the allowlist isn't accidentally empty/broken — the approved
    Web client ID (the one and only entry configured in this test's env)
    must itself pass."""
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        return_value=_idinfo(aud=APPROVED_WEB_CLIENT_ID),
    ):
        identity = verify_google_id_token("fake-id-token", RAW_NONCE)
    assert identity.sub == "1234567890"


def test_nonce_mismatch_raises():
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        return_value=_idinfo(nonce="a-completely-different-nonce"),
    ):
        with pytest.raises(GoogleVerificationError):
            verify_google_id_token("fake-id-token", RAW_NONCE)


def test_nonce_claim_absent_from_token_raises_fails_closed():
    idinfo = _idinfo()
    del idinfo["nonce"]
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        return_value=idinfo,
    ):
        with pytest.raises(GoogleVerificationError):
            verify_google_id_token("fake-id-token", RAW_NONCE)


@pytest.mark.parametrize(
    "underlying_exception_class,underlying_error_message",
    [
        # Expired token and invalid signature: empirically confirmed (against
        # the actual pinned google-auth==2.57.0 source) to be raised by
        # google.auth.jwt.decode() as InvalidValue/MalformedError -- both of
        # which happen to subclass ValueError (and GoogleAuthError).
        (google.auth.exceptions.InvalidValue, "Token expired, 100 < 200"),
        (google.auth.exceptions.MalformedError, "Could not verify token signature."),
        # Wrong issuer: empirically confirmed to be raised by
        # verify_oauth2_token() directly as a bare GoogleAuthError -- NOT a
        # ValueError subclass. This is the case CRITICAL finding #1 was about:
        # a plain `except ValueError:` does not catch this.
        (google.auth.exceptions.GoogleAuthError, "Wrong issuer."),
    ],
)
def test_underlying_library_error_raises_google_verification_error(
    underlying_exception_class, underlying_error_message
):
    """Simulates invalid signature / expired token / wrong issuer -- the
    real exception types google.oauth2.id_token.verify_oauth2_token raises
    for each, per empirical confirmation against the pinned library's
    actual source (not the library's own imprecise docstring, which only
    mentions ValueError)."""
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        side_effect=underlying_exception_class(underlying_error_message),
    ):
        with pytest.raises(GoogleVerificationError) as exc_info:
            verify_google_id_token("fake-id-token", RAW_NONCE)

    # The generic exception message must never leak the underlying
    # library's specific failure reason or the raw token.
    assert underlying_error_message not in str(exc_info.value)
    assert "fake-id-token" not in str(exc_info.value)


def test_cert_fetch_network_failure_raises_google_verification_error():
    """CRITICAL finding #2: _fetch_certs() raises
    google.auth.exceptions.TransportError (a GoogleAuthError subclass, not
    a ValueError) when Google's cert endpoint is unreachable or returns a
    non-200 response -- a real, reachable failure mode, not hypothetical."""
    with patch(
        "api.services.google_auth.google_id_token.verify_oauth2_token",
        side_effect=google.auth.exceptions.TransportError(
            "Could not fetch certificates at https://www.googleapis.com/oauth2/v1/certs"
        ),
    ):
        with pytest.raises(GoogleVerificationError) as exc_info:
            verify_google_id_token("fake-id-token", RAW_NONCE)

    assert "fake-id-token" not in str(exc_info.value)


# --- _google_allowed_audiences -------------------------------------------


def test_allowed_audiences_env_var_unset_raises_clear_config_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_ALLOWED_AUDIENCES", raising=False)
    with pytest.raises(Exception):
        _google_allowed_audiences()


def test_allowed_audiences_parses_comma_separated_set(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_ALLOWED_AUDIENCES", f" {APPROVED_WEB_CLIENT_ID} , {OTHER_AUDIENCE} "
    )
    assert _google_allowed_audiences() == {APPROVED_WEB_CLIENT_ID, OTHER_AUDIENCE}


# --- _google_nonce_matches (unit-tested directly, in isolation) ----------


def test_google_nonce_matches_true_when_equal():
    assert _google_nonce_matches("abc123", "abc123") is True


def test_google_nonce_matches_false_when_different():
    assert _google_nonce_matches("abc123", "xyz789") is False


def test_google_nonce_matches_false_when_token_claim_is_none():
    assert _google_nonce_matches("abc123", None) is False


# ============================================================================
# auth v2.1 Phase 6 corrective pass (external review) -- Correction 2:
# flag-gated, diagnostic-only nonce-transform observation. _google_nonce_matches
# is a raw-equality PLACEHOLDER pending empirical confirmation -- these tests
# prove the diagnostic sees BOTH a raw-match and a sha256-match independently
# (so a wrong guess is diagnosable), while the actual enforcement
# (_google_nonce_matches, unmodified) remains the sole determinant of
# pass/fail in every case, including when both diagnostic booleans are False.
# ============================================================================

GOOGLE_LOGGER = "api.services.google_auth"


def _sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def test_google_nonce_diagnostic_raw_match_only_logs_true_false_and_verification_succeeds(caplog, monkeypatch):
    """Raw comparison matches (== the current, actually-enforced transform);
    sha256 does not. Verification succeeds, exactly as it does today."""
    monkeypatch.setenv("PROVIDER_AUTH_EMPIRICAL_LOGGING", "1")
    with caplog.at_level(logging.INFO, logger=GOOGLE_LOGGER):
        with patch(
            "api.services.google_auth.google_id_token.verify_oauth2_token",
            return_value=_idinfo(nonce=RAW_NONCE),
        ):
            identity = verify_google_id_token("fake-id-token", RAW_NONCE)
    assert identity.sub == "1234567890"

    matches = [rec for rec in caplog.records if "provider_auth_empirical google_verify" in rec.getMessage()]
    assert len(matches) == 1, caplog.text
    msg = matches[0].getMessage()
    assert "nonce_raw_match=True" in msg
    assert "nonce_sha256_match=False" in msg


def test_google_nonce_diagnostic_sha256_match_only_logs_false_true_and_verification_still_fails_closed(caplog, monkeypatch):
    """sha256(raw) matches the token's nonce claim; raw equality does not.
    _google_nonce_matches is UNCHANGED raw-equality enforcement, so this
    must still raise GoogleVerificationError -- the diagnostic observes but
    never overrides enforcement."""
    monkeypatch.setenv("PROVIDER_AUTH_EMPIRICAL_LOGGING", "1")
    sha256_nonce = _sha256_hex(RAW_NONCE)
    with caplog.at_level(logging.INFO, logger=GOOGLE_LOGGER):
        with patch(
            "api.services.google_auth.google_id_token.verify_oauth2_token",
            return_value=_idinfo(nonce=sha256_nonce),
        ):
            with pytest.raises(GoogleVerificationError):
                verify_google_id_token("fake-id-token", RAW_NONCE)

    matches = [rec for rec in caplog.records if "provider_auth_empirical google_verify" in rec.getMessage()]
    assert len(matches) == 1, caplog.text
    msg = matches[0].getMessage()
    assert "nonce_raw_match=False" in msg
    assert "nonce_sha256_match=True" in msg


def test_google_nonce_diagnostic_neither_match_logs_false_false_and_verification_still_fails_closed(caplog, monkeypatch):
    """Most important assertion in this correction: when NEITHER transform
    matches, the diagnostic logs both booleans False, and enforcement still
    fails closed via the existing, unmodified GoogleVerificationError --
    diagnostics observing never overrides enforcement."""
    monkeypatch.setenv("PROVIDER_AUTH_EMPIRICAL_LOGGING", "1")
    with caplog.at_level(logging.INFO, logger=GOOGLE_LOGGER):
        with patch(
            "api.services.google_auth.google_id_token.verify_oauth2_token",
            return_value=_idinfo(nonce="a-completely-unrelated-nonce-value"),
        ):
            with pytest.raises(GoogleVerificationError):
                verify_google_id_token("fake-id-token", RAW_NONCE)

    matches = [rec for rec in caplog.records if "provider_auth_empirical google_verify" in rec.getMessage()]
    assert len(matches) == 1, caplog.text
    msg = matches[0].getMessage()
    assert "nonce_raw_match=False" in msg
    assert "nonce_sha256_match=False" in msg


def test_google_nonce_diagnostic_flag_off_emits_no_log_lines(caplog, monkeypatch):
    """Flag-off inertness extends cleanly to the new nonce-diagnostic log
    line too -- zero log records, and enforcement behavior is identical to
    before this correction existed."""
    monkeypatch.delenv("PROVIDER_AUTH_EMPIRICAL_LOGGING", raising=False)
    with caplog.at_level(logging.DEBUG, logger=GOOGLE_LOGGER):
        with patch(
            "api.services.google_auth.google_id_token.verify_oauth2_token",
            return_value=_idinfo(nonce=RAW_NONCE),
        ):
            identity = verify_google_id_token("fake-id-token", RAW_NONCE)
    assert identity.sub == "1234567890"
    assert caplog.records == []
