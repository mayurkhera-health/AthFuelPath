"""
Phase 1 — Unified auth endpoint.
Originally resolved parent OR athlete from a single email via
POST /login; that route was retired in auth v2.1 Phase 4 (email-only
session issuance removed) in favor of the OTP-verified /email/request +
/email/verify flow below. Keeps /api/athletes/* intact for backward compat.
"""
import logging
import secrets
from datetime import datetime

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from api.database import get_conn
from api.services import login_alerts
from api.services.session_auth import mint_session_token, require_session
from api.services.otp_auth import issue_otp, verify_otp as verify_otp_code, OtpRateLimited, OtpDeliveryFailed
from api.services.identity_resolver import (
    resolve_identity,
    NoExistingAccount,
    AmbiguousIdentity,
    ResolvedIdentity,
    _resolve_exactly_one_owner,
    _resolve_exactly_one_parent_owner,
)
from api.services.google_auth import verify_google_id_token, GoogleVerificationError
from api.services.apple_auth import (
    verify_apple_identity_token,
    exchange_authorization_code_for_refresh_token,
    AppleVerificationError,
)
from api.services.provider_credential_crypto import encrypt_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter()

# auth v2.1 Phase 6 (Part K) — fixed, generic 401/409/502 messages, reused
# verbatim across every branch that needs them so no response ever hints
# which specific check failed.
_GOOGLE_VERIFY_FAILED_MESSAGE = "Google sign-in could not be verified. Please try again."
_APPLE_VERIFY_FAILED_MESSAGE = "Apple sign-in could not be verified. Please try again."
_APPLE_EXCHANGE_FAILED_MESSAGE = "Apple sign-in could not be completed. Please try again."
_AMBIGUOUS_IDENTITY_MESSAGE = "Something went wrong. Please contact support."

# auth v2.1 Phase 6 — named TTL constants (interpolated via Postgres's own
# make_interval(), never raw string-embedded SQL intervals) instead of magic
# numbers duplicated at each call site.
_CHALLENGE_TTL_MINUTES = 5
_PENDING_LINK_TTL_MINUTES = 10


class LoginRequest(BaseModel):
    email: str


class AthleteCreateLoginRequest(BaseModel):
    email: str          # athlete's own email (becomes their login)
    parent_email: str   # parent's email — the gate
    code: str            # OTP sent to parent_email, proving the parent authorized this claim (auth v2.1 Phase 4)


class AthleteClaimLookupRequest(BaseModel):
    parent_email: str


class EmailAuthRequest(BaseModel):
    email: str


class EmailAuthVerify(BaseModel):
    email: str
    code: str


class ProviderChallengeRequest(BaseModel):
    provider: str  # "google" | "apple"


class GoogleVerifyRequest(BaseModel):
    challenge_id: str
    id_token: str


class AppleVerifyRequest(BaseModel):
    challenge_id: str
    identity_token: str
    authorization_code: str | None = None  # required whenever no stored
    # credential exists yet for this identity — see apple_verify below.


class AppleLinkExistingRequest(BaseModel):
    pending_link_id: str
    email: str    # the EXISTING AthFuelPath account's email, typed by the user
    code: str     # the OTP just sent to that email via the existing /email/request


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

    auth v2.1 Phase 5 (Task 3): identity resolution itself — "which parent
    or athlete does this verified email belong to" — is delegated to the
    common resolver (api.services.identity_resolver.resolve_identity)
    instead of this route's own inline parent-then-athlete lookup. The
    route still owns everything the resolver deliberately does not: loading
    the full row for the response, minting the session, and the parent-only
    side effects below. Response shapes/status codes are unchanged from
    before this migration for every case that was reachable before it.

    If the verified email has no existing account (resolver raises
    NoExistingAccount), this reports that plainly instead of guessing/
    creating one — creating an account here would be Phase 7 (verified
    signup), out of scope for Phase 2. Reporting it is safe: the caller
    just proved ownership of exactly this email, so telling them whether
    THEIR OWN email has an account is not an enumeration leak (unlike
    /email/request, which must stay neutral to an unverified caller).

    If the verified email resolves to more than one possible owner
    (resolver raises AmbiguousIdentity — not reachable with current
    production data, see Phase 5 plan A.5, but handled defensively since a
    future write could make it possible), this fails closed: 409 (never
    401 — OTP verification already proved genuine authentication, so 401
    would be wrong), with a fixed generic message only. No parent/athlete
    IDs, email, or collision details ever appear in the response or in the
    server-side log line for this case.

    On a successful parent login, this also stamps last_login_at and
    schedules a best-effort founder login-alert (login_alerts.notify_login)
    as a background task — ported from the now-deleted unified_login
    (auth v2.1 Phase 4). These side effects fire only in the parent branch,
    unconditionally on a successful parent resolution, exactly as before
    this migration.
    """
    email = data.email.strip().lower()

    if not verify_otp_code(email, data.code.strip()):
        raise HTTPException(401, "Invalid or expired code. Please request a new one.")

    try:
        identity = resolve_identity(
            provider="email", provider_subject=email, email=email, email_verified=True,
        )
    except NoExistingAccount:
        return {"verified": True, "has_account": False}
    except AmbiguousIdentity:
        logger.error(
            "email_auth_verify: ambiguous identity for a verified email "
            "(auth_identities data integrity issue — multiple possible owners)"
        )
        raise HTTPException(409, "Something went wrong. Please contact support.")

    conn = get_conn()
    try:
        if identity.role == "parent":
            parent = conn.execute(
                "SELECT * FROM parents WHERE id = %s", (identity.parent_id,)
            ).fetchone()
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

        # identity.role == "athlete". No defensive "athlete row missing"
        # check here (unlike the pre-Phase-5 code's now-removed inline
        # lookup): athlete_logins.athlete_id is NOT NULL UNIQUE REFERENCES
        # athletes(id) ON DELETE CASCADE, so a resolved athlete_id can never
        # point at a since-deleted athlete row — that branch was always
        # unreachable, even before this migration (see Phase 5 plan, Task 3
        # Step 4 note).
        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = %s", (identity.athlete_id,)
        ).fetchone()
        athlete_d = dict(athlete)
        token = mint_session_token(
            role="athlete", athlete_id=athlete_d["id"], parent_id=athlete_d["parent_id"],
        )
        return {"role": "athlete", "athlete": athlete_d, "session_token": token}
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
    No athlete login without proof the parent authorized it. Corrected auth
    v2.1 Phase 4 design (2026-08-23 review): the OTP is sent to and verified
    against the PARENT's email, not the athlete's new login email, and
    verification happens here directly via verify_otp_code — never via
    POST /api/auth/email/verify, which would resolve the parent identity and
    mint a PARENT session. The athlete must never receive a parent session
    as a side effect of claiming their own profile.

    Order (each gate checked only after the previous one passes):
    1. Verify the submitted code against parent_email — no account lookup
       needed for this, so it happens first.
    2. Only after OTP success, recheck parent ownership: parent must exist,
       and this athlete must belong to that parent.
    3. Athlete must not already have a login.
    4. Create the login row.
    5. Mint an athlete session — never a parent one.
    """
    email = data.email.strip().lower()
    parent_email = data.parent_email.strip().lower()

    # Gate 1: a real, server-verified OTP proving control of parent_email.
    # Single-use (verify_otp_code marks it consumed on success) and checked
    # BEFORE any parent/athlete lookup — an invalid code learns nothing
    # about whether parent_email or athlete_id are even real.
    if not verify_otp_code(parent_email, data.code.strip()):
        raise HTTPException(401, "Invalid or expired code. Please request a new one.")

    conn = get_conn()
    try:
        # Gate 2 (recheck, only reached after OTP success): parent must exist.
        parent = conn.execute(
            "SELECT id FROM parents WHERE lower(email) = %s", (parent_email,)
        ).fetchone()
        if not parent:
            raise HTTPException(
                403,
                "Ask your parent to set up AthFuelPath first — no parent account was found for that email.",
            )
        parent_id = dict(parent)["id"]

        # Gate 3: athlete must belong to this parent.
        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = %s AND parent_id = %s",
            (athlete_id, parent_id),
        ).fetchone()
        if not athlete:
            raise HTTPException(
                403, "This athlete profile is not linked to that parent account."
            )

        # Gate 4: athlete must not already have a login.
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


# ============================================================================
# auth v2.1 Phase 6 — Google + Apple Sign-In
# (docs/superpowers/plans/2026-08-24-auth-v2.1-phase-6.md, Parts A.6/A.8/C/F)
#
# Google's flow hands a verified (provider, provider_subject, email,
# email_verified) straight to the unchanged resolve_identity(), exactly like
# email_auth_verify above. Apple's flow deliberately does NOT call
# resolve_identity() at all (A.8, corrected 4th round): a first-time Apple
# identity has a mandatory external dependency (capturing a refresh token,
# the Phase-10 revocation prerequisite) that must succeed BEFORE the
# identity mapping is durably created — resolve_identity()'s auto-link path
# would INSERT the mapping first, which could leave a partially-complete
# Apple identity (mapping without credential) behind if the exchange then
# failed. Apple uses only the read-only _resolve_exactly_one_owner() /
# _resolve_exactly_one_parent_owner() building blocks and performs its own
# atomic, credential-first writes below.
# ============================================================================


def _cleanup_expired_provider_auth_state() -> None:
    """Opportunistic, bounded cleanup (A.11) — no scheduler needed. Called at
    the top of provider_challenge(), the highest-traffic entry point into
    this subsystem, so stale rows never accumulate indefinitely. Narrowly
    scoped to exactly these two Phase 6 temporary tables. Consumed
    apple_pending_links rows (successfully completed links) are intentionally
    left alone — they're inert once consumed."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM provider_auth_challenges WHERE expires_at < now()")
        conn.execute("DELETE FROM apple_pending_links WHERE expires_at < now() AND consumed_at IS NULL")
        conn.commit()
    finally:
        conn.close()


def _consume_challenge(challenge_id: str, *, provider: str, generic_message: str) -> str:
    """Atomically consumes a provider-auth challenge (A.6) — the exact same
    atomic-consumption idiom otp_auth.py already uses for OTP codes. No row
    returned (doesn't exist, wrong provider, already consumed, or expired)
    means 401 BEFORE any provider-token verification is even attempted. A
    successfully consumed challenge can never authenticate a second request —
    the atomic `WHERE consumed_at IS NULL` guarantees this at the DB layer."""
    conn = get_conn()
    try:
        row = conn.execute(
            "UPDATE provider_auth_challenges SET consumed_at = now() "
            "WHERE challenge_id = %s AND provider = %s AND consumed_at IS NULL AND expires_at > now() "
            "RETURNING raw_nonce",
            (challenge_id, provider),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        raise HTTPException(401, generic_message)
    return dict(row)["raw_nonce"]


def _mint_session_for_resolved_identity(
    resolved: ResolvedIdentity, background_tasks: BackgroundTasks, conn=None,
) -> dict:
    """Shared success-branch helper (Part F) — reuses the exact same pattern
    email_auth_verify already has (full row lookup, last_login_at/login-alert
    ONLY for the parent branch, mint_session_token), fed by a ResolvedIdentity
    instead of resolve_identity()'s return value directly, so google_verify/
    apple_verify/apple_link_existing all share one implementation instead of
    quadruplicating it. email_auth_verify itself is intentionally left with
    its own copy of this logic, unmodified, per this task's scope.

    Accepts an optional caller-owned `conn` — same owns_conn idiom as
    identity_resolver.py's _resolve_exactly_one_owner/
    _resolve_exactly_one_parent_owner — so a caller that already has a
    connection open (e.g. apple_link_existing, still inside its own
    transaction) doesn't pay for a second physical connection (no pooling
    exists — get_conn() opens a fresh one every call). Opens/closes its own
    when none is passed, exactly like every other caller of this function."""
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
    try:
        if resolved.role == "parent":
            parent = conn.execute(
                "SELECT * FROM parents WHERE id = %s", (resolved.parent_id,)
            ).fetchone()
            parent_d = dict(parent)
            athletes = [dict(a) for a in conn.execute(
                "SELECT * FROM athletes WHERE parent_id = %s", (parent_d["id"],)
            ).fetchall()]

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

        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = %s", (resolved.athlete_id,)
        ).fetchone()
        athlete_d = dict(athlete)
        token = mint_session_token(
            role="athlete", athlete_id=athlete_d["id"], parent_id=athlete_d["parent_id"],
        )
        return {"role": "athlete", "athlete": athlete_d, "session_token": token}
    finally:
        if owns_conn:
            conn.close()


@router.post("/provider/challenge")
def provider_challenge(data: ProviderChallengeRequest):
    """A.6/C.1 — server-issued, single-use, short-lived nonce challenge that
    replaces a mobile-generated nonce as the authoritative replay-protection
    mechanism. No auth required — issuing a challenge reveals nothing about
    any account. Stores the RAW issued nonce (not a pre-committed hash under
    an assumed transform, see google_auth.py/apple_auth.py)."""
    if data.provider not in ("google", "apple"):
        raise HTTPException(422, "Unsupported provider.")
    _cleanup_expired_provider_auth_state()
    raw_nonce = secrets.token_urlsafe(32)
    challenge_id = secrets.token_urlsafe(24)
    conn = get_conn()
    try:
        # expiry computed via Postgres's own now() + interval, not Python
        # datetime arithmetic -- expires_at is TIMESTAMPTZ and this session's
        # timezone is not guaranteed to be UTC (e.g. local dev defaults to
        # the machine's zone), so a naive Python isoformat() string would be
        # silently (mis)interpreted in that session timezone instead of UTC.
        conn.execute(
            "INSERT INTO provider_auth_challenges (challenge_id, provider, raw_nonce, expires_at) "
            "VALUES (%s, %s, %s, now() + make_interval(mins => %s))",
            (challenge_id, data.provider, raw_nonce, _CHALLENGE_TTL_MINUTES),
        )
        conn.commit()
    finally:
        conn.close()
    return {"challenge_id": challenge_id, "nonce": raw_nonce}


@router.post("/google/verify")
def google_verify(data: GoogleVerifyRequest, background_tasks: BackgroundTasks):
    """C.2 — Google's flow is explicitly unchanged/unweakened: verify the
    challenge + ID token server-side, then hand straight to the unchanged
    resolve_identity(), exactly as email_auth_verify already does for the
    email provider."""
    raw_nonce = _consume_challenge(
        data.challenge_id, provider="google", generic_message=_GOOGLE_VERIFY_FAILED_MESSAGE,
    )
    try:
        identity = verify_google_id_token(data.id_token, raw_nonce)
    except GoogleVerificationError:
        raise HTTPException(401, _GOOGLE_VERIFY_FAILED_MESSAGE)

    try:
        resolved = resolve_identity(
            provider="google", provider_subject=identity.sub,
            email=identity.email.strip().lower() if identity.email else None,
            email_verified=identity.email_verified,
        )
    except NoExistingAccount:
        return {"verified": True, "has_account": False}
    except AmbiguousIdentity:
        logger.error("google_verify: ambiguous identity for a verified Google account")
        raise HTTPException(409, _AMBIGUOUS_IDENTITY_MESSAGE)

    return _mint_session_for_resolved_identity(resolved, background_tasks)


# --- Apple: read-only building blocks (Case A of A.8) ----------------------

def _find_exact_apple_identity(provider_subject: str):
    """A direct, READ-ONLY exact-match lookup — NEVER resolve_identity(),
    whose auto-link INSERT would create a mapping before any Apple credential
    exists. Returns (auth_identity_id, ResolvedIdentity) or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, parent_id, athlete_id FROM auth_identities "
            "WHERE provider = 'apple' AND provider_subject = %s",
            (provider_subject,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    row_d = dict(row)
    resolved = ResolvedIdentity(
        role="parent" if row_d["parent_id"] is not None else "athlete",
        parent_id=row_d["parent_id"], athlete_id=row_d["athlete_id"],
    )
    return row_d["id"], resolved


def _has_stored_apple_credential(auth_identity_id: int) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM apple_provider_credentials WHERE auth_identity_id = %s",
            (auth_identity_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _store_apple_credential(auth_identity_id: int, ciphertext: bytes, nonce: bytes) -> None:
    """Case A's missing-credential branch — a single-table insert, the
    existing auth_identities row is left completely untouched.

    auth_identity_id is NOT NULL UNIQUE on apple_provider_credentials, and
    _has_stored_apple_credential's check + this insert are not covered by a
    shared transaction/lock (each opens its own connection, same as every
    other helper in this file) — so two concurrent requests for the same
    not-yet-stored Apple identity (e.g. a client retry-on-timeout) can both
    pass the check, both perform the external Apple exchange, and then race
    here. Whichever loses the race hits a genuine UniqueViolation: that's
    benign, not an error — it just means the other concurrent request's
    credential already won, so this one proceeds to mint a session same as
    if its own insert had succeeded, exactly like the UniqueViolation
    idioms elsewhere in this file (_create_apple_identity_with_credential,
    _consume_pending_link_and_create_apple_identity)."""
    conn = get_conn()
    try:
        try:
            conn.execute(
                "INSERT INTO apple_provider_credentials "
                "(auth_identity_id, encrypted_refresh_token, encryption_nonce) VALUES (%s, %s, %s)",
                (auth_identity_id, ciphertext, nonce),
            )
            conn.commit()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
    finally:
        conn.close()


def _create_apple_identity_with_credential(
    provider_subject: str, owner: tuple, ciphertext: bytes, nonce: bytes,
) -> ResolvedIdentity:
    """Case B's exactly-one-owner branch (A.8) — the ONE-transaction dual
    insert: creates the auth_identities row and its apple_provider_credentials
    row TOGETHER, committed or rolled back as a single unit (one conn, one
    commit()). Any uniqueness/storage failure on either insert rolls back the
    entire transaction — the identity mapping and its credential are created
    together or not at all; there is no intermediate observable state where
    one exists without the other (Part L, item 8)."""
    role, parent_id, athlete_id = owner
    conn = get_conn()
    try:
        try:
            row = conn.execute(
                "INSERT INTO auth_identities "
                "(provider, provider_subject, parent_id, athlete_id, email, email_verified) "
                "VALUES ('apple', %s, %s, %s, NULL, FALSE) RETURNING id",
                (provider_subject, parent_id, athlete_id),
            ).fetchone()
            auth_identity_id = dict(row)["id"]
            conn.execute(
                "INSERT INTO apple_provider_credentials "
                "(auth_identity_id, encrypted_refresh_token, encryption_nonce) VALUES (%s, %s, %s)",
                (auth_identity_id, ciphertext, nonce),
            )
            conn.commit()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            # Matches this codebase's existing "owner already linked" 409
            # pattern (create_athlete_login above) — fails closed, never
            # partially applies either insert.
            raise HTTPException(
                409, "This account is already linked to a different Apple sign-in."
            ) from None
        except Exception:
            # ANY failure between the two inserts (Part L, item 8) rolls
            # back the whole transaction — the identity mapping and its
            # credential are created together or not at all, never one
            # without the other.
            conn.rollback()
            raise
    finally:
        conn.close()
    return ResolvedIdentity(role=role, parent_id=parent_id, athlete_id=athlete_id)


def _create_apple_pending_link(
    *, provider_subject: str, email_from_token: str | None, email_verified_from_token: bool,
    encrypted_refresh_token: bytes, encryption_nonce: bytes,
) -> str:
    """Hide-My-Email path (A.8) — only ever called with an already-encrypted
    credential already in hand (the caller performed the synchronous exchange
    BEFORE calling this). There is no such thing as a credential-less pending
    link in this design — apple_pending_links' credential columns are
    NOT NULL at the schema level too (db/postgres/004_phase6_provider_auth.sql)."""
    pending_link_id = secrets.token_urlsafe(24)
    conn = get_conn()
    try:
        # Expiry computed via Postgres's own now() + interval -- see
        # provider_challenge()'s identical comment on why a naive Python
        # isoformat() string must never be written into a TIMESTAMPTZ column.
        conn.execute(
            "INSERT INTO apple_pending_links "
            "(pending_link_id, provider_subject, email_from_token, email_verified_from_token, "
            "encrypted_refresh_token, encryption_nonce, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s))",
            (
                pending_link_id, provider_subject, email_from_token, email_verified_from_token,
                encrypted_refresh_token, encryption_nonce, _PENDING_LINK_TTL_MINUTES,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return pending_link_id


async def _require_apple_exchange_and_encrypt(authorization_code: str | None, *, expected_sub: str) -> tuple[bytes, bytes]:
    """Shared by every branch that needs Apple's mandatory synchronous
    exchange before any write (A.8's "one rule, stated once"). Performs the
    exchange AND encrypts the result (see provider_credential_crypto) before
    returning, so every caller gets ciphertext ready to store, never a raw
    refresh token. Raises HTTPException(502) uniformly — no branch may skip
    this or treat a missing/failed exchange as anything but a hard failure.
    Returns (ciphertext, nonce) ready to store."""
    if not authorization_code:
        raise HTTPException(502, _APPLE_EXCHANGE_FAILED_MESSAGE)
    try:
        raw_refresh_token = await exchange_authorization_code_for_refresh_token(
            authorization_code, expected_sub=expected_sub,
        )
    except AppleVerificationError:
        logger.error("apple exchange: authorization-code exchange failed")
        raise HTTPException(502, _APPLE_EXCHANGE_FAILED_MESSAGE)
    return encrypt_refresh_token(raw_refresh_token)


@router.post("/apple/verify")
async def apple_verify(data: AppleVerifyRequest, background_tasks: BackgroundTasks):
    """C.3/A.8 — THE most critical part of Phase 6. Apple NEVER calls
    resolve_identity(). Case A (exact mapping already exists) is looked up
    directly and read-only; Case B (no exact mapping) uses only the
    read-only _resolve_exactly_one_owner() building block. Every first-time
    write path performs its mandatory synchronous credential exchange BEFORE
    any auth_identities/apple_pending_links row is created."""
    raw_nonce = _consume_challenge(
        data.challenge_id, provider="apple", generic_message=_APPLE_VERIFY_FAILED_MESSAGE,
    )
    try:
        identity = verify_apple_identity_token(data.identity_token, raw_nonce)
    except AppleVerificationError:
        raise HTTPException(401, _APPLE_VERIFY_FAILED_MESSAGE)

    # Case A — exact mapping already exists. Authoritative, never re-decided
    # by email. A direct, read-only SELECT — not resolve_identity().
    existing = _find_exact_apple_identity(identity.sub)
    if existing:
        auth_identity_id, resolved = existing
        if not _has_stored_apple_credential(auth_identity_id):
            ciphertext, nonce = await _require_apple_exchange_and_encrypt(
                data.authorization_code, expected_sub=identity.sub,
            )
            _store_apple_credential(auth_identity_id, ciphertext, nonce)
        # Credential already existed: no exchange attempted at all, even if
        # authorization_code is present in this request (A.8/Part K).
        return _mint_session_for_resolved_identity(resolved, background_tasks)

    # Case B — no exact mapping. READ-ONLY owner match only; never a write.
    email = identity.email.strip().lower() if identity.email else None
    try:
        owner = _resolve_exactly_one_owner(email, email_verified=identity.email_verified)
    except NoExistingAccount:
        # Hide-My-Email path. Exchange BEFORE creating anything — no
        # credential-less pending link can ever be created.
        ciphertext, nonce = await _require_apple_exchange_and_encrypt(
            data.authorization_code, expected_sub=identity.sub,
        )
        pending_link_id = _create_apple_pending_link(
            provider_subject=identity.sub,
            email_from_token=identity.email,
            email_verified_from_token=identity.email_verified,
            encrypted_refresh_token=ciphertext,
            encryption_nonce=nonce,
        )
        return {
            "verified": True, "has_account": False,
            "apple_linkable": True, "pending_link_id": pending_link_id,
        }
    except AmbiguousIdentity:
        # Checked BEFORE the exchange — no reason to spend an Apple API
        # round-trip on a request that 409s regardless.
        logger.error("apple_verify: ambiguous identity for a verified Apple account")
        raise HTTPException(409, _AMBIGUOUS_IDENTITY_MESSAGE)

    # Exactly one owner. Exchange BEFORE creating the identity mapping, then
    # create the mapping + its credential in ONE transaction.
    ciphertext, nonce = await _require_apple_exchange_and_encrypt(data.authorization_code, expected_sub=identity.sub)
    resolved = _create_apple_identity_with_credential(
        provider_subject=identity.sub, owner=owner, ciphertext=ciphertext, nonce=nonce,
    )
    return _mint_session_for_resolved_identity(resolved, background_tasks)


def _consume_pending_link_and_create_apple_identity(
    conn, pending: dict, parent_id: int,
) -> ResolvedIdentity:
    """C.4 — transactional: atomically re-consumes the pending-link row
    (guards against a concurrent double-use of the same pending_link_id),
    then in the SAME transaction copies its ALREADY-encrypted credential
    (no second exchange, it already happened synchronously in apple_verify's
    Hide-My-Email branch) into a new auth_identities row + its
    apple_provider_credentials row. Any conflict rolls back everything."""
    try:
        consumed = conn.execute(
            "UPDATE apple_pending_links SET consumed_at = now() "
            "WHERE pending_link_id = %s AND consumed_at IS NULL "
            "RETURNING provider_subject, encrypted_refresh_token, encryption_nonce",
            (pending["pending_link_id"],),
        ).fetchone()
        if not consumed:
            conn.rollback()
            raise HTTPException(
                401, "This sign-in attempt has expired. Please try Continue with Apple again."
            )
        consumed_d = dict(consumed)

        row = conn.execute(
            "INSERT INTO auth_identities "
            "(provider, provider_subject, parent_id, athlete_id, email, email_verified) "
            "VALUES ('apple', %s, %s, NULL, NULL, FALSE) RETURNING id",
            (consumed_d["provider_subject"], parent_id),
        ).fetchone()
        auth_identity_id = dict(row)["id"]

        conn.execute(
            "INSERT INTO apple_provider_credentials "
            "(auth_identity_id, encrypted_refresh_token, encryption_nonce) VALUES (%s, %s, %s)",
            (auth_identity_id, consumed_d["encrypted_refresh_token"], consumed_d["encryption_nonce"]),
        )
        conn.commit()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            409, "This account is already linked to a different Apple sign-in."
        ) from None
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise
    return ResolvedIdentity(role="parent", parent_id=parent_id, athlete_id=None)


@router.post("/apple/link-existing")
def apple_link_existing(data: AppleLinkExistingRequest, background_tasks: BackgroundTasks):
    """C.4 — completes the Hide-My-Email path: typing an email alone can
    never link anything — a genuine, freshly-verified OTP is required first.
    Explicitly parent-scoped (A.8) — an athlete has no independent
    OTP-receiving email channel in this architecture."""
    email = data.email.strip().lower()
    if not verify_otp_code(email, data.code.strip()):
        raise HTTPException(401, "Invalid or expired code. Please request a new one.")

    conn = get_conn()
    try:
        pending = conn.execute(
            "SELECT * FROM apple_pending_links WHERE pending_link_id = %s "
            "AND consumed_at IS NULL AND expires_at > now()",
            (data.pending_link_id,),
        ).fetchone()
        if not pending:
            raise HTTPException(
                401, "This sign-in attempt has expired. Please try Continue with Apple again."
            )
        pending_d = dict(pending)

        try:
            parent_id = _resolve_exactly_one_parent_owner(email, conn=conn)
        except (NoExistingAccount, AmbiguousIdentity):
            raise HTTPException(
                401, "We couldn't verify that account. Please check the email and try again."
            )

        resolved = _consume_pending_link_and_create_apple_identity(conn, pending_d, parent_id)
        # Pass this same still-open conn through rather than letting
        # _mint_session_for_resolved_identity open a second physical
        # connection after this transaction's connection closes (owns_conn
        # idiom, matching identity_resolver.py's
        # _resolve_exactly_one_owner/_resolve_exactly_one_parent_owner).
        return _mint_session_for_resolved_identity(resolved, background_tasks, conn=conn)
    finally:
        conn.close()
