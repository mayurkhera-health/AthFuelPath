"""Sign in with Apple — server-side identity-token verification and
refresh-token exchange (auth v2.1 Phase 6, plan B.2/A.5/A.6/A.7).

This module verifies Apple's `identityToken` (the user's proof of identity,
built and signed by Apple) and separately performs the one-time,
synchronous `authorization_code` -> `refresh_token` exchange required to
satisfy Phase 10's revocation prerequisite (A.7/A.8). It does NOT call
`resolve_identity()`, write to `auth_identities`, or touch the database in
any way — this is a pure verification/exchange service; the atomic,
credential-first orchestration lives in `api/routes/auth.py` (Part F/C.3).

Two things in this file are DELIBERATELY left configurable rather than
hardcoded, because they are empirically unconfirmed as of this writing
(plan A.5/A.6, pending a real-device test against the actual native
`expo-apple-authentication` flow — a later, separate task):

  1. The user identity token's signing algorithm (`_apple_allowed_algorithms`)
     — do NOT assume this matches ES256 just because
     `_build_apple_client_secret()` below also happens to use ES256. Those
     are two independently-confirmed requirements for two structurally
     different tokens (A.5): the client secret's ES256 is OUR choice,
     mandated by Apple's REST API docs for what we must produce; the
     identity token's algorithm is APPLE's choice for what Apple produces,
     and has not yet been empirically confirmed against a live JWKS fetch
     and a genuine decoded token header.
  2. The nonce-claim comparison transform (`_apple_nonce_matches`) — Apple's
     docs describe a SHA-256 pre-hash for some of its web/JS flows; whether
     `expo-apple-authentication`'s native path does the same has not yet
     been confirmed against a real token.

Both are built as small, swappable functions specifically so the pending
empirical confirmation step only ever requires changing this file's
internals (or an env var, for the algorithm allowlist) — never call sites.
"""
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import jwt
from jwt import PyJWK

logger = logging.getLogger(__name__)

# auth v2.1 Phase 6 corrective pass (external review) -- tiny, duplicated
# env-read helper, matching this codebase's established tolerance for small
# per-module config-flag duplication (e.g. this file's own
# _apple_bundle_id(), google_auth.py's identical copy) rather than importing
# api.routes.auth's identical _empirical_logging_enabled() (which would risk
# a circular import: api.routes.auth imports this module). Keep in sync with
# api.routes.auth._empirical_logging_enabled() and google_auth.py's copy if
# the env var name or accepted values ever change.
_EMPIRICAL_LOGGING_ENV_VAR = "PROVIDER_AUTH_EMPIRICAL_LOGGING"


def _empirical_logging_enabled() -> bool:
    return os.getenv(_EMPIRICAL_LOGGING_ENV_VAR, "false").strip().lower() in ("1", "true")


APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_ISSUER = "https://appleid.apple.com"

# Apple's own client-secret JWT contract caps `exp` at 6 months out
# (15,777,000s). 180 days keeps a small safety margin under that cap.
APPLE_CLIENT_SECRET_TTL_SECONDS = 60 * 60 * 24 * 180

_JWKS_CACHE_TTL_SECONDS = 3600
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


@dataclass
class VerifiedAppleIdentity:
    sub: str
    email: Optional[str]  # from the verified TOKEN claims, never credential.email
    email_verified: bool


class AppleVerificationError(Exception):
    """Signature/issuer/audience/expiry/nonce check failed."""


# --- Environment configuration -------------------------------------------
# Matches this codebase's os.environ[...]-at-call-time convention (see
# api/services/session_auth.py's _secret()). Missing config raises a clear
# RuntimeError — never a silent fallback to a guessed value.

def _apple_bundle_id() -> str:
    val = os.environ.get("APPLE_BUNDLE_ID", "")
    if not val:
        raise RuntimeError(
            "APPLE_BUNDLE_ID env var is not set — Apple Sign-In cannot be "
            "verified until this is configured."
        )
    return val


def _apple_team_id() -> str:
    val = os.environ.get("APPLE_TEAM_ID", "")
    if not val:
        raise RuntimeError(
            "APPLE_TEAM_ID env var is not set — the Apple client secret "
            "cannot be built until this is configured."
        )
    return val


def _apple_key_id() -> str:
    val = os.environ.get("APPLE_KEY_ID", "")
    if not val:
        raise RuntimeError(
            "APPLE_KEY_ID env var is not set — the Apple client secret "
            "cannot be built until this is configured."
        )
    return val


def _apple_private_key() -> str:
    val = os.environ.get("APPLE_PRIVATE_KEY", "")
    if not val:
        raise RuntimeError(
            "APPLE_PRIVATE_KEY env var is not set — the Apple client secret "
            "cannot be signed until this is configured."
        )
    return val


def _apple_nonce_matches(raw_challenge_nonce: str, token_nonce_claim: Optional[str]) -> bool:
    """
    PLACEHOLDER pending empirical confirmation (Phase 6 plan, A.6) of the
    actual transform expo-apple-authentication's native flow applies.
    Apple's documentation for SOME of its web/JS flows describes a
    SHA-256 pre-hash of the supplied nonce before it's embedded in the
    token's nonce claim -- this is used here as the best-available
    documented default, but MUST be empirically re-verified against a
    real token from the actual native module before this is trusted in
    production; if the real behavior turns out to be verbatim (unhashed),
    this function's body is the only thing that needs to change. Trivially
    swappable, matching google_auth.py's identical pattern for the same
    reason.
    """
    return bool(token_nonce_claim) and hashlib.sha256(raw_challenge_nonce.encode()).hexdigest() == token_nonce_claim


def _apple_allowed_algorithms() -> list[str]:
    """
    PLACEHOLDER pending empirical confirmation (Phase 6 plan, A.5) of
    Apple's actual identity-token signing algorithm from a live JWKS
    fetch + a genuine decoded token header. Reads APPLE_ALLOWED_ALGORITHMS
    from the environment (comma-separated) so the confirmed value can be
    supplied via configuration without a code change once confirmed --
    raises a clear configuration error if unset, does NOT default to a
    guessed algorithm silently.
    """
    raw = os.environ.get("APPLE_ALLOWED_ALGORITHMS", "")
    algorithms = [a.strip() for a in raw.split(",") if a.strip()]
    if not algorithms:
        raise RuntimeError(
            "APPLE_ALLOWED_ALGORITHMS env var is not set — the Apple "
            "identity-token signing algorithm has not been empirically "
            "confirmed (Phase 6 plan, A.5) and this function refuses to "
            "guess. Set it to a comma-separated allowlist (e.g. 'RS256') "
            "once confirmed against a live JWKS fetch and a genuine token."
        )
    if "none" in [a.lower() for a in algorithms]:
        raise RuntimeError(
            "APPLE_ALLOWED_ALGORITHMS must never include 'none' — refusing "
            "to start with an algorithm allowlist that would accept "
            "unsigned tokens."
        )
    return algorithms


def _fetch_apple_jwks_response() -> httpx.Response:
    """Thin wrapper around the outbound HTTPS GET to Apple's JWKS endpoint —
    isolated so tests can monkeypatch exactly this function to simulate a
    network failure/timeout, without needing a real HTTP mock server and
    without bypassing _fetch_apple_jwks's own caching/error-handling logic."""
    return httpx.get(APPLE_JWKS_URL, timeout=15)


def _fetch_apple_jwks(*, force_refresh: bool = False) -> dict:
    """Fetches and caches Apple's published JWKS
    (https://appleid.apple.com/auth/keys). Isolated in its own function
    (rather than inlined) specifically so tests can monkeypatch this exact
    function to return a locally-generated JWKS in Apple's published
    format, letting the real signature-verification code path run against
    a token/key the test controls — no network access required.

    force_refresh=True bypasses the cache unconditionally — used by
    verify_apple_identity_token's one-shot retry when a token's kid isn't
    found in the cached JWKS, so a legitimate token signed under a
    just-rotated Apple key doesn't have to wait out the full cache TTL.

    Raises AppleVerificationError (never a raw httpx exception) on any
    network failure, timeout, or non-2xx response — matching this
    function's callers, which all assume JWKS-fetch failures surface the
    same way as any other verification failure."""
    now = time.time()
    cached = _jwks_cache.get("keys")
    fetched_at = _jwks_cache.get("fetched_at", 0.0)
    if not force_refresh and cached is not None and (now - fetched_at) < _JWKS_CACHE_TTL_SECONDS:
        return cached
    try:
        resp = _fetch_apple_jwks_response()
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise AppleVerificationError("Could not fetch Apple's signing keys.") from exc
    _jwks_cache["keys"] = data
    _jwks_cache["fetched_at"] = now
    return data


def _coerce_bool(value) -> bool:
    """Apple's email_verified claim is sometimes a JSON bool, sometimes the
    string 'true'/'false' — normalize either into a real bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def verify_apple_identity_token(identity_token: str, raw_challenge_nonce: str) -> VerifiedAppleIdentity:
    """
    Fetches/caches Apple's JWKS (https://appleid.apple.com/auth/keys),
    selects the key matching the token's kid. Verifies signature against
    ONLY the algorithms in _apple_allowed_algorithms() -- explicitly
    rejects alg=none and any algorithm outside that allowlist, and any
    kid not present in the current JWKS. Verifies iss ==
    'https://appleid.apple.com', aud == APPLE_BUNDLE_ID (env-configured),
    exp, and that the token's 'nonce' claim matches raw_challenge_nonce
    via _apple_nonce_matches(). Raises AppleVerificationError on any
    failure. Returns sub/email/email_verified read from the verified
    token only -- never from any client-supplied field, which this
    function doesn't even accept as input.
    """
    # Config errors (missing algorithm allowlist / bundle id) are distinct
    # from token-verification failures and intentionally propagate as
    # RuntimeError, not AppleVerificationError — they mean "this deployment
    # isn't configured yet," not "this particular sign-in attempt is bad."
    allowed_algorithms = _apple_allowed_algorithms()
    bundle_id = _apple_bundle_id()

    try:
        unverified_header = jwt.get_unverified_header(identity_token)
    except jwt.InvalidTokenError as exc:
        raise AppleVerificationError("Apple identity token is malformed.") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise AppleVerificationError("Apple identity token is missing a key id.")

    jwks = _fetch_apple_jwks()
    matching_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if matching_key is None:
        # One-shot retry: Apple may have rotated its signing keys since our
        # cached JWKS was fetched. Force exactly one fresh, cache-bypassing
        # fetch and look up the kid once more before failing closed — not a
        # full cache-invalidation loop, just a single bypass-cache retry.
        jwks = _fetch_apple_jwks(force_refresh=True)
        matching_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if matching_key is None:
        raise AppleVerificationError("Apple identity token references an unrecognized signing key.")

    try:
        signing_key = PyJWK(matching_key)
    except Exception as exc:  # noqa: BLE001 — any malformed-key condition is a verification failure here
        raise AppleVerificationError("Apple's signing key could not be loaded.") from exc

    try:
        claims = jwt.decode(
            identity_token,
            key=signing_key,
            algorithms=allowed_algorithms,
            audience=bundle_id,
            issuer=APPLE_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AppleVerificationError("Apple identity token failed verification.") from exc

    # auth v2.1 Phase 6 corrective pass (external review) -- diagnostic-only,
    # flag-gated nonce-transform observation. This exists because
    # _apple_nonce_matches() below is a PLACEHOLDER pending empirical
    # confirmation of the actual transform expo-apple-authentication's
    # native flow applies (see this module's own docstring and
    # _apple_nonce_matches' docstring) -- if the sha256-prehash guess turns
    # out to be wrong, this lets a person running the backend locally see
    # whether raw OR sha256 WOULD have matched, without ever weakening
    # enforcement to accept either. Logs ONLY two booleans -- never the raw
    # nonce, the token's nonce claim, the token itself, or the computed hash
    # value. Independent of google_auth.py's identical-shaped diagnostic --
    # deliberately not shared logic, since the two providers' nonce
    # transforms are treated as potentially different.
    #
    # CRITICAL: this never influences pass/fail. The unmodified
    # _apple_nonce_matches() call immediately below remains the sole
    # determinant of verification outcome -- a genuine mismatch (both
    # booleans False) still raises AppleVerificationError exactly as before
    # this diagnostic was added.
    if _empirical_logging_enabled():
        token_nonce_claim = claims.get("nonce")
        nonce_raw_match = bool(token_nonce_claim) and raw_challenge_nonce == token_nonce_claim
        nonce_sha256_match = (
            bool(token_nonce_claim)
            and hashlib.sha256(raw_challenge_nonce.encode()).hexdigest() == token_nonce_claim
        )
        logger.info(
            "provider_auth_empirical apple_verify: nonce_raw_match=%s nonce_sha256_match=%s",
            nonce_raw_match, nonce_sha256_match,
        )

    if not _apple_nonce_matches(raw_challenge_nonce, claims.get("nonce")):
        raise AppleVerificationError("Apple identity token nonce did not match the issued challenge.")

    sub = claims.get("sub")
    if not sub:
        raise AppleVerificationError("Apple identity token is missing its subject claim.")

    return VerifiedAppleIdentity(
        sub=sub,
        email=claims.get("email"),
        email_verified=_coerce_bool(claims.get("email_verified")),
    )


async def _apple_token_exchange_request(data: dict) -> httpx.Response:
    """Thin wrapper around the outbound HTTPS POST to Apple's token
    endpoint — isolated so tests can monkeypatch exactly this function with
    a fake async response, rather than needing a real HTTP mock server."""
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.post(APPLE_TOKEN_URL, data=data)


async def exchange_authorization_code_for_refresh_token(authorization_code: str, expected_sub: str) -> str:
    """
    POSTs to https://appleid.apple.com/auth/token with
    client_id=APPLE_BUNDLE_ID, client_secret=<from _build_apple_client_secret()>,
    code=authorization_code, grant_type=authorization_code. Decodes the
    response's own id_token (a lightweight claims read -- the response's
    authenticity rests on the outbound HTTPS call + our own client_secret
    authentication, not a second JWKS signature-verification pass) and
    confirms its sub == expected_sub and aud == APPLE_BUNDLE_ID before
    returning anything -- raises AppleVerificationError on any mismatch,
    any HTTP failure, any malformed response. Returns the raw
    refresh_token. NEVER logs the authorization_code, the response body,
    or the returned token anywhere -- no print, no logger.* referencing
    any of these values, not even at debug level.
    """
    bundle_id = _apple_bundle_id()
    client_secret = _build_apple_client_secret()

    request_data = {
        "client_id": bundle_id,
        "client_secret": client_secret,
        "code": authorization_code,
        "grant_type": "authorization_code",
    }

    try:
        response = await _apple_token_exchange_request(request_data)
    except httpx.HTTPError as exc:
        # Deliberately no exc/request/response detail in the message —
        # never logs the authorization_code or anything derived from it.
        raise AppleVerificationError("Apple token exchange request failed.") from exc

    if response.status_code != 200:
        raise AppleVerificationError("Apple token exchange returned a non-success response.")

    try:
        body = response.json()
    except ValueError as exc:
        raise AppleVerificationError("Apple token exchange returned a malformed response.") from exc

    refresh_token = body.get("refresh_token")
    id_token = body.get("id_token")
    if not refresh_token or not id_token:
        raise AppleVerificationError("Apple token exchange response is missing required fields.")

    try:
        # Lightweight claims read only, deliberately NOT a second full
        # JWKS-signature-verification pass — see A.7/A.8: the response's
        # authenticity already rests on this being a direct HTTPS call to
        # Apple authenticated with our own client_secret.
        response_claims = jwt.decode(id_token, options={"verify_signature": False})
    except jwt.InvalidTokenError as exc:
        raise AppleVerificationError("Apple token exchange returned a malformed id_token.") from exc

    if response_claims.get("sub") != expected_sub or response_claims.get("aud") != bundle_id:
        # Subject-binding check (A.7) — a hard-fail sanity check, not a
        # normally-expected branch. Refresh token is never returned/stored
        # on a mismatch.
        raise AppleVerificationError("Apple token exchange response did not match the expected identity.")

    return refresh_token


def _build_apple_client_secret() -> str:
    """
    Builds a fresh ES256-signed JWT client_secret for EACH call needing
    one -- never stored as a static long-lived string. header
    {alg: ES256, kid: APPLE_KEY_ID}; payload {iss: APPLE_TEAM_ID,
    sub: APPLE_BUNDLE_ID, aud: 'https://appleid.apple.com', iat,
    exp <= 6 months out}; signed with APPLE_PRIVATE_KEY (the .p8 file
    contents, read from an environment variable at call time -- this IS
    a genuinely required, confirmed algorithm per Apple's own REST API
    docs, unlike the user identity token's algorithm -- do not conflate
    the two, this function's ES256 choice is correct and final, it is
    NOT the empirically-pending part of this file).
    """
    now = int(time.time())
    payload = {
        "iss": _apple_team_id(),
        "iat": now,
        "exp": now + APPLE_CLIENT_SECRET_TTL_SECONDS,
        "aud": APPLE_ISSUER,
        "sub": _apple_bundle_id(),
    }
    headers = {"kid": _apple_key_id()}
    return jwt.encode(payload, _apple_private_key(), algorithm="ES256", headers=headers)
