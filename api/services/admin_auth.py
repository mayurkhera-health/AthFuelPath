"""
Admin Module auth — minimal single-user (founder) protection.

No JWT/session library is used anywhere in this codebase (only hashlib), so this
mints a self-contained HMAC-signed token with stdlib primitives — no new
dependency. Token shape:  base64url(payload_json).base64url(hmac_sha256(payload))
Payload: {"sub": "admin", "exp": <unix seconds>}.

Config (all via os.getenv, graceful when unset):
  ADMIN_PASSWORD        — the founder's login password (login is impossible if unset)
  ADMIN_SESSION_SECRET  — HMAC signing key (tokens can't be minted/verified if unset)

Also provides:
  require_admin   — FastAPI dependency; apply to every /api/admin route
  check_rate_limit / record_failed_login  — in-memory login throttle
  write_audit     — append a row to admin_audit_log for every admin mutation
"""

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime

from fastapi import Header, HTTPException

from api.database import get_conn

TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24h

# ── In-memory login rate limiter ────────────────────────────────────────────
# Single-process app (one Fly machine, min_machines_running = 1), so a module
# dict is sufficient. Keyed by client IP. Resets on redeploy — acceptable.
_MAX_FAILS = 5
_WINDOW_SECONDS = 15 * 60
_LOCKOUT_SECONDS = 15 * 60
_failed_logins: dict[str, list[float]] = {}


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret() -> str:
    return os.getenv("ADMIN_SESSION_SECRET", "")


def password_configured() -> bool:
    return bool(os.getenv("ADMIN_PASSWORD"))


def verify_password(candidate: str) -> bool:
    """Constant-time compare against ADMIN_PASSWORD. False if the secret is unset."""
    expected = os.getenv("ADMIN_PASSWORD", "")
    if not expected:
        return False
    return hmac.compare_digest(candidate or "", expected)


def mint_token() -> str:
    secret = _secret()
    if not secret:
        raise HTTPException(500, "Admin session secret is not configured.")
    payload = {"sub": "admin", "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), payload_b, hashlib.sha256).digest()
    return f"{_b64u(payload_b)}.{_b64u(sig)}"


def verify_token(token: str) -> bool:
    secret = _secret()
    if not secret or not token or "." not in token:
        return False
    try:
        payload_part, sig_part = token.split(".", 1)
        payload_b = _b64u_decode(payload_part)
        expected_sig = hmac.new(secret.encode(), payload_b, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64u_decode(sig_part), expected_sig):
            return False
        payload = json.loads(payload_b)
        return payload.get("sub") == "admin" and int(payload.get("exp", 0)) > time.time()
    except Exception:
        return False


# ── Rate limiting ───────────────────────────────────────────────────────────
def _prune(ip: str) -> list[float]:
    now = time.time()
    hits = [t for t in _failed_logins.get(ip, []) if now - t < _WINDOW_SECONDS]
    _failed_logins[ip] = hits
    return hits


def check_rate_limit(ip: str) -> None:
    """Raise 429 if this IP is locked out from too many recent failed logins."""
    hits = _prune(ip)
    if len(hits) >= _MAX_FAILS and time.time() - hits[-1] < _LOCKOUT_SECONDS:
        raise HTTPException(429, "Too many failed attempts. Try again later.")


def record_failed_login(ip: str) -> None:
    _prune(ip)
    _failed_logins.setdefault(ip, []).append(time.time())


def clear_failed_logins(ip: str) -> None:
    _failed_logins.pop(ip, None)


# ── Dependency ──────────────────────────────────────────────────────────────
def require_admin(authorization: str = Header(None)) -> bool:
    """FastAPI dependency guarding every /api/admin route. Expects
    `Authorization: Bearer <token>`. Raises 401 otherwise."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Admin authentication required.")
    token = authorization[7:].strip()
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired admin session.")
    return True


# ── Audit log ───────────────────────────────────────────────────────────────
# Single-admin (founder) product: there is no per-user identity beyond the
# password, so the actor is a fixed super-admin. These fill the NOT NULL actor_*
# columns of the shared admin_audit_log table. actor_id=1 matches the historical
# AthFuelPath-Admin rows on the production volume.
ACTOR_ID = 1
ACTOR_EMAIL = os.getenv("ADMIN_EMAIL", "admin")
ACTOR_ROLE = "super_admin"


def write_audit(action: str, target_type: str, target_id, detail: dict | None = None,
                conn=None, actor_id: int | None = None, actor_email: str | None = None,
                actor_role: str | None = None) -> None:
    """Append one row to admin_audit_log. The `detail` dict (cascade counts,
    changed fields) is stored as JSON in after_state. Pass an existing `conn` to
    enlist the audit write in the caller's transaction (used by cascade delete so
    the log row is atomic with the delete); otherwise a fresh connection is opened
    and committed here.

    actor_id/actor_email/actor_role default to the fixed super-admin actor
    (this table originated as admin-panel-only) — pass all three to attribute
    a row to a real, non-admin actor instead, e.g. a parent-initiated action
    reached via a normal parent session, not the admin panel."""
    after_state = json.dumps(detail or {}, default=str)
    created_at = datetime.utcnow().isoformat()
    own = conn is None
    if own:
        conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO admin_audit_log "
            "(actor_id, actor_email, actor_role, action, target_type, target_id, after_state, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (actor_id if actor_id is not None else ACTOR_ID,
             actor_email if actor_email is not None else ACTOR_EMAIL,
             actor_role if actor_role is not None else ACTOR_ROLE,
             action, target_type, target_id, after_state, created_at),
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
