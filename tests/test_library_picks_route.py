"""Integration tests for GET /api/library/picks/{athlete_id} — "Alex's Picks
For You". Covers the two fixes: (1) picks are now generated lazily on read
instead of requiring a manual admin-key curl per athlete per week, and
(2) the caller must prove they know the athlete's real parent_id."""

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
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client):
    _counter["n"] += 1
    email = f"picks{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    })
    assert a.status_code == 201, a.text
    return a.json()["id"], parent_id


def _seed_article(category="iron"):
    conn = get_conn()
    conn.execute(
        """INSERT INTO articles (title, summary, body_markdown, category, audience,
               read_time_min, author, published_date, is_active)
           VALUES (?, ?, ?, ?, 'athlete', 3, 'Test Author', '2026-01-01', 1)""",
        (f"Article about {category}", "summary", "body", category),
    )
    conn.commit()
    conn.close()


def test_picks_generate_lazily_on_first_read(client):
    athlete_id, parent_id = _make_athlete(client)
    _seed_article()

    r = client.get(f"/api/library/picks/{athlete_id}", params={"parent_id": parent_id})
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["alex_reason"]


def test_picks_are_idempotent_across_repeated_reads(client):
    athlete_id, parent_id = _make_athlete(client)
    _seed_article()

    first = client.get(f"/api/library/picks/{athlete_id}", params={"parent_id": parent_id}).json()
    second = client.get(f"/api/library/picks/{athlete_id}", params={"parent_id": parent_id}).json()
    assert first == second
    assert len(second) == 1  # not duplicated on the second read


def test_wrong_parent_id_403s(client):
    athlete_id, real_parent_id = _make_athlete(client)
    _, other_parent_id = _make_athlete(client)
    _seed_article()

    r = client.get(f"/api/library/picks/{athlete_id}", params={"parent_id": other_parent_id})
    assert r.status_code == 403


def test_missing_parent_id_422s(client):
    athlete_id, _ = _make_athlete(client)
    r = client.get(f"/api/library/picks/{athlete_id}")
    assert r.status_code == 422


def test_unknown_athlete_id_404s(client):
    r = client.get("/api/library/picks/999999", params={"parent_id": 1})
    assert r.status_code == 404
