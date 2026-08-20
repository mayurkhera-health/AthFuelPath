"""Parent/athlete session tokens — stateless, HMAC-signed bearer tokens.

Mirrors the crypto already used for TeamCoach (teamcoach_auth_service.py) and
admin (admin_auth.py): stdlib-only HMAC-SHA256 over a JSON payload, no new DB
table. This does NOT add a password — email-only login is unchanged. It closes
a separate gap: once a request arrives, the server had no way to know who was
actually asking, so every athlete_id/parent_id in a URL was trusted as-is
(BOLA). A token minted at login now lets routes verify the caller actually
owns the record they're trying to read or write.

Rolling TTL: verify_session_token() alone never extends anything; routes that
want a sliding session call mint_session_token() again with the same identity
and return the refreshed token, which is what the /login and revalidation
endpoints do.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Header, HTTPException

TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days, refreshed on each successful login/restore


def _secret() -> str:
    val = os.getenv("APP_SESSION_SECRET", "")
    if not val:
        raise RuntimeError(
            "APP_SESSION_SECRET env var is not set — session tokens cannot be "
            "minted or verified until this is configured."
        )
    return val


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def mint_session_token(
    *, role: str, parent_id: Optional[int] = None, athlete_id: Optional[int] = None,
    ttl_seconds: int = TOKEN_TTL_SECONDS,
) -> str:
    """role is 'parent' or 'athlete'. A parent token carries parent_id (and may
    carry the currently-selected athlete_id, informational only — ownership
    checks always re-verify against the DB, never trust athlete_id alone for a
    parent token). An athlete token carries athlete_id and that athlete's own
    parent_id, so ownership checks never need a DB round trip for the common case."""
    if role not in ("parent", "athlete"):
        raise ValueError(f"Invalid role for session token: {role!r}")
    payload = {
        "role": role,
        "parent_id": parent_id,
        "athlete_id": athlete_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(_secret().encode(), payload_b, hashlib.sha256).digest()
    return f"{_b64u(payload_b)}.{_b64u(sig)}"


def verify_session_token(token: str) -> Optional[dict]:
    """Return the payload dict if valid and unexpired; None otherwise. Never raises."""
    try:
        secret_val = os.getenv("APP_SESSION_SECRET", "")
        if not secret_val or not token or "." not in token:
            return None
        payload_part, sig_part = token.split(".", 1)
        payload_b = _b64u_decode(payload_part)
        expected_sig = hmac.new(secret_val.encode(), payload_b, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64u_decode(sig_part), expected_sig):
            return None
        payload = json.loads(payload_b)
        if int(payload.get("exp", 0)) <= time.time():
            return None
        if payload.get("role") not in ("parent", "athlete"):
            return None
        return payload
    except Exception:
        return None


class SessionIdentity:
    """Resolved, verified caller identity for the current request."""

    def __init__(self, role: str, parent_id: Optional[int], athlete_id: Optional[int]):
        self.role = role
        self.parent_id = parent_id
        self.athlete_id = athlete_id


def require_session(authorization: str = Header(None)) -> SessionIdentity:
    """FastAPI dependency — extract and verify the bearer session token.
    Raises 401 if missing, malformed, or expired."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Session required.")
    payload = verify_session_token(authorization[7:].strip())
    if not payload:
        raise HTTPException(401, "Invalid or expired session.")
    return SessionIdentity(payload["role"], payload.get("parent_id"), payload.get("athlete_id"))


def assert_owns_athlete(identity: SessionIdentity, athlete_id: int, conn) -> None:
    """403 unless the caller's session is linked to this athlete: either the
    caller IS this athlete, or the caller is the parent who owns this athlete.
    404 if the athlete_id doesn't exist at all (don't leak existence via a 403
    vs 404 distinction beyond what the route already does)."""
    if identity.role == "athlete":
        if identity.athlete_id == athlete_id:
            return
        raise HTTPException(403, "Not authorized for this athlete.")
    row = conn.execute("SELECT parent_id FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Athlete not found.")
    if dict(row)["parent_id"] != identity.parent_id:
        raise HTTPException(403, "Not authorized for this athlete.")


def assert_owns_parent(identity: SessionIdentity, parent_id: int) -> None:
    """403 unless the caller's session IS this parent. Athlete tokens never own
    a parent record."""
    if identity.role != "parent" or identity.parent_id != parent_id:
        raise HTTPException(403, "Not authorized for this parent account.")
