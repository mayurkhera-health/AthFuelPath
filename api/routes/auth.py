"""
Phase 1 — Unified auth endpoint.
Originally resolved parent OR athlete from a single email via
POST /login; that route was retired in auth v2.1 Phase 4 (email-only
session issuance removed) in favor of the OTP-verified /email/request +
/email/verify flow below. Keeps /api/athletes/* intact for backward compat.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from api.database import get_conn
from api.services import login_alerts
from api.services.session_auth import mint_session_token, require_session
from api.services.otp_auth import issue_otp, verify_otp as verify_otp_code, OtpRateLimited, OtpDeliveryFailed

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str


class AthleteCreateLoginRequest(BaseModel):
    email: str          # athlete's own email (becomes their login)
    parent_email: str   # parent's email — the gate


class AthleteClaimLookupRequest(BaseModel):
    parent_email: str


class EmailAuthRequest(BaseModel):
    email: str


class EmailAuthVerify(BaseModel):
    email: str
    code: str


@router.post("/email/request")
def email_auth_request(data: EmailAuthRequest):
    """
    Phase 2 — neutral, non-enumerating OTP request. There is exactly one
    code path here regardless of whether an AthFuelPath account exists for
    this email: no parent/account lookup happens before issuing the code.
    That is what makes this non-enumerating, not just a same-looking JSON
    body — a caller cannot distinguish "account exists" from "no account"
    by status code, response shape, or which code path ran.
    """
    email = data.email.strip().lower()
    try:
        issue_otp(email, parent_id=None)
    except OtpRateLimited:
        raise HTTPException(429, "A code was already sent. Please wait 60 seconds before requesting another.")
    except OtpDeliveryFailed:
        raise HTTPException(502, "Could not send the code right now. Please try again shortly.")
    return {"message": "If that email is associated with an AthFuelPath account, a 6-digit code has been sent."}


@router.post("/email/verify")
def email_auth_verify(data: EmailAuthVerify, background_tasks: BackgroundTasks):
    """
    Phase 2 — verify proof of email ownership, then resolve to an existing
    account and issue a real session. A session is issued ONLY after
    verify_otp_code succeeds — email knowledge alone (an unverified POST to
    this endpoint) never issues one; see the 401 paths below, none of which
    include a session_token.

    If the verified email has no existing account, this reports that
    plainly instead of guessing/creating one — creating an account here
    would be Phase 7 (verified signup), out of scope for Phase 2. Reporting
    it is safe: the caller just proved ownership of exactly this email, so
    telling them whether THEIR OWN email has an account is not an
    enumeration leak (unlike /email/request, which must stay neutral to an
    unverified caller).

    On a successful parent login, this also stamps last_login_at and
    schedules a best-effort founder login-alert (login_alerts.notify_login)
    as a background task — ported from the now-deleted unified_login
    (auth v2.1 Phase 4).
    """
    email = data.email.strip().lower()

    if not verify_otp_code(email, data.code.strip()):
        raise HTTPException(401, "Invalid or expired code. Please request a new one.")

    conn = get_conn()
    try:
        # 1. Parent? (same precedence as unified_login — parents checked first)
        parent = conn.execute(
            "SELECT * FROM parents WHERE lower(email) = %s", (email,)
        ).fetchone()
        if parent:
            parent_d = dict(parent)
            athletes = [dict(a) for a in conn.execute(
                "SELECT * FROM athletes WHERE parent_id = %s", (parent_d["id"],)
            ).fetchall()]

            # Beta login alert (best-effort; backgrounded so it never slows the
            # response, never blocks login if it fails). Ported from the now-
            # deleted unified_login (auth v2.1 Phase 4) — this is the only
            # place a parent login fires this alert now that email-only
            # /api/auth/login no longer exists.
            try:
                is_new = not parent_d.get("last_login_at")
                conn.execute(
                    "UPDATE parents SET last_login_at = %s WHERE id = %s",
                    (datetime.utcnow().isoformat(), parent_d["id"]),
                )
                conn.commit()
                background_tasks.add_task(
                    login_alerts.notify_login, parent_d,
                    is_new=is_new, athlete_hint=login_alerts.athlete_hint(athletes),
                )
            except Exception:
                logger.warning("login alert scheduling failed (non-blocking)", exc_info=True)

            token = mint_session_token(role="parent", parent_id=parent_d["id"])
            return {"role": "parent", "parent": parent_d, "athletes": athletes, "session_token": token}

        # 2. Athlete?
        al = conn.execute(
            "SELECT * FROM athlete_logins WHERE lower(email) = %s", (email,)
        ).fetchone()
        if al:
            athlete = conn.execute(
                "SELECT * FROM athletes WHERE id = %s", (dict(al)["athlete_id"],)
            ).fetchone()
            if not athlete:
                raise HTTPException(500, "Athlete profile not found.")
            athlete_d = dict(athlete)
            token = mint_session_token(
                role="athlete", athlete_id=athlete_d["id"], parent_id=athlete_d["parent_id"],
            )
            return {"role": "athlete", "athlete": athlete_d, "session_token": token}

        # 3. Verified, but no account exists — safe to say so (see docstring).
        return {"verified": True, "has_account": False}
    finally:
        conn.close()


@router.get("/session")
def get_session(identity=Depends(require_session)):
    """
    Phase 3 — restore an existing session from the bearer token alone. No
    email is accepted or consulted anywhere in this handler; require_session
    (401 on missing/malformed/expired) is the only gate. Mints no new token
    — the client already has one and keeps using it; this endpoint only
    re-confirms it's still good and returns fresh account context.

    See api/services/session_auth.py's "Rolling TTL" module docstring — this
    endpoint is the one documented exception to that pattern, by design.
    """
    conn = get_conn()
    try:
        if identity.role == "parent":
            parent = conn.execute(
                "SELECT * FROM parents WHERE id = %s", (identity.parent_id,)
            ).fetchone()
            if not parent:
                # Token is well-formed and unexpired, but the account behind
                # it is gone (e.g. deleted) — treat as an invalid session,
                # not a permissions problem, so the client's existing
                # 401-clears-session handling applies.
                raise HTTPException(401, "Session no longer valid.")
            parent_d = dict(parent)
            athletes = [dict(a) for a in conn.execute(
                "SELECT * FROM athletes WHERE parent_id = %s", (parent_d["id"],)
            ).fetchall()]
            return {"role": "parent", "parent": parent_d, "athletes": athletes}

        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = %s", (identity.athlete_id,)
        ).fetchone()
        if not athlete:
            raise HTTPException(401, "Session no longer valid.")
        athlete_d = dict(athlete)
        al = conn.execute(
            "SELECT email FROM athlete_logins WHERE athlete_id = %s", (athlete_d["id"],)
        ).fetchone()
        return {
            "role": "athlete",
            "athlete": athlete_d,
            "email": dict(al)["email"] if al else None,
        }
    finally:
        conn.close()


@router.post("/athlete-claim-lookup")
def athlete_claim_lookup(data: AthleteClaimLookupRequest):
    """
    Phase 0 mitigation — auth v2.1 spec Part 2.1 (SEVERE), tightened per
    2026-08-20 security review. Returns only {athletes: [{id, first_name}]}
    for the athlete-claim screen's profile picker — never a session_token,
    never the parent's name, never athlete age, never a full parent/athlete
    row. An unknown parent email returns the same 200 {athletes: []} shape
    as a real parent with zero athletes, so the response never discloses
    whether a given email has an AthFuelPath account. It only ever looks at
    the parents table, so an athlete's own login email will not resolve
    here either — same {athletes: []} shape.
    """
    email = data.parent_email.strip().lower()
    conn = get_conn()
    try:
        parent = conn.execute(
            "SELECT id FROM parents WHERE lower(email) = %s", (email,)
        ).fetchone()
        if not parent:
            return {"athletes": []}
        parent_id = dict(parent)["id"]
        athletes = [dict(a) for a in conn.execute(
            "SELECT id, first_name FROM athletes WHERE parent_id = %s", (parent_id,)
        ).fetchall()]
        return {
            "athletes": [{"id": a["id"], "first_name": a["first_name"]} for a in athletes]
        }
    finally:
        conn.close()


@router.post("/athlete-create-login/{athlete_id}")
def create_athlete_login(athlete_id: int, data: AthleteCreateLoginRequest):
    """
    Phase 0c gate: no athlete login without a verified parent account.
    1. Verify parent exists by email.
    2. Verify athlete belongs to that parent.
    3. Create athlete_logins row.
    """
    email = data.email.strip().lower()
    parent_email = data.parent_email.strip().lower()
    conn = get_conn()
    try:
        # Gate 1: parent must exist
        parent = conn.execute(
            "SELECT id FROM parents WHERE lower(email) = %s", (parent_email,)
        ).fetchone()
        if not parent:
            raise HTTPException(
                403,
                "Ask your parent to set up AthFuelPath first — no parent account was found for that email.",
            )
        parent_id = dict(parent)["id"]

        # Gate 2: athlete must belong to this parent
        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = %s AND parent_id = %s",
            (athlete_id, parent_id),
        ).fetchone()
        if not athlete:
            raise HTTPException(
                403, "This athlete profile is not linked to that parent account."
            )

        # Gate 3: athlete must not already have a login.
        # Explicit check so the operation is sound regardless of whether the live
        # athlete_logins table has the UNIQUE(athlete_id) constraint (prod currently
        # does not — see db_migrations). Prevents a silent duplicate login for the
        # same athlete claimed under a second email.
        if conn.execute(
            "SELECT 1 FROM athlete_logins WHERE athlete_id = %s", (athlete_id,)
        ).fetchone():
            raise HTTPException(409, "This athlete already has a login.")

        # Create login credentials
        try:
            conn.execute(
                "INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)",
                (email, athlete_id),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            if "unique" in str(e).lower():
                raise HTTPException(409, "An account with that email already exists.")
            raise HTTPException(500, str(e))

        token = mint_session_token(role="athlete", athlete_id=athlete_id, parent_id=parent_id)
        return {"role": "athlete", "athlete": dict(athlete), "session_token": token}
    finally:
        conn.close()
