"""Integration tests for the Instacart grocery-handoff feedback route."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def test_feedback_saved_and_201(client):
    r = client.post("/api/instacart/feedback", json={
        "athlete_id": 1,
        "outcome": "worked_great",
        "would_use_again": "yes",
    }, headers=auth_headers("athlete", athlete_id=1))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["id"], int)

    row = get_conn().execute(
        "SELECT athlete_id, outcome, would_use_again, comment FROM instacart_handoff_feedback WHERE id = %s",
        (body["id"],),
    ).fetchone()
    assert row["athlete_id"] == 1
    assert row["outcome"] == "worked_great"
    assert row["would_use_again"] == "yes"
    assert row["comment"] is None


def test_minimal_payload_ok_without_athlete_id(client):
    r = client.post("/api/instacart/feedback", json={
        "outcome": "some_issues",
        "would_use_again": "maybe",
    }, headers=auth_headers("athlete", athlete_id=999))
    assert r.status_code == 201, r.text
    assert r.json()["ok"] is True


def test_invalid_outcome_rejected(client):
    before = get_conn().execute("SELECT COUNT(*) AS c FROM instacart_handoff_feedback").fetchone()["c"]
    r = client.post(
        "/api/instacart/feedback", json={"outcome": "meh", "would_use_again": "yes"},
        headers=auth_headers("athlete", athlete_id=999),
    )
    assert r.status_code == 400, r.text
    after = get_conn().execute("SELECT COUNT(*) AS c FROM instacart_handoff_feedback").fetchone()["c"]
    assert after == before, "an invalid outcome must not be persisted"


def test_invalid_would_use_again_rejected(client):
    before = get_conn().execute("SELECT COUNT(*) AS c FROM instacart_handoff_feedback").fetchone()["c"]
    r = client.post(
        "/api/instacart/feedback", json={"outcome": "worked_great", "would_use_again": "nah"},
        headers=auth_headers("athlete", athlete_id=999),
    )
    assert r.status_code == 400, r.text
    after = get_conn().execute("SELECT COUNT(*) AS c FROM instacart_handoff_feedback").fetchone()["c"]
    assert after == before, "an invalid would_use_again must not be persisted"
