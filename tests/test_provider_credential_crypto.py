"""Unit tests for api/services/provider_credential_crypto.py — AES-256-GCM
encryption/decryption of Apple refresh tokens (auth v2.1 Phase 6, Part A.7).

Proves: round-trip correctness, genuinely-random per-call nonces, AEAD
tamper-detection (ciphertext and nonce), and fail-closed behavior when
PROVIDER_CREDENTIAL_ENCRYPTION_KEY is missing or the wrong length.
"""
import base64

import pytest
from cryptography.exceptions import InvalidTag

from api.services import provider_credential_crypto as crypto

# 32 raw bytes, base64-encoded — matches the module's documented env-var
# encoding (base64-encoded 32 raw bytes, since APP_SESSION_SECRET offers no
# raw-bytes-through-env precedent to follow instead).
TEST_KEY_B64 = base64.b64encode(b"0" * 32).decode()


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", TEST_KEY_B64)


def test_round_trip_returns_exact_original_plaintext():
    plaintext = "a-real-looking-apple-refresh-token-value-1234567890"
    ciphertext, nonce = crypto.encrypt_refresh_token(plaintext)
    assert crypto.decrypt_refresh_token(ciphertext, nonce) == plaintext


def test_round_trip_empty_string_plaintext():
    ciphertext, nonce = crypto.encrypt_refresh_token("")
    assert crypto.decrypt_refresh_token(ciphertext, nonce) == ""


def test_two_encryptions_of_same_plaintext_differ_in_ciphertext_and_nonce():
    plaintext = "same-plaintext-both-times"
    ciphertext1, nonce1 = crypto.encrypt_refresh_token(plaintext)
    ciphertext2, nonce2 = crypto.encrypt_refresh_token(plaintext)
    assert nonce1 != nonce2
    assert ciphertext1 != ciphertext2
    # Both must still decrypt correctly despite differing.
    assert crypto.decrypt_refresh_token(ciphertext1, nonce1) == plaintext
    assert crypto.decrypt_refresh_token(ciphertext2, nonce2) == plaintext


def test_tampered_ciphertext_byte_raises_instead_of_returning_garbage():
    plaintext = "another-refresh-token-value"
    ciphertext, nonce = crypto.encrypt_refresh_token(plaintext)
    tampered = bytearray(ciphertext)
    tampered[0] ^= 0xFF  # flip one byte
    with pytest.raises(InvalidTag):
        crypto.decrypt_refresh_token(bytes(tampered), nonce)


def test_tampered_nonce_raises_instead_of_returning_garbage():
    plaintext = "yet-another-refresh-token-value"
    ciphertext, nonce = crypto.encrypt_refresh_token(plaintext)
    wrong_nonce = bytearray(nonce)
    wrong_nonce[0] ^= 0xFF  # flip one byte of the nonce actually used (still 12 bytes long)
    with pytest.raises(InvalidTag):
        crypto.decrypt_refresh_token(ciphertext, bytes(wrong_nonce))


def test_wrong_length_nonce_raises_config_error_not_bare_value_error():
    plaintext = "a-refresh-token-value"
    ciphertext, nonce = crypto.encrypt_refresh_token(plaintext)
    too_short_nonce = nonce[:8]
    with pytest.raises(crypto.ProviderCredentialCryptoError):
        crypto.decrypt_refresh_token(ciphertext, too_short_nonce)


def test_missing_key_env_var_raises_clear_error_on_encrypt(monkeypatch):
    monkeypatch.delenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(crypto.ProviderCredentialCryptoError):
        crypto.encrypt_refresh_token("some-plaintext")


def test_missing_key_env_var_raises_clear_error_on_decrypt(monkeypatch):
    # Encrypt first (with key set via the autouse fixture), then remove the
    # key and confirm decrypt also fails closed rather than using a default.
    ciphertext, nonce = crypto.encrypt_refresh_token("some-plaintext")
    monkeypatch.delenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(crypto.ProviderCredentialCryptoError):
        crypto.decrypt_refresh_token(ciphertext, nonce)


def test_wrong_length_key_raises_clear_error(monkeypatch):
    short_key_b64 = base64.b64encode(b"too-short").decode()
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", short_key_b64)
    with pytest.raises(crypto.ProviderCredentialCryptoError):
        crypto.encrypt_refresh_token("some-plaintext")
