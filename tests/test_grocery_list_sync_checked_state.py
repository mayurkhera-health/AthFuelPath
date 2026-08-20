"""Regression test: POST /api/recipes/selections/sync-grocery-list used to
delete-then-reinsert every recipe_list_items row on every add/remove of ANY
recipe selection that week — resetting `checked` to unchecked for every item
still needed by an untouched, still-selected recipe. Not limited to the
shared-ingredient-name case; any add/remove of any recipe in the week reset
everything.
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

WEEK_START = "2026-06-14"


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def _make_athlete(client):
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": "sync-checked@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    }, headers=auth_headers("parent", parent_id=pid))
    return a.json()["id"]


def _select(client, headers, aid, recipe_id, window_key):
    r = client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": WEEK_START,
        "fueling_window_key": window_key, "recipe_id": recipe_id,
    }, headers=headers)
    assert r.status_code == 201, r.text


def test_checking_an_item_survives_removing_an_unrelated_recipe(client):
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)

    # R001 (eggs, turkey bacon, tortilla, cheddar, spinach) and R002 (yogurt,
    # granola, berries, honey, chia) share no ingredients — any checked-state
    # loss on R001's items after touching only R002 proves the bug.
    _select(client, headers, aid, "R001", "everyday_breakfast")
    sel2 = client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": WEEK_START,
        "fueling_window_key": "everyday_lunch", "recipe_id": "R002",
    }, headers=headers)
    assert sel2.status_code == 201, sel2.text
    selection2_id = sel2.json()["selection"]["id"]

    sync1 = client.post(
        "/api/recipes/selections/sync-grocery-list",
        json={"athlete_id": aid, "week_start": WEEK_START}, headers=headers,
    )
    assert sync1.status_code == 200, sync1.text

    list_before = client.get(
        f"/api/recipes/grocery-list?athlete_id={aid}&week_start={WEEK_START}", headers=headers,
    ).json()
    eggs_item = next(
        i for g in list_before["groups"] for i in g["items"] if i["name"].lower() == "eggs"
    )
    assert eggs_item["checked"] is False

    check_resp = client.patch(
        f"/api/recipes/grocery-list/items/{eggs_item['id']}", json={"checked": True}, headers=headers,
    )
    assert check_resp.status_code == 200, check_resp.text
    assert check_resp.json()["checked"] is True

    # Remove the UNRELATED recipe (R002) — R001/eggs is untouched.
    del_resp = client.delete(
        f"/api/recipes/selections/{selection2_id}", params={"athlete_id": aid}, headers=headers,
    )
    assert del_resp.status_code == 200, del_resp.text

    sync2 = client.post(
        "/api/recipes/selections/sync-grocery-list",
        json={"athlete_id": aid, "week_start": WEEK_START}, headers=headers,
    )
    assert sync2.status_code == 200, sync2.text

    list_after = client.get(
        f"/api/recipes/grocery-list?athlete_id={aid}&week_start={WEEK_START}", headers=headers,
    ).json()
    eggs_after = next(
        i for g in list_after["groups"] for i in g["items"] if i["name"].lower() == "eggs"
    )
    assert eggs_after["checked"] is True, (
        "checking an item was lost after removing a completely unrelated recipe"
    )

    # R002's ingredients (e.g. granola) must actually be gone now.
    remaining_names = {i["name"].lower() for g in list_after["groups"] for i in g["items"]}
    assert "granola" not in remaining_names
