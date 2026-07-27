import os
os.environ["DB_PATH"] = ":memory:"
import pytest
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn

@pytest.fixture
def db():
    keep = get_conn(); init_db(); run_all()
    yield keep
    keep.close()

def test_pantry_list_items_table_exists(db):
    cols = [r[1] for r in db.execute("PRAGMA table_info(pantry_list_items)").fetchall()]
    assert cols, "pantry_list_items table missing"
    for c in ["id","athlete_id","week_start","food_id","name","cue_label",
              "purchase_unit","role","meal_context","must_have","checked"]:
        assert c in cols, f"missing column {c}"


from fastapi.testclient import TestClient
from api.main import app
import api.routes.pantry as pantry_route
from tests.conftest import auth_headers

@pytest.fixture
def client(db):
    with TestClient(app) as c:
        yield c

_counter = {"n": 0}

def _make_athlete(client):
    _counter["n"] += 1
    p = client.post("/api/parents/", json={"full_name":"P","email":f"pan{_counter['n']}@test.com","consent_confirmed":True})
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={"parent_id":pid,"first_name":"Ari","age":15,"gender":"girl",
        "weight_lbs":110,"height_ft":5,"height_in":6})
    return a.json()["id"]

def test_generate_happy_path(client, monkeypatch):
    aid = _make_athlete(client)
    monkeypatch.setattr(pantry_route.claude_ai, "prompt8_pantry_plan",
        lambda *a, **k: {"items":[{"food_id":"banana_ripe","meal_context":"pre_training_fuel","must_have":True}], "reasoning":"go"})
    r = client.post(
        f"/api/pantry/generate?athlete_id={aid}&week_start=2026-06-29",
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item_count"] >= 1

def test_generate_ai_fail_uses_fallback_not_502(client, monkeypatch):
    aid = _make_athlete(client)
    monkeypatch.setattr(pantry_route.claude_ai, "prompt8_pantry_plan",
        lambda *a, **k: {"items": [], "reasoning": ""})
    r = client.post(
        f"/api/pantry/generate?athlete_id={aid}&week_start=2026-06-29",
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text          # fallback, not 502
    assert r.json()["item_count"] >= 1


def test_suggest_replacement_ai_fail_uses_fallback(client, monkeypatch):
    aid = _make_athlete(client)
    monkeypatch.setattr(pantry_route.claude_ai, "prompt8_pantry_plan",
        lambda *a, **k: {"items":[{"food_id":"banana_ripe","meal_context":"snacks_everyday","must_have":False}], "reasoning":""})
    headers = auth_headers("athlete", athlete_id=aid)
    client.post(f"/api/pantry/generate?athlete_id={aid}&week_start=2026-06-29", headers=headers)
    monkeypatch.setattr(pantry_route.claude_ai, "prompt_suggest_replacement", lambda **k: {"food_id": None})
    r = client.post("/api/pantry/suggest-replacement", json={
        "athlete_id": aid, "week_start": "2026-06-29", "food_id": "banana_ripe",
        "food_name": "Banana (ripe)", "meal_context": "snacks_everyday"}, headers=headers)
    assert r.status_code == 200, r.text
    # a same-role replacement (carb) should have been inserted by the fallback
    names = [i["food_id"] for g in r.json()["groups"] for i in g["items"]]
    assert "banana_ripe" not in names


def _insert_item(db, aid, ws, food_id, name):
    db.execute(
        "INSERT INTO pantry_list_items "
        "(athlete_id, week_start, food_id, name, cue_label, purchase_unit, role, meal_context, must_have, checked) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (aid, ws, food_id, name, "", "", "protein", "recovery", 0, 0),
    )


def test_excluded_allergen_stays_gone_after_swapping_another_item(client, db, monkeypatch):
    """Repro: mark Tuna as allergy, then swap a DIFFERENT item -> Tuna must NOT reappear (Gap #1)."""
    aid = _make_athlete(client)
    ws = "2026-06-29"
    # seed a list with a real swap-target (banana_ripe)
    monkeypatch.setattr(pantry_route.claude_ai, "prompt8_pantry_plan",
        lambda *a, **k: {"items":[{"food_id":"banana_ripe","meal_context":"snacks_everyday","must_have":False}], "reasoning":""})
    headers = auth_headers("athlete", athlete_id=aid)
    assert client.post(
        f"/api/pantry/generate?athlete_id={aid}&week_start={ws}", headers=headers
    ).status_code == 200
    # add an allergen row directly (name carries a parenthetical unit suffix)
    _insert_item(db, aid, ws, "tuna_canned", "Tuna (5 oz can)")
    db.commit()
    # mark Tuna as allergy (mobile sends the paren-stripped name)
    assert client.post(
        "/api/pantry/exclude",
        json={"athlete_id": aid, "food_id": "tuna_canned", "food_name": "Tuna"}, headers=headers,
    ).status_code == 200
    # Gap #1 (isolated): exclude must delete the stored row, not just record the dislike
    assert db.execute(
        "SELECT COUNT(*) FROM pantry_list_items WHERE athlete_id=? AND food_id='tuna_canned'",
        (aid,)).fetchone()[0] == 0, "exclude did not delete the stored allergen row (Gap #1)"
    # swap the OTHER item (banana) -> AI fail -> fallback -> returns the full list
    monkeypatch.setattr(pantry_route.claude_ai, "prompt_suggest_replacement", lambda **k: {"food_id": None})
    r = client.post("/api/pantry/suggest-replacement", json={
        "athlete_id": aid, "week_start": ws, "food_id": "banana_ripe",
        "food_name": "Banana (ripe)", "meal_context": "snacks_everyday"}, headers=headers)
    assert r.status_code == 200, r.text
    ids = [i["food_id"] for g in r.json()["groups"] for i in g["items"]]
    assert "tuna_canned" not in ids, "excluded Tuna reappeared after swapping a different item"


def test_get_pantry_list_filters_disliked_with_paren_normalization(client, db):
    """Gap #2: a stored 'Tuna (5 oz can)' row is filtered when bare 'Tuna' is disliked."""
    from api.services.pantry_service import get_pantry_list
    aid = _make_athlete(client)
    ws = "2026-06-29"
    _insert_item(db, aid, ws, "tuna_canned", "Tuna (5 oz can)")
    _insert_item(db, aid, ws, "banana_ripe", "Banana (ripe)")
    db.execute(
        "INSERT OR REPLACE INTO athlete_food_prefs (athlete_id, food_name, preference, category) "
        "VALUES (?, 'Tuna', 'disliked', NULL)", (aid,))
    db.commit()
    ids = [i["food_id"] for i in get_pantry_list(aid, ws, db)]
    assert "tuna_canned" not in ids, "disliked Tuna not filtered despite '(5 oz can)' suffix"
    assert "banana_ripe" in ids, "non-disliked item was wrongly filtered"
