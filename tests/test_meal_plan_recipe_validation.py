"""Regression tests: POST /api/meal-plan/windows/{window_key}/items used to
accept `recipe` as a bare, unvalidated dict — any malformed payload (missing
fields, wrong types) was stored and re-served as-is. Now validated against
MealPlanRecipeIn, which mirrors fuelup-mobile/types/recipe.ts's Recipe shape.
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

VALID_RECIPE = {
    "name": "Post-Game Recovery Bowl",
    "category": "recovery",
    "calories": 450,
    "protein_g": 30,
    "carbs_g": 55,
    "fat_g": 12,
    "ingredients": ["chicken breast", "rice", "broccoli"],
    "preparation_notes": "Grill chicken, steam broccoli, serve over rice.",
}


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
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"mealplan-recipe{_counter['n']}@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    })
    return a.json()["id"]


def test_valid_recipe_payload_is_accepted_and_round_trips(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post(
        "/api/meal-plan/windows/everyday_lunch/items",
        json={"athlete_id": aid, "plan_date": "2026-06-16", "recipe": VALID_RECIPE},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["text"] == "Post-Game Recovery Bowl"
    assert body["recipe"]["calories"] == 450
    assert body["recipe"]["ingredients"] == ["chicken breast", "rice", "broccoli"]


def test_recipe_missing_required_field_is_rejected_with_422(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    malformed = {k: v for k, v in VALID_RECIPE.items() if k != "calories"}
    r = client.post(
        "/api/meal-plan/windows/everyday_lunch/items",
        json={"athlete_id": aid, "plan_date": "2026-06-16", "recipe": malformed},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_recipe_with_wrong_field_type_is_rejected_with_422(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    malformed = {**VALID_RECIPE, "ingredients": "chicken, rice, broccoli"}  # str, not list
    r = client.post(
        "/api/meal-plan/windows/everyday_lunch/items",
        json={"athlete_id": aid, "plan_date": "2026-06-16", "recipe": malformed},
        headers=headers,
    )
    assert r.status_code == 422, r.text
