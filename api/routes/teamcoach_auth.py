from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from api.database import get_conn
from api.services.teamcoach_auth_service import (
    verify_password, mint_token, verify_token,
    check_rate_limit, record_failed_login, clear_failed_logins,
)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(ip)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, password_hash, salt FROM coaches WHERE email = %s",
            (body.email,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["password_hash"] or not verify_password(
        body.password, row["password_hash"], row["salt"]
    ):
        record_failed_login(ip)
        raise HTTPException(401, "Invalid email or password")
    clear_failed_logins(ip)
    token = mint_token(coach_id=row["id"], email=body.email)
    return {"token": token, "coach_name": row["name"]}


def require_coach(authorization: str = Header(None)) -> dict:
    """FastAPI dependency — extract and verify TeamCoach bearer token.
    Returns payload dict with coach_id and email. Raises 401 otherwise."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "TeamCoach authentication required")
    payload = verify_token(authorization[7:].strip())
    if not payload:
        raise HTTPException(401, "Invalid or expired session")
    return payload


@router.get("/me")
def me(authorization: str = Header(None)):
    payload = require_coach(authorization)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, email FROM coaches WHERE id = %s",
            (payload["coach_id"],),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Coach account not found")
    return {"coach_id": row["id"], "name": row["name"], "email": row["email"]}
