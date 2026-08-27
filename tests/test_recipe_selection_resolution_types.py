"""Coverage for the three recipe_selections resolution types (migration 007):
a real catalog recipe, no_recipe_needed ("I've got this"), and custom_text
(a parent-typed entry) — all three are surfaces Build 67's RecipePickerSheet
exposes, but only recipe_id ever had backend support before this fix.
"""
import os
os.environ["DB_PATH"] = ":memory:"
os.environ["EVENT_RELATIVE_WINDOWS"] = "true"

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
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"selres{_counter['n']}@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    a = client.post(
        "/api/athletes/",
        json={
            "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
            "weight_lbs": 110, "height_ft": 5, "height_in": 6,
        },
        headers=auth_headers("parent", parent_id=pid),
    )
    return a.json()["id"]


SELECTION_DATE = "2026-08-24"  # a Monday; canonical week_start is 2026-08-23


def test_normal_recipe_selection_succeeds(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/recipes/selections",
        json={"athlete_id": aid, "selection_date": SELECTION_DATE,
              "fueling_window_key": "everyday_breakfast", "recipe_id": "R001"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 201, r.text
    sel = r.json()["selection"]
    assert sel["recipe_id"] == "R001"
    assert sel["no_recipe_needed"] is False
    assert sel["custom_text"] is None


def test_no_recipe_needed_selection_succeeds(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/recipes/selections",
        json={"athlete_id": aid, "selection_date": SELECTION_DATE,
              "fueling_window_key": "everyday_lunch", "no_recipe_needed": True},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 201, r.text
    sel = r.json()["selection"]
    assert sel["recipe_id"] == ""
    assert sel["no_recipe_needed"] is True
    assert sel["custom_text"] is None


def test_custom_text_selection_succeeds(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/recipes/selections",
        json={"athlete_id": aid, "selection_date": SELECTION_DATE,
              "fueling_window_key": "everyday_dinner", "custom_text": "  Grandma's soup  "},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 201, r.text
    sel = r.json()["selection"]
    assert sel["recipe_id"] == ""
    assert sel["no_recipe_needed"] is False
    assert sel["custom_text"] == "Grandma's soup"  # stripped


def test_zero_resolutions_rejected(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/recipes/selections",
        json={"athlete_id": aid, "selection_date": SELECTION_DATE, "fueling_window_key": "everyday_snack"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 422


def test_two_resolutions_rejected(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/recipes/selections",
        json={"athlete_id": aid, "selection_date": SELECTION_DATE, "fueling_window_key": "everyday_snack",
              "recipe_id": "R001", "no_recipe_needed": True},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 422


def test_blank_custom_text_counts_as_no_resolution(client):
    """Whitespace-only custom_text strips to None — must not satisfy the
    'exactly one resolution' requirement on its own."""
    aid = _make_athlete(client)
    r = client.post(
        "/api/recipes/selections",
        json={"athlete_id": aid, "selection_date": SELECTION_DATE,
              "fueling_window_key": "everyday_snack", "custom_text": "   "},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 422


def test_week_reload_returns_all_three_types_with_null_recipe_for_non_catalog_rows(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
    }, headers=hdr)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_lunch", "no_recipe_needed": True,
    }, headers=hdr)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_dinner", "custom_text": "Soup",
    }, headers=hdr)

    r = client.get("/api/recipes/selections/week",
                    params={"athlete_id": aid, "week_start": "2026-08-23"}, headers=hdr)
    assert r.status_code == 200, r.text
    by_window = {s["fueling_window_key"]: s for s in r.json()["selections"]}
    assert len(by_window) == 3
    assert by_window["everyday_breakfast"]["recipe"]["id"] == "R001"
    assert by_window["everyday_lunch"]["recipe"] is None
    assert by_window["everyday_lunch"]["no_recipe_needed"] is True
    assert by_window["everyday_dinner"]["recipe"] is None
    assert by_window["everyday_dinner"]["custom_text"] == "Soup"


def test_reposting_custom_text_updates_existing_row_not_duplicate(client):
    """recipe_id="" is shared by no_recipe_needed and custom_text — a plain
    INSERT ON CONFLICT DO NOTHING would silently no-op a second resolution
    for the same slot. Must be a real update instead."""
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_lunch", "no_recipe_needed": True,
    }, headers=hdr)
    r2 = client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_lunch", "custom_text": "Changed my mind: soup",
    }, headers=hdr)
    assert r2.status_code == 201, r2.text

    r = client.get("/api/recipes/selections/week",
                    params={"athlete_id": aid, "week_start": "2026-08-23"}, headers=hdr)
    sels = [s for s in r.json()["selections"] if s["fueling_window_key"] == "everyday_lunch"]
    assert len(sels) == 1, "expected the second POST to update the same row, not create a duplicate"
    assert sels[0]["no_recipe_needed"] is False
    assert sels[0]["custom_text"] == "Changed my mind: soup"


def test_grocery_sync_scoped_to_selection_ids_only_includes_that_recipe(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    r1 = client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
    }, headers=hdr)
    sel_id = r1.json()["selection"]["id"]
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_lunch", "no_recipe_needed": True,
    }, headers=hdr)

    r = client.post("/api/recipes/selections/sync-grocery-list", json={
        "athlete_id": aid, "week_start": "2026-08-23", "selection_ids": [sel_id],
    }, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["items_added"] > 0


def test_grocery_sync_unscoped_omits_selection_ids_and_still_succeeds(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
    }, headers=hdr)

    r = client.post("/api/recipes/selections/sync-grocery-list", json={
        "athlete_id": aid, "week_start": "2026-08-23",
    }, headers=hdr)
    assert r.status_code == 200, r.text


def test_grocery_sync_empty_selection_ids_list_syncs_nothing(client):
    """selection_ids=[] (explicitly zero selected) must NOT behave like
    omitted (which means full-week sync) — truthiness would conflate the two."""
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": SELECTION_DATE,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
    }, headers=hdr)

    r = client.post("/api/recipes/selections/sync-grocery-list", json={
        "athlete_id": aid, "week_start": "2026-08-23", "selection_ids": [],
    }, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["items_added"] == 0


# ── Cross-day slot identity (Blocker 1 correction) ──────────────────────────
# Slot identity is (athlete_id, week_start, selection_date, fueling_window_key)
# — NOT recipe_id. The same window on two different days in one week are
# independent slots; the same window on the same day is exactly one slot
# regardless of how many times its resolution changes.

MONDAY = "2026-08-24"
TUESDAY = "2026-08-25"
WEEK_START = "2026-08-23"


def _week_selections(client, hdr, aid):
    r = client.get("/api/recipes/selections/week",
                    params={"athlete_id": aid, "week_start": WEEK_START}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["selections"]


def test_same_recipe_on_two_different_days_persists_as_two_rows(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    for d in (MONDAY, TUESDAY):
        r = client.post("/api/recipes/selections", json={
            "athlete_id": aid, "selection_date": d,
            "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
        }, headers=hdr)
        assert r.status_code == 201, r.text

    sels = _week_selections(client, hdr, aid)
    by_date = {s["selection_date"]: s for s in sels}
    assert len(sels) == 2
    assert by_date[MONDAY]["recipe_id"] == "R001"
    assert by_date[TUESDAY]["recipe_id"] == "R001"


def test_no_recipe_needed_on_two_different_days_persists_as_two_rows(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    for d in (MONDAY, TUESDAY):
        r = client.post("/api/recipes/selections", json={
            "athlete_id": aid, "selection_date": d,
            "fueling_window_key": "everyday_lunch", "no_recipe_needed": True,
        }, headers=hdr)
        assert r.status_code == 201, r.text

    sels = _week_selections(client, hdr, aid)
    by_date = {s["selection_date"]: s for s in sels}
    assert len(sels) == 2
    assert by_date[MONDAY]["no_recipe_needed"] is True
    assert by_date[TUESDAY]["no_recipe_needed"] is True


def test_custom_text_on_two_different_days_persists_as_two_rows(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    for d in (MONDAY, TUESDAY):
        r = client.post("/api/recipes/selections", json={
            "athlete_id": aid, "selection_date": d,
            "fueling_window_key": "everyday_dinner", "custom_text": "Pasta",
        }, headers=hdr)
        assert r.status_code == 201, r.text

    sels = _week_selections(client, hdr, aid)
    by_date = {s["selection_date"]: s for s in sels}
    assert len(sels) == 2
    assert by_date[MONDAY]["custom_text"] == "Pasta"
    assert by_date[TUESDAY]["custom_text"] == "Pasta"


def test_same_day_recipe_to_different_recipe_replaces_the_one_row(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": MONDAY,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
    }, headers=hdr)
    r2 = client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": MONDAY,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R002",
    }, headers=hdr)
    assert r2.status_code == 201, r2.text

    sels = [s for s in _week_selections(client, hdr, aid) if s["selection_date"] == MONDAY]
    assert len(sels) == 1, "expected one Monday breakfast row, got a duplicate"
    assert sels[0]["recipe_id"] == "R002"


def test_all_cross_resolution_replacements_stay_one_row_per_date_and_window(client):
    """recipe -> custom -> covered -> recipe: every step replaces the same
    (date, window) row in place. The backend must enforce this even without
    the client pre-deleting the previous selection."""
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    window = "everyday_snack"

    steps = [
        {"recipe_id": "R001"},
        {"custom_text": "Trail mix"},
        {"no_recipe_needed": True},
        {"recipe_id": "R002"},
    ]
    for step in steps:
        r = client.post("/api/recipes/selections", json={
            "athlete_id": aid, "selection_date": MONDAY,
            "fueling_window_key": window, **step,
        }, headers=hdr)
        assert r.status_code == 201, r.text

        sels = [s for s in _week_selections(client, hdr, aid)
                if s["selection_date"] == MONDAY and s["fueling_window_key"] == window]
        assert len(sels) == 1, f"expected exactly one row after {step}, got {len(sels)}"

    final = [s for s in _week_selections(client, hdr, aid)
             if s["selection_date"] == MONDAY and s["fueling_window_key"] == window][0]
    assert final["recipe_id"] == "R002"
    assert final["no_recipe_needed"] is False
    assert final["custom_text"] is None


def test_weekly_reload_returns_each_days_resolution_on_its_actual_date(client):
    aid = _make_athlete(client)
    hdr = auth_headers("athlete", athlete_id=aid)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": MONDAY,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R001",
    }, headers=hdr)
    client.post("/api/recipes/selections", json={
        "athlete_id": aid, "selection_date": TUESDAY,
        "fueling_window_key": "everyday_breakfast", "recipe_id": "R002",
    }, headers=hdr)

    sels = _week_selections(client, hdr, aid)
    by_date = {s["selection_date"]: s for s in sels}
    assert by_date[MONDAY]["recipe_id"] == "R001"
    assert by_date[TUESDAY]["recipe_id"] == "R002"
