"""Regression tests for free-text dietary_restrictions bricking the pantry.

Prod bug (athlete 65): dietary_restrictions='Red meat' matched no diet_tag, so
safe_foods_for_athlete returned 0 of 67 foods and /pantry/generate 422'd for
every week. Free text must map to known diet/allergen filters where possible
and never zero out the food list on unrecognized tokens.
"""
import os
os.environ["DB_PATH"] = ":memory:"
import pytest

from api.services.food_db import FOOD_DATABASE
from api.services.pantry_service import safe_foods_for_athlete


def _safe(restrictions=None, allergies=None):
    return safe_foods_for_athlete({"allergies": allergies, "dietary_restrictions": restrictions})


# ── free text must never zero out the list ─────────────────────────────────────

def test_unrecognized_free_text_does_not_zero_out():
    # athlete 65 in prod — the showstopper
    assert len(_safe("Red meat")) > 0

def test_placeholder_example_lactose_intolerant_maps_to_dairy_free():
    # the onboarding placeholder literally suggests this phrasing
    safe = _safe("lactose intolerant")
    assert len(safe) > 0
    assert all("dairy_free" in f.get("diet_tags", []) for f in safe)

def test_hyphenated_gluten_free_maps_to_tag():
    safe = _safe("Gluten-free")
    assert len(safe) > 0
    assert all("gluten_free" in f.get("diet_tags", []) for f in safe)


# ── "-Free" allergen phrasings from older onboarding (athletes 24/29/46/47) ────

def test_egg_free_excludes_egg_foods_only():
    safe = _safe("Egg-Free")
    assert len(safe) > 0
    assert all("eggs" not in f.get("allergens", []) for f in safe)

def test_shellfish_free_excludes_shellfish_only():
    safe = _safe("Shellfish-Free")
    assert len(safe) > 0
    assert all("shellfish" not in f.get("allergens", []) for f in safe)

def test_soy_free_excludes_soy_only():
    safe = _safe("Soy-Free")
    assert len(safe) > 0
    assert all("soy" not in f.get("allergens", []) for f in safe)


# ── existing exact-enum behavior must keep working ─────────────────────────────

def test_vegetarian_exact_still_filters():
    safe = _safe("vegetarian")
    assert len(safe) > 0
    assert all("vegetarian" in f.get("diet_tags", []) for f in safe)

def test_combined_tokens_all_apply():
    safe = _safe("vegetarian, gluten-free")
    assert len(safe) > 0
    for f in safe:
        assert "vegetarian" in f.get("diet_tags", [])
        assert "gluten_free" in f.get("diet_tags", [])

def test_none_and_empty_return_full_db():
    assert len(_safe(None)) == len(FOOD_DATABASE)
    assert len(_safe("none")) == len(FOOD_DATABASE)

def test_allergies_column_still_filters():
    safe = _safe(None, allergies="dairy")
    assert len(safe) > 0
    assert all("dairy" not in f.get("allergens", []) for f in safe)

def test_free_text_wheat_allergy_maps_to_gluten():
    # prod has allergies='wheat' (typed via the "Other" chip) — must exclude gluten foods
    safe = _safe(None, allergies="wheat")
    assert len(safe) > 0
    assert all("gluten" not in f.get("allergens", []) for f in safe)


# ── route: generate must succeed for free-text restrictions, and AI items must
#    be validated against the safe list (not just existence in the food DB) ─────

from fastapi.testclient import TestClient
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
import api.routes.pantry as pantry_route
from tests.conftest import auth_headers

@pytest.fixture
def db():
    keep = get_conn(); init_db(); run_all()
    yield keep
    keep.close()

@pytest.fixture
def client(db):
    with TestClient(app) as c:
        yield c

_counter = {"n": 0}

def _make_athlete(client, **extra):
    _counter["n"] += 1
    p = client.post("/api/parents/", json={"full_name": "P", "email": f"restr{_counter['n']}@test.com", "consent_confirmed": True})
    pid = p.json()["id"]
    body = {"parent_id": pid, "first_name": "Ari", "age": 15, "gender": "girl",
            "weight_lbs": 110, "height_ft": 5, "height_in": 6, **extra}
    a = client.post("/api/athletes/", json=body)
    return a.json()["id"]

def test_generate_with_free_text_restriction_succeeds(client, monkeypatch):
    # exact prod repro: 'Red meat' + AI returns nothing → must fall back, not 422
    aid = _make_athlete(client, dietary_restrictions="Red meat")
    monkeypatch.setattr(pantry_route.claude_ai, "prompt8_pantry_plan",
                        lambda *a, **k: {"items": [], "reasoning": ""})
    r = client.post(
        f"/api/pantry/generate?athlete_id={aid}&week_start=2026-06-29",
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item_count"] >= 1

def test_generate_rejects_ai_items_outside_safe_list(client, monkeypatch):
    # AI hallucinating a real-but-unsafe food_id must not leak into the list
    aid = _make_athlete(client, allergies="dairy")
    monkeypatch.setattr(pantry_route.claude_ai, "prompt8_pantry_plan",
                        lambda *a, **k: {"items": [{"food_id": "milk_8oz", "meal_context": "hydration", "must_have": False}],
                                         "reasoning": ""})
    r = client.post(
        f"/api/pantry/generate?athlete_id={aid}&week_start=2026-06-29",
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    names = [i["name"] for g in r.json()["groups"] for i in g["items"]]
    assert not any("Milk" in n for n in names), f"dairy food leaked past allergy filter: {names}"


# ── prompt: unrecognized restrictions must reach the AI as a soft instruction ──

import api.services.claude_ai as ai

def test_prompt8_includes_dietary_restrictions_text(monkeypatch):
    captured = {}
    def fake_converse(**k):
        captured["prompt"] = k.get("user", "")
        return '{"items":[],"reasoning":""}'
    monkeypatch.setattr(ai, "converse_text", fake_converse)
    athlete = {"first_name": "A", "age": 15, "gender": "girl", "season_phase": "in_season",
               "food_preferences": "loves rice", "dietary_restrictions": "Red meat"}
    slot_plan = {"week_summary": {}, "slots": []}
    ai.prompt8_pantry_plan(athlete, [], slot_plan, [])
    assert "Red meat" in captured.get("prompt", ""), "restrictions not passed to AI prompt"
