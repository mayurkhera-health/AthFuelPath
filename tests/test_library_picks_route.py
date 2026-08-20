"""Integration tests for GET /api/library/picks/{athlete_id} — "Alex's Picks
For You". Covers the two fixes: (1) picks are now generated lazily on read
instead of requiring a manual admin-key curl per athlete per week, and
(2) the caller must prove ownership via a session token — a client-supplied
parent_id query param is spoofable and is no longer trusted at all."""

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
           VALUES (%s, %s, %s, %s, 'athlete', 3, 'Test Author', '2026-01-01', 1)""",
        (f"Article about {category}", "summary", "body", category),
    )
    conn.commit()
    conn.close()


def test_picks_generate_lazily_on_first_read(client):
    athlete_id, parent_id = _make_athlete(client)
    _seed_article()

    r = client.get(f"/api/library/picks/{athlete_id}", headers=auth_headers("parent", parent_id=parent_id))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["alex_reason"]


def test_picks_are_idempotent_across_repeated_reads(client):
    athlete_id, parent_id = _make_athlete(client)
    _seed_article()
    headers = auth_headers("parent", parent_id=parent_id)

    first = client.get(f"/api/library/picks/{athlete_id}", headers=headers).json()
    second = client.get(f"/api/library/picks/{athlete_id}", headers=headers).json()
    assert first == second
    assert len(second) == 1  # not duplicated on the second read


def test_athlete_token_can_read_own_picks(client):
    athlete_id, _ = _make_athlete(client)
    _seed_article()

    r = client.get(f"/api/library/picks/{athlete_id}", headers=auth_headers("athlete", athlete_id=athlete_id))
    assert r.status_code == 200, r.text


def test_unrelated_parent_token_403s(client):
    athlete_id, real_parent_id = _make_athlete(client)
    _, other_parent_id = _make_athlete(client)
    _seed_article()

    r = client.get(f"/api/library/picks/{athlete_id}", headers=auth_headers("parent", parent_id=other_parent_id))
    assert r.status_code == 403


def test_missing_session_401s(client):
    athlete_id, _ = _make_athlete(client)
    r = client.get(f"/api/library/picks/{athlete_id}")
    assert r.status_code == 401


def test_unknown_athlete_id_404s(client):
    _, parent_id = _make_athlete(client)
    r = client.get("/api/library/picks/999999", headers=auth_headers("parent", parent_id=parent_id))
    assert r.status_code == 404


# ─── Copy rule: win-framed, never deficit-framed ─────────────────────────────

def test_build_reason_is_never_deficit_framed():
    """CLAUDE.md rule 5: positive/win-framed copy only. The old
    '{name} has been low N of M days' phrasing is banned outright."""
    from api.services.library_service import _build_reason

    banned = ["missed", "behind", "deficit", "failed", "warning", "lacking", "critical", "low", "has been low"]
    for nutrient_key in ("iron_mg", "calcium_mg", "carbs_g", "water_oz", "unknown_nutrient"):
        reason = _build_reason({"nutrient": nutrient_key, "days_below": 3, "days_logged": 3})
        lowered = reason.lower()
        for word in banned:
            assert word not in lowered, f"{reason!r} contains banned word {word!r}"
        assert "3" not in reason  # never quantifies the gap
