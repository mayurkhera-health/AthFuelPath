"""Regression test for GET /api/recipes/for-window ignoring dietary_restrictions.

Before this fix, get_recipes_for_window() only passed the athlete's
allergies to recipe_db.get_valid_recipes() — dietary_restrictions
(vegetarian, vegan, etc.) were parsed elsewhere in this file for the
/generate route but never reached this one, so a vegetarian athlete could
be shown meat recipes for a window that has vegetarian options available.
"""
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


def _make_athlete(client, **extra):
    _counter["n"] += 1
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"forwindow{_counter['n']}@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    body = {
        "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6, **extra,
    }
    a = client.post("/api/athletes/", json=body)
    return a.json()["id"]


def test_no_restriction_returns_both_vegetarian_and_non_vegetarian(client):
    aid = _make_athlete(client)
    r = client.get(
        "/api/recipes/for-window", params={"athlete_id": aid, "window_key": "breakfast"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    recipes = r.json()["recipes"]
    all_dietary = [set(x.lower() for x in rec.get("dietary", [])) for rec in recipes]
    assert any("vegetarian" not in d and "vegan" not in d for d in all_dietary), (
        "expected at least one non-vegetarian recipe with no restriction set"
    )


def test_vegetarian_restriction_filters_out_non_vegetarian_recipes(client):
    aid = _make_athlete(client, dietary_restrictions="vegetarian")
    r = client.get(
        "/api/recipes/for-window", params={"athlete_id": aid, "window_key": "breakfast"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    recipes = r.json()["recipes"]
    assert recipes, "expected at least one vegetarian breakfast recipe to remain"
    for rec in recipes:
        dietary = [x.lower() for x in rec.get("dietary", [])]
        assert "vegetarian" in dietary or "vegan" in dietary, (
            f"{rec['name']!r} has no vegetarian/vegan tag but was returned for a vegetarian athlete"
        )
