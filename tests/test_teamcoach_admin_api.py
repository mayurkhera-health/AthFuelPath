import os
os.environ.setdefault("ADMIN_SESSION_SECRET", "admin-secret")
os.environ.setdefault("ADMIN_PASSWORD", "adminpass")
os.environ.setdefault("TEAM_COACH_SESSION_SECRET", "coach-secret")

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import get_conn
from db.setup import init_db
from api.services.admin_auth import mint_token as admin_mint

client = TestClient(app)


@pytest.fixture(autouse=True)
def seed():
    init_db()
    conn = get_conn()
    conn.execute(
        "INSERT INTO parents (id,full_name,email,consent_timestamp) "
        "VALUES (1,'P','p@e.com','2026-01-01') ON CONFLICT (id) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO athletes "
        "(id,parent_id,first_name,age,gender,weight_lbs,height_ft,height_in) "
        "VALUES (1,1,'Alice',15,'female',130,5,4) ON CONFLICT (id) DO NOTHING"
    )
    conn.commit()
    conn.close()


TOKEN = admin_mint()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_create_coach():
    r = client.post("/api/admin/team-coach/coaches", json={
        "name": "Jane Coach", "email": "jane@club.com", "password": "Str0ng!Pass"
    }, headers=_auth())
    assert r.status_code == 201
    assert "coach_id" in r.json()


def test_create_coach_duplicate_409():
    client.post("/api/admin/team-coach/coaches", json={
        "name": "J", "email": "dup@club.com", "password": "x"
    }, headers=_auth())
    r = client.post("/api/admin/team-coach/coaches", json={
        "name": "J2", "email": "dup@club.com", "password": "y"
    }, headers=_auth())
    assert r.status_code == 409


def test_create_team():
    r = client.post("/api/admin/team-coach/teams", json={
        "name": "U16 Girls", "season": "Fall 2026"
    }, headers=_auth())
    assert r.status_code == 201
    assert "team_id" in r.json()


def test_grant_coach_access():
    coach_id = client.post("/api/admin/team-coach/coaches", json={
        "name": "C", "email": "c@c.com", "password": "p"
    }, headers=_auth()).json()["coach_id"]
    team_id = client.post("/api/admin/team-coach/teams", json={
        "name": "T", "season": "S"
    }, headers=_auth()).json()["team_id"]
    r = client.post(
        f"/api/admin/team-coach/teams/{team_id}/coaches/{coach_id}",
        headers=_auth()
    )
    assert r.status_code == 201


def test_add_athlete_to_roster():
    team_id = client.post("/api/admin/team-coach/teams", json={
        "name": "T2", "season": "S"
    }, headers=_auth()).json()["team_id"]
    r = client.post(f"/api/admin/team-coach/teams/{team_id}/roster", json={
        "athlete_id": 1
    }, headers=_auth())
    assert r.status_code == 201


def test_no_admin_token_401():
    r = client.post("/api/admin/team-coach/coaches", json={
        "name": "x", "email": "x@x.com", "password": "x"
    })
    assert r.status_code == 401
