"""Integration tests for the Fuel IQ API surface (api/routes/fueliq.py)."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.services import fueliq_service as fq
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


_counter = {"n": 0}


def _make_athlete(client, age=14):
    _counter["n"] += 1
    email = f"fueliq{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": age, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6, "competition_level": "Recreational",
    })
    assert a.status_code == 201, a.text
    return a.json()["id"]


def _seed_lesson(conn, level=1, points=10):
    cur = conn.execute(
        "INSERT INTO fueliq_lessons "
        "(level, order_in_level, is_myth, title, hook, fact_body, takeaway, "
        " source_citation, points, review_status) "
        "VALUES (?, 1, 0, 'Test Lesson', 'hook', 'fact', 'takeaway', 'cite', ?, 'approved')",
        (level, points),
    )
    conn.commit()
    return cur.lastrowid


def _seed_question(conn, lesson_id, correct_option="b"):
    cur = conn.execute(
        "INSERT INTO fueliq_questions "
        "(lesson_id, question_text, option_a, option_b, option_c, correct_option, "
        " explanation, misconception_tag, order_in_lesson) "
        "VALUES (?, 'q', 'A', 'B', 'C', ?, 'because', 'tag1', 1)",
        (lesson_id, correct_option),
    )
    conn.commit()
    return cur.lastrowid


def test_hub_returns_disabled_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "false")
    aid = _make_athlete(client)
    r = client.get(f"/api/athletes/{aid}/hub", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_hub_returns_baseline_progress_when_enabled(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    r = client.get(f"/api/athletes/{aid}/hub", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["score"] == 50
    assert body["levels"] == [
        {"level": 1, "unlocked": True,  "level_name": "Kickoff"},
        {"level": 2, "unlocked": False, "level_name": "Energy Builder"},
        {"level": 3, "unlocked": False, "level_name": "Match Ready"},
        {"level": 4, "unlocked": False, "level_name": "Performance Leader"},
        {"level": 5, "unlocked": False, "level_name": "Fuel IQ Champion"},
    ]
    assert body["badges_earned"] == []


def test_lesson_detail_404_for_unknown_lesson(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    r = client.get(f"/api/athletes/{aid}/lessons/999999", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 404
    # Must be the business-logic 404 ("no such lesson"), not a generic
    # unmatched-route 404 — those are indistinguishable by status code alone.
    assert "999999" in r.json()["detail"]


def test_lesson_detail_403_when_level_locked(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    conn = get_conn()
    lesson_id = _seed_lesson(conn, level=2)
    conn.close()
    r = client.get(f"/api/athletes/{aid}/lessons/{lesson_id}", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 403


def test_lesson_detail_hides_correct_answers(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    conn = get_conn()
    lesson_id = _seed_lesson(conn, level=1)
    _seed_question(conn, lesson_id)
    conn.close()
    r = client.get(f"/api/athletes/{aid}/lessons/{lesson_id}", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Test Lesson"
    question = body["questions"][0]
    assert "correct_option" not in question
    assert "explanation" not in question


def test_complete_lesson_then_hub_reflects_new_score(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    conn = get_conn()
    lesson_id = _seed_lesson(conn, level=1, points=10)
    conn.close()

    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post(f"/api/athletes/{aid}/lessons/{lesson_id}/complete", json={"perfect_quiz": True}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["points_earned"] == 15
    assert body["already_completed"] is False

    hub = client.get(f"/api/athletes/{aid}/hub", headers=headers).json()
    assert hub["score"] == 65


def test_answer_question_returns_correctness_and_explanation(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    conn = get_conn()
    lesson_id = _seed_lesson(conn)
    question_id = _seed_question(conn, lesson_id, correct_option="b")
    conn.close()

    r = client.post(
        f"/api/athletes/{aid}/questions/{question_id}/answer", json={"selected_option": "a"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["correct"] is False
    assert body["misconception_tag"] == "tag1"


def test_answer_question_rejects_invalid_selected_option(client, monkeypatch):
    """Regression: selected_option used to be a bare str — any value other
    than "a"/"b"/"c" never matched correct_option and was silently recorded
    as a wrong answer instead of being rejected as malformed input."""
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    conn = get_conn()
    lesson_id = _seed_lesson(conn)
    question_id = _seed_question(conn, lesson_id, correct_option="b")
    conn.close()

    r = client.post(
        f"/api/athletes/{aid}/questions/{question_id}/answer", json={"selected_option": "z"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 422


def test_badges_lists_all_defined_badges_locked_until_earned(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    conn = get_conn()
    lesson_id = _seed_lesson(conn)
    conn.close()

    headers = auth_headers("athlete", athlete_id=aid)
    before = client.get(f"/api/athletes/{aid}/badges", headers=headers).json()
    assert len(before["badges"]) == 8
    assert all(b["earned"] is False for b in before["badges"])

    client.post(f"/api/athletes/{aid}/lessons/{lesson_id}/complete", json={"perfect_quiz": False}, headers=headers)

    after = client.get(f"/api/athletes/{aid}/badges", headers=headers).json()
    first_whistle = next(b for b in after["badges"] if b["key"] == "first_whistle")
    assert first_whistle["earned"] is True


def test_hub_includes_percentile_block(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    # Unique age (other tests in this file all use the default 14; valid
    # range is 13-17) so this athlete's cohort is guaranteed to be just
    # themself, regardless of test execution order in the shared in-memory DB.
    aid = _make_athlete(client, age=17)
    body = client.get(f"/api/athletes/{aid}/hub", headers=auth_headers("athlete", athlete_id=aid)).json()
    # A lone test athlete is a cohort of 1 — must report insufficient data,
    # never a fabricated percentile.
    assert body["percentile"]["insufficient_data"] is True
    assert body["percentile"]["percentile"] is None
