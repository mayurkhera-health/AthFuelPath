"""
Phase 1 — Unified auth endpoint.
Resolves parent OR athlete from a single email.
Keeps /api/parents/login and /api/athletes/* intact for backward compat.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from api.database import get_conn
from api.services import login_alerts
from api.services.session_auth import mint_session_token

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str


class AthleteCreateLoginRequest(BaseModel):
    email: str          # athlete's own email (becomes their login)
    parent_email: str   # parent's email — the gate


@router.post("/login")
def unified_login(data: LoginRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Single login for both personas.
    Checks parents first (most common), then athlete_logins.
    Returns { role, ...session_data }.

    This is the explicit parent sign-in path (the Login screen). Silent
    session-restore on app relaunch uses /api/parents/login, so alerting here
    fires only on a real, active sign-in — not a background rehydrate.
    """
    # Temporary — 2026-08-19, remove after ~7 days. Same client-split logging
    # as parents.py's /login — see docs/age-audit.md Part 14/16.
    logger.info("unified_login_client origin=%r user_agent=%r",
                request.headers.get("origin"), request.headers.get("user-agent"))
    email = data.email.strip().lower()
    conn = get_conn()
    try:
        # 1. Parent?
        parent = conn.execute(
            "SELECT * FROM parents WHERE lower(email) = %s", (email,)
        ).fetchone()
        if parent:
            parent_d = dict(parent)
            athletes = [dict(a) for a in conn.execute(
                "SELECT * FROM athletes WHERE parent_id = %s", (parent_d["id"],)
            ).fetchall()]

            # Beta login alert (best-effort; backgrounded so it never slows the
            # response, never blocks the login if it fails). A NULL last_login_at
            # means first-ever login → treated as a new signup.
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

        raise HTTPException(404, "No account found with that email address.")
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
