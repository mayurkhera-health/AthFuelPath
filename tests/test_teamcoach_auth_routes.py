import os
os.environ.setdefault("TEAM_COACH_SESSION_SECRET", "test-coach-secret")

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import get_conn
from db.setup import init_db
from api.services.teamcoach_auth_service import hash_password


@pytest.fixture(autouse=True)
def seed():
    init_db()
    conn = get_conn()
    pw_hash, salt = hash_password("Str0ng!Pass")
    conn.execute(
        "INSERT INTO coaches (name, email, password_hash, salt) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (email) DO NOTHING",
        ("Jane Coach", "jane@club.com", pw_hash, salt),
    )
    conn.commit()
    conn.close()


client = TestClient(app)


def test_login_success():
    r = client.post("/api/team-coach/auth/login", json={
        "email": "jane@club.com",
        "password": "Str0ng!Pass",
    })
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["coach_name"] == "Jane Coach"


def test_login_wrong_password_401():
    r = client.post("/api/team-coach/auth/login", json={
        "email": "jane@club.com", "password": "wrong"
    })
    assert r.status_code == 401


def test_login_unknown_email_401():
    r = client.post("/api/team-coach/auth/login", json={
        "email": "nobody@club.com", "password": "Str0ng!Pass"
    })
    assert r.status_code == 401


def test_me_returns_coach():
    token = client.post("/api/team-coach/auth/login", json={
        "email": "jane@club.com", "password": "Str0ng!Pass"
    }).json()["token"]
    r = client.get("/api/team-coach/auth/me",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "jane@club.com"


def test_me_no_token_401():
    r = client.get("/api/team-coach/auth/me")
    assert r.status_code == 401


def test_me_bad_token_401():
    r = client.get("/api/team-coach/auth/me",
                   headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_admin_token_rejected_on_coach_route():
    os.environ.setdefault("ADMIN_SESSION_SECRET", "admin-secret")
    from api.services.admin_auth import mint_token as admin_mint
    admin_token = admin_mint()
    r = client.get("/api/team-coach/auth/me",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 401
