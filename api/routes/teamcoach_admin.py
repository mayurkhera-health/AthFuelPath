"""Admin provisioning for TeamCoach — create coaches, teams, roster entries.
All routes require existing admin bearer token via require_admin.
Mounted at /api/admin/team-coach/* to keep TeamCoach admin ops namespaced.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.database import get_conn
from api.services.admin_auth import require_admin
from api.services.teamcoach_auth_service import hash_password

router = APIRouter()


class CreateCoachRequest(BaseModel):
    name: str
    email: str
    password: str


@router.post("/coaches", status_code=201, dependencies=[Depends(require_admin)])
def create_coach(body: CreateCoachRequest):
    pw_hash, salt = hash_password(body.password)
    conn = get_conn()
    try:
        if conn.execute(
            "SELECT id FROM coaches WHERE email = %s", (body.email,)
        ).fetchone():
            raise HTTPException(409, "Email already registered")
        cur = conn.execute(
            "INSERT INTO coaches (name, email, password_hash, salt) VALUES (%s,%s,%s,%s) RETURNING id",
            (body.name, body.email, pw_hash, salt),
        )
        conn.commit()
        return {"coach_id": cur.fetchone()["id"]}
    finally:
        conn.close()


class CreateTeamRequest(BaseModel):
    name: str
    season: str
    threshold_pct: int = 80


@router.post("/teams", status_code=201, dependencies=[Depends(require_admin)])
def create_team(body: CreateTeamRequest):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO teams (name, season, threshold_pct) VALUES (%s,%s,%s) RETURNING id",
            (body.name, body.season, body.threshold_pct),
        )
        conn.commit()
        return {"team_id": cur.fetchone()["id"]}
    finally:
        conn.close()


@router.post(
    "/teams/{team_id}/coaches/{coach_id}",
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def grant_coach_access(team_id: int, coach_id: int):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO coach_team_access (coach_id, team_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (coach_id, team_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


class AddRosterRequest(BaseModel):
    athlete_id: int
    parent_consent_flag: int = 0


@router.post(
    "/teams/{team_id}/roster",
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def add_to_roster(team_id: int, body: AddRosterRequest):
    conn = get_conn()
    try:
        if not conn.execute(
            "SELECT id FROM athletes WHERE id = %s", (body.athlete_id,)
        ).fetchone():
            raise HTTPException(404, "Athlete not found")
        conn.execute(
            "INSERT INTO roster_membership "
            "(athlete_id, team_id, parent_consent_flag) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (body.athlete_id, team_id, body.parent_consent_flag),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post(
    "/teams/{team_id}/snapshot",
    status_code=200,
    dependencies=[Depends(require_admin)],
)
def trigger_snapshot(team_id: int):
    """Manual snapshot trigger — useful for backfill or testing."""
    from api.services.snapshot_job import generate_snapshot
    return generate_snapshot(team_id)
