"""Tests for api/services/apple_auth.py (auth v2.1 Phase 6, Part B.2).

Builds locally-signed, Apple-shaped identity tokens with a real EC keypair
(via `cryptography`) and monkeypatches `_fetch_apple_jwks` to return a
JWKS containing that keypair's public half in Apple's published format —
so the actual JWKS-based signature-verification code path in
`verify_apple_identity_token` runs for real against a token this test
controls, rather than mocking verification itself away.

Also proves (A.5/A.6) that the identity-token algorithm allowlist and the
nonce-comparison transform are both explicit, configurable, and swappable
— never silently hardcoded as if empirically final — and (A.7) that the
authorization-code exchange's subject-binding check actually blocks a
mismatched response from ever producing a usable refresh token.
"""
import asyncio
import base64
import hashlib
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from api.services import apple_auth
from api.services.apple_auth import (
    AppleVerificationError,
    VerifiedAppleIdentity,
    _apple_allowed_algorithms,
    _apple_nonce_matches,
    _build_apple_client_secret,
    exchange_authorization_code_for_refresh_token,
    verify_apple_identity_token,
)

BUNDLE_ID = "com.fuelupyouth.app"
TEAM_ID = "TEAMID1234"
KEY_ID = "CLIENTSECRETKEY1"
TOKEN_KID = "apple-jwks-key-1"


# --- Local key/token fixtures ---------------------------------------------

def _generate_ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key


def _private_key_pem(private_key) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _int_to_b64url(value: int, length: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode().rstrip("=")


def _public_jwk(private_key, kid: str, alg: str = "ES256") -> dict:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _int_to_b64url(numbers.x, 32),
        "y": _int_to_b64url(numbers.y, 32),
        "kid": kid,
        "alg": alg,
        "use": "sig",
    }


@pytest.fixture
def apple_signing_key():
    """Simulates Apple's own JWKS signing key."""
    return _generate_ec_keypair()


@pytest.fixture
def apple_client_secret_key():
    """Simulates our APPLE_PRIVATE_KEY (.p8) used only by _build_apple_client_secret."""
    return _generate_ec_keypair()


@pytest.fixture(autouse=True)
def apple_env(monkeypatch, apple_client_secret_key):
    monkeypatch.setenv("APPLE_BUNDLE_ID", BUNDLE_ID)
    monkeypatch.setenv("APPLE_TEAM_ID", TEAM_ID)
    monkeypatch.setenv("APPLE_KEY_ID", KEY_ID)
    monkeypatch.setenv("APPLE_PRIVATE_KEY", _private_key_pem(apple_client_secret_key))
    monkeypatch.setenv("APPLE_ALLOWED_ALGORITHMS", "ES256")
    # Reset the module-level JWKS cache so tests never leak keys/timing
    # between each other regardless of what _fetch_apple_jwks is patched to.
    apple_auth._jwks_cache["keys"] = None
    apple_auth._jwks_cache["fetched_at"] = 0.0
    yield


@pytest.fixture
def mock_jwks(monkeypatch, apple_signing_key):
    """Monkeypatches the JWKS fetch to return our locally-generated public
    key in Apple's published JWKS format — the real signature-verification
    path in verify_apple_identity_token runs against this for real."""
    jwks = {"keys": [_public_jwk(apple_signing_key, TOKEN_KID)]}
    monkeypatch.setattr(apple_auth, "_fetch_apple_jwks", lambda: jwks)
    return jwks


def _raw_nonce() -> str:
    return "test-challenge-raw-nonce-value"


def _hashed_nonce_claim(raw_nonce: str) -> str:
    return hashlib.sha256(raw_nonce.encode()).hexdigest()


def _build_token(
    *,
    signing_key,
    kid: str = TOKEN_KID,
    alg: str = "ES256",
    sub: str = "apple-sub-0001",
    email="teen@example.com",
    email_verified=True,
    iss: str = apple_auth.APPLE_ISSUER,
    aud: str = BUNDLE_ID,
    exp_delta: int = 600,
    nonce_claim=None,
    headers_override: dict | None = None,
    payload_override: dict | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "iss": iss,
        "aud": aud,
        "exp": now + exp_delta,
        "iat": now,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "nonce": nonce_claim,
    }
    if payload_override:
        payload.update(payload_override)
    headers = {"kid": kid}
    if headers_override:
        headers.update(headers_override)
    key = _private_key_pem(signing_key) if signing_key is not None else None
    return jwt.encode(payload, key, algorithm=alg, headers=headers)


# --- 1. Valid token --------------------------------------------------------

def test_valid_token_returns_verified_identity(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        sub="apple-sub-happy-path",
        email="teen@example.com",
        email_verified=True,
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    identity = verify_apple_identity_token(token, raw_nonce)
    assert isinstance(identity, VerifiedAppleIdentity)
    assert identity.sub == "apple-sub-happy-path"
    assert identity.email == "teen@example.com"
    assert identity.email_verified is True


def test_valid_token_email_verified_string_claim_coerced(mock_jwks, apple_signing_key):
    """Apple sometimes sends email_verified as the string 'true'/'false'."""
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        nonce_claim=_hashed_nonce_claim(raw_nonce),
        payload_override={"email_verified": "true"},
    )
    identity = verify_apple_identity_token(token, raw_nonce)
    assert identity.email_verified is True


# --- 2. Tampered signature --------------------------------------------------

def test_tampered_signature_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    wrong_key = _generate_ec_keypair()
    # Signed with a DIFFERENT private key than the one published in the
    # mocked JWKS under this kid — signature verification must fail.
    token = _build_token(
        signing_key=wrong_key,
        kid=TOKEN_KID,
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


def test_corrupted_signature_bytes_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    header, payload, sig = token.split(".")
    corrupted_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    tampered = f"{header}.{payload}.{corrupted_sig}"
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(tampered, raw_nonce)


# --- 3. alg=none explicitly rejected ---------------------------------------

def test_alg_none_is_rejected(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    now = int(time.time())
    payload = {
        "iss": apple_auth.APPLE_ISSUER,
        "aud": BUNDLE_ID,
        "exp": now + 600,
        "iat": now,
        "sub": "apple-sub-none-alg",
        "email": "teen@example.com",
        "email_verified": True,
        "nonce": _hashed_nonce_claim(raw_nonce),
    }
    unsigned_token = jwt.encode(payload, key=None, algorithm="none", headers={"kid": TOKEN_KID})
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(unsigned_token, raw_nonce)


# --- 4. Algorithm outside the configured allowlist --------------------------

def test_algorithm_outside_configured_allowlist_is_rejected(monkeypatch, mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        alg="ES256",
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    # A genuinely valid ES256 token, but the deployment's confirmed allowlist
    # (per A.5) doesn't happen to include ES256 in this test — must fail
    # closed rather than accept an algorithm outside the configured set.
    monkeypatch.setenv("APPLE_ALLOWED_ALGORITHMS", "RS256")
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


# --- 5. Unknown kid ----------------------------------------------------------

def test_unknown_kid_is_rejected(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        kid="some-kid-not-in-jwks",
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


# --- 6. Wrong issuer ----------------------------------------------------------

def test_wrong_issuer_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        iss="https://evil.example.com",
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


# --- 7. Wrong audience --------------------------------------------------------

def test_wrong_audience_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        aud="com.someoneelse.app",
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


# --- 8. Expired token ---------------------------------------------------------

def test_expired_token_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        exp_delta=-600,
        nonce_claim=_hashed_nonce_claim(raw_nonce),
    )
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


# --- 9. Nonce mismatch ---------------------------------------------------------

def test_nonce_mismatch_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(
        signing_key=apple_signing_key,
        nonce_claim=_hashed_nonce_claim("a-completely-different-nonce"),
    )
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


def test_missing_nonce_claim_fails(mock_jwks, apple_signing_key):
    raw_nonce = _raw_nonce()
    token = _build_token(signing_key=apple_signing_key, nonce_claim=None)
    with pytest.raises(AppleVerificationError):
        verify_apple_identity_token(token, raw_nonce)


def test_apple_nonce_matches_unit():
    raw_nonce = "abc123"
    good_claim = hashlib.sha256(raw_nonce.encode()).hexdigest()
    assert _apple_nonce_matches(raw_nonce, good_claim) is True
    assert _apple_nonce_matches(raw_nonce, "wrong-claim") is False
    assert _apple_nonce_matches(raw_nonce, None) is False
    assert _apple_nonce_matches(raw_nonce, raw_nonce) is False  # not verbatim by current placeholder


# --- 10. _build_apple_client_secret() ------------------------------------

def test_build_apple_client_secret_matches_documented_contract():
    secret = _build_apple_client_secret()

    header = jwt.get_unverified_header(secret)
    assert header["alg"] == "ES256"
    assert header["kid"] == KEY_ID

    payload = jwt.decode(secret, options={"verify_signature": False})
    assert payload["iss"] == TEAM_ID
    assert payload["sub"] == BUNDLE_ID
    assert payload["aud"] == apple_auth.APPLE_ISSUER
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)

    six_months_seconds = 60 * 60 * 24 * 183  # generous upper bound on "6 months"
    assert payload["exp"] - payload["iat"] <= six_months_seconds
    assert payload["exp"] > payload["iat"]


def test_build_apple_client_secret_is_fresh_each_call():
    """Never a stored static long-lived string -- each call re-signs with a
    fresh iat, so two calls a moment apart produce different tokens."""
    first = _build_apple_client_secret()
    time.sleep(1.05)
    second = _build_apple_client_secret()
    assert first != second
    payload1 = jwt.decode(first, options={"verify_signature": False})
    payload2 = jwt.decode(second, options={"verify_signature": False})
    assert payload2["iat"] >= payload1["iat"]


# --- 11. exchange_authorization_code_for_refresh_token ---------------------

class _FakeResponse:
    def __init__(self, status_code, json_body):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        return self._json_body


def _mock_exchange_request(monkeypatch, response: "_FakeResponse | Exception"):
    async def _fake(data):
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(apple_auth, "_apple_token_exchange_request", _fake)


def _make_exchange_id_token(*, sub: str, aud: str = BUNDLE_ID) -> str:
    # A lightweight, unsigned-is-fine-for-this-claims-only-read stand-in for
    # Apple's own id_token in the /auth/token response -- matches how
    # exchange_authorization_code_for_refresh_token reads it (verify_signature=False).
    now = int(time.time())
    return jwt.encode(
        {"iss": apple_auth.APPLE_ISSUER, "aud": aud, "sub": sub, "iat": now, "exp": now + 600},
        key="unused-for-this-unsigned-style-token",
        algorithm="HS256",
    )


def test_successful_exchange_returns_refresh_token(monkeypatch):
    expected_sub = "apple-sub-exchange-001"
    id_token = _make_exchange_id_token(sub=expected_sub)
    _mock_exchange_request(
        monkeypatch,
        _FakeResponse(200, {"refresh_token": "real-refresh-token-value", "id_token": id_token}),
    )
    result = asyncio.run(
        exchange_authorization_code_for_refresh_token("auth-code-abc", expected_sub=expected_sub)
    )
    assert result == "real-refresh-token-value"


def test_exchange_subject_mismatch_rejected_and_no_token_returned(monkeypatch):
    id_token = _make_exchange_id_token(sub="apple-sub-DIFFERENT")
    _mock_exchange_request(
        monkeypatch,
        _FakeResponse(200, {"refresh_token": "should-never-be-returned", "id_token": id_token}),
    )
    with pytest.raises(AppleVerificationError):
        asyncio.run(
            exchange_authorization_code_for_refresh_token(
                "auth-code-abc", expected_sub="apple-sub-expected"
            )
        )


def test_exchange_audience_mismatch_rejected(monkeypatch):
    expected_sub = "apple-sub-aud-mismatch"
    id_token = _make_exchange_id_token(sub=expected_sub, aud="com.someoneelse.app")
    _mock_exchange_request(
        monkeypatch,
        _FakeResponse(200, {"refresh_token": "should-never-be-returned", "id_token": id_token}),
    )
    with pytest.raises(AppleVerificationError):
        asyncio.run(
            exchange_authorization_code_for_refresh_token("auth-code-abc", expected_sub=expected_sub)
        )


def test_exchange_http_error_status_rejected(monkeypatch):
    _mock_exchange_request(monkeypatch, _FakeResponse(400, {"error": "invalid_grant"}))
    with pytest.raises(AppleVerificationError):
        asyncio.run(
            exchange_authorization_code_for_refresh_token("auth-code-abc", expected_sub="any-sub")
        )


def test_exchange_transport_failure_rejected(monkeypatch):
    import httpx as httpx_mod
    _mock_exchange_request(monkeypatch, httpx_mod.ConnectError("boom"))
    with pytest.raises(AppleVerificationError):
        asyncio.run(
            exchange_authorization_code_for_refresh_token("auth-code-abc", expected_sub="any-sub")
        )


def test_exchange_missing_refresh_token_in_response_rejected(monkeypatch):
    id_token = _make_exchange_id_token(sub="apple-sub-no-refresh")
    _mock_exchange_request(
        monkeypatch,
        _FakeResponse(200, {"id_token": id_token}),  # no refresh_token key at all
    )
    with pytest.raises(AppleVerificationError):
        asyncio.run(
            exchange_authorization_code_for_refresh_token(
                "auth-code-abc", expected_sub="apple-sub-no-refresh"
            )
        )


# --- 12. Missing configuration -> clear config errors, never silent defaults --

def test_missing_allowed_algorithms_raises_config_error(monkeypatch):
    monkeypatch.delenv("APPLE_ALLOWED_ALGORITHMS", raising=False)
    with pytest.raises(Exception):
        _apple_allowed_algorithms()


def test_allowed_algorithms_never_silently_includes_none(monkeypatch):
    monkeypatch.setenv("APPLE_ALLOWED_ALGORITHMS", "none")
    with pytest.raises(Exception):
        _apple_allowed_algorithms()


def test_missing_bundle_id_raises_config_error(monkeypatch, mock_jwks, apple_signing_key):
    monkeypatch.delenv("APPLE_BUNDLE_ID", raising=False)
    raw_nonce = _raw_nonce()
    token = _build_token(signing_key=apple_signing_key, nonce_claim=_hashed_nonce_claim(raw_nonce))
    with pytest.raises(Exception):
        verify_apple_identity_token(token, raw_nonce)


def test_missing_team_id_raises_config_error(monkeypatch):
    monkeypatch.delenv("APPLE_TEAM_ID", raising=False)
    with pytest.raises(Exception):
        _build_apple_client_secret()


def test_missing_key_id_raises_config_error(monkeypatch):
    monkeypatch.delenv("APPLE_KEY_ID", raising=False)
    with pytest.raises(Exception):
        _build_apple_client_secret()


def test_missing_private_key_raises_config_error(monkeypatch):
    monkeypatch.delenv("APPLE_PRIVATE_KEY", raising=False)
    with pytest.raises(Exception):
        _build_apple_client_secret()


def test_missing_bundle_id_raises_config_error_for_exchange(monkeypatch):
    monkeypatch.delenv("APPLE_BUNDLE_ID", raising=False)
    with pytest.raises(Exception):
        asyncio.run(
            exchange_authorization_code_for_refresh_token("auth-code-abc", expected_sub="any-sub")
        )
