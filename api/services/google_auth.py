"""
Google ID-token verification (auth v2.1 Phase 6, Part B.1 — see
docs/superpowers/plans/2026-08-24-auth-v2.1-phase-6.md, sections A.4 and A.6).

verify_google_id_token() wraps google.oauth2.id_token.verify_oauth2_token
with two checks that library call does NOT perform on its own:

  1. An audience ALLOWLIST check (GOOGLE_ALLOWED_AUDIENCES, an explicit,
     environment-configured SET — never a single hardcoded value, per A.4).
     verify_oauth2_token is deliberately called WITHOUT an `audience`
     argument (its own audience check only supports a single expected
     value), and this module checks the verified token's own `aud` claim
     against the allowlist itself.
  2. A nonce-claim check via the separately-factored, swappable
     _google_nonce_matches() (per A.6) — verify_oauth2_token does not
     check nonce at all; that's a required additional step layered on top.

_google_nonce_matches() is now CONFIRMED, not a placeholder (Phase 6 plan,
A.6, real-device Gate 3 validation): react-native-nitro-google-signin's
flow results in the token's nonce claim being
sha256(raw_nonce).hexdigest() -- not the raw value verbatim, contrary to
the earlier placeholder guess based on standard OIDC nonce-echo behavior.
It accepts SHA-256(raw) ONLY -- no dual-accept, no fallback to a raw-
equality comparison. It remains factored out as its own function so any
future correction would only ever require changing this function's body,
never a caller. The audience allowlist's actual production contents
remain a later, separate configuration step this module does not perform.

Everything else here (signature, issuer, expiry checks delegated to
google.oauth2.id_token.verify_oauth2_token) rests on Google's own published
library contract, not a guess.

Known follow-up, not implemented here: google.oauth2.id_token's own
docstring recommends wrapping the transport Request with an external HTTP
caching layer (e.g. CacheControl) so Google's certs aren't re-fetched over
the network on every single verification call. This module deliberately
does not add that -- CacheControl is not currently a dependency of this
codebase, and a hand-rolled cache risks silently serving stale keys past a
real Google key rotation if it doesn't correctly honor cache-control
semantics, which is a worse failure mode than the current latency/
availability cost for a security-sensitive minors' app. Left as an
explicit, documented follow-up rather than silently uncached.
"""
import hashlib
import logging
import os
from dataclasses import dataclass

import google.auth.exceptions
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger(__name__)

# auth v2.1 Phase 6 corrective pass (external review) -- tiny, duplicated
# env-read helper, matching this codebase's established tolerance for small
# per-module config-flag duplication (e.g. this file's own
# _google_allowed_audiences(), apple_auth.py's _apple_bundle_id()) rather
# than importing api.routes.auth's identical _empirical_logging_enabled()
# (which would risk a circular import: api.routes.auth imports this module).
# Keep in sync with api.routes.auth._empirical_logging_enabled() and
# apple_auth.py's copy if the env var name or accepted values ever change.
_EMPIRICAL_LOGGING_ENV_VAR = "PROVIDER_AUTH_EMPIRICAL_LOGGING"


def _empirical_logging_enabled() -> bool:
    return os.getenv(_EMPIRICAL_LOGGING_ENV_VAR, "false").strip().lower() in ("1", "true")


@dataclass
class VerifiedGoogleIdentity:
    sub: str
    email: str | None
    email_verified: bool


class GoogleVerificationError(Exception):
    """Signature/issuer/audience/expiry/nonce check failed. Message is
    generic and safe to log; never includes the raw token."""


def _google_allowed_audiences() -> set[str]:
    """Reads GOOGLE_ALLOWED_AUDIENCES (comma-separated) from the
    environment and returns it as a set — the "allowlist, not a single
    hardcoded value" design from plan A.4. This codebase has no existing
    comma-separated-env-var convention to follow (checked api/main.py and
    api/database.py), so this uses the plain
    `os.environ["..."].split(",")` approach with whitespace-stripping.

    Raises a clear configuration error if the env var is unset — never
    silently allows everything (no allowlist enforcement) or nothing (every
    real Google sign-in would then fail closed with no way to diagnose why).
    """
    raw = os.environ.get("GOOGLE_ALLOWED_AUDIENCES", "")
    if not raw.strip():
        raise RuntimeError(
            "GOOGLE_ALLOWED_AUDIENCES env var is not set — Google sign-in "
            "cannot be verified until this is configured with the approved "
            "Web/server OAuth client ID(s)."
        )
    return {aud.strip() for aud in raw.split(",") if aud.strip()}


def _google_nonce_matches(raw_challenge_nonce: str, token_nonce_claim: str | None) -> bool:
    """
    CONFIRMED behavior (Phase 6 plan, A.6) from real-device Gate 3
    validation: react-native-nitro-google-signin's flow results in the
    token's nonce claim being sha256(raw_nonce).hexdigest() -- not the raw
    value verbatim, contrary to the earlier placeholder guess based on
    standard OIDC nonce-echo behavior. Accepts SHA-256(raw) ONLY -- no
    dual-accept, no fallback to a raw-equality comparison.
    """
    return (
        bool(token_nonce_claim)
        and hashlib.sha256(raw_challenge_nonce.encode()).hexdigest() == token_nonce_claim
    )


def verify_google_id_token(id_token_str: str, raw_challenge_nonce: str) -> VerifiedGoogleIdentity:
    """
    Verifies via google.oauth2.id_token.verify_oauth2_token against
    GOOGLE_ALLOWED_AUDIENCES (an explicit, environment-configured set --
    see _google_allowed_audiences() above; contains only the approved
    Web/server client ID, never the iOS/Android client IDs, per the plan's
    A.4). Then independently verifies the token's own 'nonce' claim via
    _google_nonce_matches() -- Google's baseline library call does NOT
    check nonce at all, this is an additional required step. Raises
    GoogleVerificationError on any failure. Returns sub/email/
    email_verified read from the verified token claims only.

    Note: a misconfigured GOOGLE_ALLOWED_AUDIENCES (env var unset) raises a
    separate, uncaught RuntimeError from _google_allowed_audiences() --
    that's a deployment-configuration error, not a token-verification
    failure, so it is deliberately not wrapped as GoogleVerificationError.
    """
    allowed_audiences = _google_allowed_audiences()

    # No `audience` kwarg passed deliberately -- verify_oauth2_token's own
    # audience check only supports a single expected value, which would
    # defeat the allowlist design. Signature/issuer/expiry are still fully
    # verified by this call, per google-auth's documented contract.
    #
    # Exception surface, empirically confirmed against the actual pinned
    # google-auth==2.57.0 source (not assumed from the docstring alone,
    # which is itself imprecise here):
    #   - verify_oauth2_token() raises google.auth.exceptions.GoogleAuthError
    #     directly for a wrong issuer -- this is NOT a ValueError subclass.
    #   - Signature/expiry/audience/malformed-claim failures are raised by
    #     google.auth.jwt.decode() (the code path actually exercised here,
    #     since the configured certs URL returns the x509-map cert format,
    #     not a JWK set) as google.auth.exceptions.InvalidValue or
    #     .MalformedError -- both of which happen to subclass BOTH
    #     GoogleAuthError and ValueError.
    #   - _fetch_certs() raises google.auth.exceptions.TransportError (a
    #     GoogleAuthError subclass, not a ValueError) on a non-200 response
    #     or connection failure while fetching Google's certs -- a real,
    #     reachable failure mode (Google's cert endpoint being briefly
    #     unreachable), not hypothetical.
    # Catching (ValueError, GoogleAuthError) together covers all of the
    # above, including TransportError via GoogleAuthError.
    try:
        idinfo = google_id_token.verify_oauth2_token(
            id_token_str, google_auth_requests.Request()
        )
    except (ValueError, google.auth.exceptions.GoogleAuthError):
        # Never surface the underlying message or the raw token -- both
        # could contain sensitive detail unsafe to log.
        raise GoogleVerificationError("Google ID token failed verification.")

    if idinfo.get("aud") not in allowed_audiences:
        raise GoogleVerificationError("Google ID token failed verification.")

    # auth v2.1 Phase 6 corrective pass (external review) -- diagnostic-only,
    # flag-gated nonce-transform observation. This is what CONFIRMED
    # _google_nonce_matches() below via real-device Gate 3 validation
    # (sha256-of-raw, not the earlier raw-equality guess -- see this
    # module's own docstring and _google_nonce_matches' docstring). Left
    # in place so a person running the backend locally can still see
    # whether raw OR sha256 WOULD have matched, without ever weakening
    # either. Logs ONLY two booleans -- never the raw nonce, the token's
    # nonce claim, the token itself, or the computed hash value.
    #
    # CRITICAL: this never influences pass/fail. The unmodified
    # _google_nonce_matches() call immediately below remains the sole
    # determinant of verification outcome -- a genuine mismatch (both
    # booleans False) still raises GoogleVerificationError exactly as before
    # this diagnostic was added.
    if _empirical_logging_enabled():
        token_nonce_claim = idinfo.get("nonce")
        nonce_raw_match = bool(token_nonce_claim) and raw_challenge_nonce == token_nonce_claim
        nonce_sha256_match = (
            bool(token_nonce_claim)
            and hashlib.sha256(raw_challenge_nonce.encode()).hexdigest() == token_nonce_claim
        )
        logger.info(
            "provider_auth_empirical google_verify: nonce_raw_match=%s nonce_sha256_match=%s",
            nonce_raw_match, nonce_sha256_match,
        )

    if not _google_nonce_matches(raw_challenge_nonce, idinfo.get("nonce")):
        raise GoogleVerificationError("Google ID token failed verification.")

    return VerifiedGoogleIdentity(
        sub=idinfo["sub"],
        email=idinfo.get("email"),
        email_verified=bool(idinfo.get("email_verified", False)),
    )
