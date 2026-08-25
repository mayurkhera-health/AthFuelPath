"""AES-256-GCM encryption for stored provider (Apple) refresh tokens —
auth v2.1 Phase 6, Part A.7.

Why AES-256-GCM via `cryptography`'s AESGCM: it's an AEAD (authenticated
encryption with associated data) construction, so a modified ciphertext or a
mismatched nonce fails verification loudly (raises) rather than silently
decrypting into corrupted-but-plausible-looking data — the same tamper-
detection property OTP/session tokens in this codebase already lean on
elsewhere, just applied here to data at rest instead of a bearer token in
transit. `cryptography` is already a backend dependency (see
requirements.txt: cryptography==48.0.0) — no new library is introduced.

Key management: PROVIDER_CREDENTIAL_ENCRYPTION_KEY is a dedicated secret,
separate from APP_SESSION_SECRET, delivered via the same environment-
variable-backed-by-Secret-Manager mechanism this codebase already uses for
other secrets (see api/services/session_auth.py's `_secret()`). Unlike
APP_SESSION_SECRET (an arbitrary-length string used directly as an HMAC key),
AESGCM requires an exact 256-bit (32-byte) key. This codebase has no existing
precedent for passing raw fixed-length key bytes through an environment
variable, so — per Phase 6 plan A.7 — the env var value is base64-encoded
externally and base64-decoded here at read time, the standard, safe way to
carry arbitrary binary key material through a text-only env var. The decoded
result must be exactly 32 bytes; anything else raises immediately rather than
producing broken ciphertext with a silently-wrong key length.

Hard constraint (Phase 6 plan A.7, restated): this module must never log —
via print, logger.*, or an exception message — the plaintext refresh token,
the ciphertext, the nonce, or the key. Errors below only ever describe *what
configuration is wrong*, never any of that material.
"""
import base64
import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_LENGTH_BYTES = 32  # AES-256
_NONCE_LENGTH_BYTES = 12  # 96 bits, AESGCM's recommended/standard nonce size


class ProviderCredentialCryptoError(Exception):
    """Raised when PROVIDER_CREDENTIAL_ENCRYPTION_KEY is missing, malformed,
    or the wrong length. Never raised for tamper-detection failures — those
    propagate as `cryptography`'s own InvalidTag so the AEAD failure mode
    stays distinguishable from a configuration failure mode."""


def _key() -> bytes:
    raw_env = os.environ.get("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", "")
    if not raw_env:
        raise ProviderCredentialCryptoError(
            "PROVIDER_CREDENTIAL_ENCRYPTION_KEY env var is not set — provider "
            "credentials cannot be encrypted or decrypted until this is configured."
        )
    try:
        key = base64.b64decode(raw_env, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProviderCredentialCryptoError(
            "PROVIDER_CREDENTIAL_ENCRYPTION_KEY is not valid base64."
        ) from exc
    if len(key) != _KEY_LENGTH_BYTES:
        raise ProviderCredentialCryptoError(
            "PROVIDER_CREDENTIAL_ENCRYPTION_KEY must decode to exactly "
            f"{_KEY_LENGTH_BYTES} bytes (AES-256); decoded length was "
            f"{len(key)} bytes."
        )
    return key


def encrypt_refresh_token(plaintext: str) -> tuple[bytes, bytes]:
    """Returns (ciphertext, nonce). Uses AESGCM with
    PROVIDER_CREDENTIAL_ENCRYPTION_KEY (32 raw bytes, base64-encoded in the
    env var — see module docstring). A fresh random 12-byte nonce is
    generated per call via os.urandom(12) — never reused for the same key."""
    aesgcm = AESGCM(_key())
    nonce = os.urandom(_NONCE_LENGTH_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_refresh_token(ciphertext: bytes, nonce: bytes) -> str:
    """Decrypts; raises on any tampering (AEAD tag mismatch) rather than
    silently returning corrupted data. Propagates cryptography.exceptions.
    InvalidTag on a bad tag/wrong nonce/wrong key, and
    ProviderCredentialCryptoError on missing/malformed configuration —
    including a wrong-length nonce, checked explicitly here rather than left
    to raise AESGCM's own bare ValueError, which would be a third,
    undocumented exception type outside this module's two-exception
    contract."""
    if len(nonce) != _NONCE_LENGTH_BYTES:
        raise ProviderCredentialCryptoError(
            f"nonce must be exactly {_NONCE_LENGTH_BYTES} bytes; got {len(nonce)} bytes."
        )
    aesgcm = AESGCM(_key())
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


__all__ = [
    "ProviderCredentialCryptoError",
    "encrypt_refresh_token",
    "decrypt_refresh_token",
]
