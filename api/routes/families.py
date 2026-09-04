"""
Family-level actions — parent-initiated operations that act on the family
as a whole rather than a single parent or athlete record. First endpoint:
unlink, the recovery path for an athlete whose sign-in identity becomes
unusable (lost/deauthorized Apple ID, etc.).

/api/families/* is a new prefix (see the family-account-onboarding spec,
docs/planning/family-account-onboarding-spec.md in the mobile repo) —
future family-subscription and link-code endpoints are expected to land
here too, not scattered across parents.py/auth.py.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException

from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_parent, assert_owns_athlete
from api.services.admin_auth import write_audit

log = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/{parent_id}/athletes/{athlete_id}/link")
def unlink_athlete(parent_id: int, athlete_id: int, identity=Depends(require_session)):
    """Release an athlete's sign-in identity so they can re-link from
    scratch. This is the ONLY recovery path for a claimed athlete whose
    provider identity (Apple/Google) becomes unusable — there is no
    email-based recovery route, deliberately: recovery must be initiated by
    an authenticated parent in a live session, never by supplying an email
    address (the property the old athlete-claim flow didn't have).

    Deletes:
    - auth_identities row(s) for this athlete (cascades to
      apple_provider_credentials automatically — see
      db/postgres/004_phase6_provider_auth.sql's ON DELETE CASCADE).
    - the athlete_logins row, which returns the athlete to "unclaimed" and
      is what makes assert_owns_athlete() reject any session token already
      issued to this athlete on its very next request (session tokens are
      stateless with a 30-day rolling TTL and no revocation list — this
      DB-backed check is the only way to invalidate one before it expires).

    Athlete profile data (name, stats, history) is untouched — this is an
    identity reset, not a delete.
    """
    assert_owns_parent(identity, parent_id)
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)

        athlete_row = conn.execute(
            "SELECT first_name FROM athletes WHERE id = %s", (athlete_id,)
        ).fetchone()
        if not athlete_row:
            raise HTTPException(404, "Athlete not found.")

        parent_row = conn.execute(
            "SELECT email FROM parents WHERE id = %s", (parent_id,)
        ).fetchone()
        parent_email = dict(parent_row)["email"] if parent_row else "unknown"

        had_login = conn.execute(
            "SELECT 1 FROM athlete_logins WHERE athlete_id = %s", (athlete_id,)
        ).fetchone()
        if not had_login:
            raise HTTPException(409, "This athlete has no active sign-in to unlink.")

        conn.execute("DELETE FROM auth_identities WHERE athlete_id = %s", (athlete_id,))
        conn.execute("DELETE FROM athlete_logins WHERE athlete_id = %s", (athlete_id,))

        write_audit(
            "unlink_athlete", "athlete", athlete_id,
            {"parent_id": parent_id, "first_name": dict(athlete_row)["first_name"]},
            conn=conn,
            actor_id=parent_id, actor_email=parent_email, actor_role="parent",
        )
        conn.commit()
    finally:
        conn.close()

    return {"unlinked": True, "athlete_id": athlete_id}
