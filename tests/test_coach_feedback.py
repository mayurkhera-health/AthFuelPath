"""Integration tests for the coach thumbs-feedback route."""

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
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def test_thumbs_up_saved_and_201(client):
    r = client.post("/api/coach/feedback", json={
        "rating": "up",
        "question": "What should I eat before practice?",
        "answer_excerpt": "Aim for carbs 3 hours before...",
        "window_key": "pre_event_meal",
        "recipe_intent": 0,
        "role_hint": "athlete",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["id"], int)

    row = get_conn().execute(
        "SELECT rating, question, window_key, recipe_intent, role_hint, reason "
        "FROM coach_feedback WHERE id = %s", (body["id"],),
    ).fetchone()
    assert row["rating"] == "up"
    assert row["question"] == "What should I eat before practice?"
    assert row["window_key"] == "pre_event_meal"
    assert row["recipe_intent"] == 0
    assert row["role_hint"] == "athlete"
    assert row["reason"] is None  # nullable, omitted


def test_thumbs_down_saved(client):
    r = client.post("/api/coach/feedback", json={"rating": "down", "role_hint": "parent"})
    assert r.status_code == 201, r.text
    assert r.json()["ok"] is True


def test_invalid_rating_rejected(client):
    before = get_conn().execute("SELECT COUNT(*) AS c FROM coach_feedback").fetchone()["c"]
    r = client.post("/api/coach/feedback", json={"rating": "meh"})
    assert r.status_code == 400, r.text
    after = get_conn().execute("SELECT COUNT(*) AS c FROM coach_feedback").fetchone()["c"]
    assert after == before, "an invalid rating must not be persisted"


def test_minimal_payload_ok(client):
    # Only rating is required; everything else is nullable telemetry.
    r = client.post("/api/coach/feedback", json={"rating": "up"})
    assert r.status_code == 201, r.text
    assert r.json()["ok"] is True
