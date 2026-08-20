"""Atomic onboarding endpoint: parent + athlete created in one transaction."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    # Isolate THIS file's count-based assertions without touching seed data other
    # test files rely on: clear only the account tables, in FK-safe order.
    for tbl in ("events", "athletes", "parents"):
        keepalive.execute(f"DELETE FROM {tbl}")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def _body(email="new@example.com"):
    return {
        "parent": {"full_name": "Pat Parent", "email": email, "consent_confirmed": True},
        "athlete": {"first_name": "Ari", "age": 14, "gender": "girl",
                    "weight_lbs": 110, "height_ft": 5, "height_in": 6},
    }


def test_complete_creates_parent_and_athlete(client):
    r = client.post("/api/onboarding/complete", json=_body())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["parent"]["email"] == "new@example.com"
    assert data["athlete"]["first_name"] == "Ari"
    assert data["athlete"]["parent_id"] == data["parent"]["id"]
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) AS n FROM parents").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM athletes").fetchone()["n"] == 1


def test_duplicate_email_returns_409_and_writes_nothing(client):
    assert client.post("/api/onboarding/complete", json=_body("dup@example.com")).status_code == 201
    r = client.post("/api/onboarding/complete", json=_body("dup@example.com"))
    assert r.status_code == 409, r.text
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) AS n FROM parents").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM athletes").fetchone()["n"] == 1


def test_missing_consent_returns_400_and_writes_nothing(client):
    body = _body("noconsent@example.com")
    body["parent"]["consent_confirmed"] = False
    r = client.post("/api/onboarding/complete", json=body)
    assert r.status_code == 400, r.text
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) AS n FROM parents").fetchone()["n"] == 0


def test_athlete_failure_rolls_back_parent(client, monkeypatch):
    import api.routes.onboarding as ob
    real_norm = ob.normalize_season_phase
    def boom(_):
        raise RuntimeError("athlete insert blew up")
    monkeypatch.setattr(ob, "normalize_season_phase", boom)
    r = client.post("/api/onboarding/complete", json=_body("rollback@example.com"))
    assert r.status_code == 500
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) AS n FROM parents").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM athletes").fetchone()["n"] == 0
    monkeypatch.setattr(ob, "normalize_season_phase", real_norm)


def test_email_exists_check(client):
    assert client.get("/api/parents/exists", params={"email": "who@example.com"}).json() == {"exists": False}
    client.post("/api/onboarding/complete", json=_body("who@example.com"))
    assert client.get("/api/parents/exists", params={"email": "WHO@example.com"}).json() == {"exists": True}
