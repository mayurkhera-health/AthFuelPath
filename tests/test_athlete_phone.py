"""
Phone field tests for athlete endpoints.

Covers:
  - POST /api/athletes/ (AthleteCreate)
  - PUT  /api/athletes/:id (update_athlete)
  - POST /api/onboarding/complete (OnboardingComplete → OnboardingAthlete)

Each endpoint must: accept a valid phone, persist it, return it in the
response, reject a malformed number with 422, and tolerate omission
(phone remains NULL / unchanged).
"""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    for tbl in ("events", "athletes", "parents"):
        keepalive.execute(f"DELETE FROM {tbl}")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_parent(conn):
    cur = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        ("Pat Parent", "pat@example.com", datetime.utcnow().isoformat(), True),
    )
    conn.commit()
    return cur.fetchone()["id"]


def _athlete_body(parent_id, **overrides):
    base = {
        "parent_id": parent_id,
        "first_name": "Nora",
        "age": 15,
        "gender": "Girl",
        "weight_lbs": 115,
        "height_ft": 5,
        "height_in": 5,
    }
    base.update(overrides)
    return base


def _onboarding_body(**athlete_overrides):
    base = {
        "parent": {
            "full_name": "Pat Parent",
            "email": "ob@example.com",
            "consent_confirmed": True,
        },
        "athlete": {
            "first_name": "Nora",
            "age": 15,
            "gender": "Girl",
            "weight_lbs": 115,
            "height_ft": 5,
            "height_in": 5,
        },
    }
    base["athlete"].update(athlete_overrides)
    return base


# ── POST /api/athletes/ ───────────────────────────────────────────────────────

class TestCreateAthletePhone:
    def test_phone_persisted_and_returned(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()

        r = client.post("/api/athletes/", json=_athlete_body(pid, phone="(408) 555-1234"))
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["phone"] == "(408) 555-1234"

        conn = get_conn()
        row = conn.execute("SELECT phone FROM athletes WHERE id = %s", (data["id"],)).fetchone()
        conn.close()
        assert row["phone"] == "(408) 555-1234"

    def test_phone_omitted_stored_as_null(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()

        r = client.post("/api/athletes/", json=_athlete_body(pid))
        assert r.status_code == 201, r.text
        assert r.json()["phone"] is None

    def test_phone_invalid_format_rejected(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()

        r = client.post("/api/athletes/", json=_athlete_body(pid, phone="123"))
        assert r.status_code == 422, r.text

    def test_phone_digits_only_accepted(self, client):
        """Plain 10-digit string (no formatting) must be accepted."""
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()

        r = client.post("/api/athletes/", json=_athlete_body(pid, phone="4085551234"))
        assert r.status_code == 201, r.text


# ── PUT /api/athletes/:id ─────────────────────────────────────────────────────

class TestUpdateAthletePhone:
    def _create(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()
        r = client.post("/api/athletes/", json=_athlete_body(pid))
        assert r.status_code == 201, r.text
        return r.json()

    def test_phone_added_via_update(self, client):
        athlete = self._create(client)
        r = client.put(
            f"/api/athletes/{athlete['id']}",
            json={**athlete, "phone": "(650) 555-9999"},
            headers=auth_headers("athlete", athlete_id=athlete["id"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["phone"] == "(650) 555-9999"

        conn = get_conn()
        row = conn.execute("SELECT phone FROM athletes WHERE id = %s", (athlete["id"],)).fetchone()
        conn.close()
        assert row["phone"] == "(650) 555-9999"

    def test_phone_preserved_when_omitted_from_update(self, client):
        """Older clients that don't send phone must not clobber an existing value."""
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()
        r = client.post("/api/athletes/", json=_athlete_body(pid, phone="(408) 555-1234"))
        athlete = r.json()

        payload = {k: v for k, v in athlete.items() if k != "phone"}
        r2 = client.put(
            f"/api/athletes/{athlete['id']}", json=payload,
            headers=auth_headers("athlete", athlete_id=athlete["id"]),
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["phone"] == "(408) 555-1234"

    def test_phone_invalid_rejected_on_update(self, client):
        athlete = self._create(client)
        r = client.put(
            f"/api/athletes/{athlete['id']}",
            json={**athlete, "phone": "not-a-phone"},
            headers=auth_headers("athlete", athlete_id=athlete["id"]),
        )
        assert r.status_code == 422, r.text


# ── POST /api/onboarding/complete ────────────────────────────────────────────

class TestOnboardingPhone:
    def test_phone_persisted_via_onboarding(self, client):
        body = _onboarding_body(phone="(510) 555-7777")
        r = client.post("/api/onboarding/complete", json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["athlete"]["phone"] == "(510) 555-7777"

        conn = get_conn()
        row = conn.execute(
            "SELECT phone FROM athletes WHERE id = %s", (data["athlete"]["id"],)
        ).fetchone()
        conn.close()
        assert row["phone"] == "(510) 555-7777"

    def test_phone_omitted_in_onboarding_stored_as_null(self, client):
        r = client.post("/api/onboarding/complete", json=_onboarding_body())
        assert r.status_code == 201, r.text
        assert r.json()["athlete"]["phone"] is None

    def test_phone_invalid_rejected_in_onboarding(self, client):
        body = _onboarding_body(phone="555-12")
        r = client.post("/api/onboarding/complete", json=body)
        assert r.status_code == 422, r.text
