"""
Shared OTP issue/verify core — the race-safe, attempt-limited logic
originally built (and hardened against a TOCTOU lockout race) in
api/routes/parents.py's request-otp/verify-otp during auth v2.1 Phase 1.

Extracted here in Phase 2 so /api/auth/email/request and /api/auth/email/verify
can reuse it without duplicating the atomic UPDATE-based matching/lockout SQL —
there must be exactly one place that logic lives, since it's the part that was
actually security-reviewed and fixed for a real race condition.

Neither function here does any parent/account lookup or gating — that stays
the caller's responsibility (parents.py's routes require an existing parent
before calling in; /api/auth/email/request does not, by design — see
api/routes/auth.py).
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from api.database import get_conn
from api.services.email import send_otp_email

_MAX_OTP_ATTEMPTS = 5
_RESEND_COOLDOWN_SECONDS = 60
_EXPIRY_MINUTES = 10


class OtpRateLimited(Exception):
    """A code was already issued for this email in the last 60 seconds."""


class OtpDeliveryFailed(Exception):
    """Gmail delivery failed; the newly-inserted OTP row has already been
    deleted (it must not remain valid, count toward the cooldown, or sit
    around as an extra outstanding row) before this is raised."""


def issue_otp(email: str, *, parent_id: int | None = None, send_fn=None) -> None:
    """
    Issue a new OTP for `email` (already trimmed/lowercased by the caller).
    `parent_id` is optional metadata only — it is not required for a later
    verify_otp() call to succeed, since matching is by email + code_hash,
    never by parent_id. Pass None when the email has no known account yet.

    `send_fn` lets a caller thread through its own (patchable) reference to
    the mailer — e.g. parents.py imports send_otp_email into its own module
    namespace so `unittest.mock.patch("api.routes.parents.send_otp_email", ...)`
    keeps working post-extraction; that patched name has to actually be the
    thing invoked, not just present as an unused import. Defaults to this
    module's own send_otp_email for callers with no such requirement.

    Raises OtpRateLimited or OtpDeliveryFailed; callers map these to their
    own HTTP responses. Returns None on success (the caller decides what
    "success" means in its own response body).
    """
    _send = send_fn or send_otp_email
    conn = get_conn()
    try:
        # Rate limit: block if a code was issued in the last 60 seconds.
        # created_at is DB-generated via sqlite_now() ('YYYY-MM-DD HH:MI:SS',
        # no "T", no fractional seconds) — cutoff must match that exact
        # format, not .isoformat(), or the lexicographic comparison silently
        # never matches (see db/postgres/001_baseline.sql's sqlite_now()).
        cutoff = (datetime.utcnow() - timedelta(seconds=_RESEND_COOLDOWN_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
        recent = conn.execute(
            "SELECT id FROM otp_codes WHERE email = %s AND created_at > %s AND used = 0",
            (email, cutoff),
        ).fetchone()
        if recent:
            raise OtpRateLimited()

        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        expires_at = (datetime.utcnow() + timedelta(minutes=_EXPIRY_MINUTES)).isoformat()

        inserted = conn.execute(
            "INSERT INTO otp_codes (parent_id, email, code_hash, expires_at) VALUES (%s, %s, %s, %s) RETURNING id",
            (parent_id, email, code_hash, expires_at),
        ).fetchone()
        conn.commit()

        if not _send(email, code):
            conn.execute("DELETE FROM otp_codes WHERE id = %s", (dict(inserted)["id"],))
            conn.commit()
            raise OtpDeliveryFailed()
    finally:
        conn.close()


def verify_otp(email: str, code: str) -> bool:
    """
    Verify `code` for `email` (already trimmed/lowercased and stripped by
    the caller). Returns True iff a valid, unexpired, not-locked-out row
    matched and was atomically marked used + consumed_at in this call.
    Returns False for a wrong/expired/locked/nonexistent code — never
    raises for those cases.

    Single-use: the matching UPDATE's own WHERE used = 0 means a row that
    already succeeded once can never match again. Atomic: both the success
    path and the wrong-guess attempts-increment are each one UPDATE
    statement (no separate read-then-write), so Postgres's row-level
    locking prevents concurrent requests from racing past the 5-attempt
    lockout or double-consuming the same code.
    """
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    now = datetime.utcnow().isoformat()

    conn = get_conn()
    try:
        success_row = conn.execute(
            """UPDATE otp_codes SET used = 1, consumed_at = %s
               WHERE email = %s AND used = 0 AND expires_at > %s AND code_hash = %s AND attempts < %s
               RETURNING id""",
            (now, email, now, code_hash, _MAX_OTP_ATTEMPTS),
        ).fetchone()
        conn.commit()

        if success_row:
            return True

        conn.execute(
            """UPDATE otp_codes SET attempts = attempts + 1
               WHERE email = %s AND used = 0 AND expires_at > %s AND attempts < %s""",
            (email, now, _MAX_OTP_ATTEMPTS),
        )
        conn.commit()
        return False
    finally:
        conn.close()
