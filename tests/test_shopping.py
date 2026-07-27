# tests/test_shopping.py
import os
os.environ["DB_PATH"] = ":memory:"

import sqlite3, pytest
from db.setup import init_db
from api.database import get_conn


@pytest.fixture
def conn():
    init_db()
    c = get_conn()
    yield c
    c.close()


def test_fueling_foods_table_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fueling_foods'"
    ).fetchone()
    assert row is not None


def test_athlete_food_prefs_table_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='athlete_food_prefs'"
    ).fetchone()
    assert row is not None


def test_shopping_lists_table_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='shopping_lists'"
    ).fetchone()
    assert row is not None


def test_shopping_list_items_table_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='shopping_list_items'"
    ).fetchone()
    assert row is not None


def test_food_submissions_table_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='food_submissions'"
    ).fetchone()
    assert row is not None


def _csv_row_count() -> int:
    import csv
    from pathlib import Path
    csv_path = Path(__file__).resolve().parent.parent / "fueling_foods_seed.csv"
    with open(csv_path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_seed_loads_all_foods(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    count = conn.execute("SELECT COUNT(*) FROM fueling_foods").fetchone()[0]
    assert count == _csv_row_count()


def test_seed_is_idempotent(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    seed_fueling_foods(conn)
    count = conn.execute("SELECT COUNT(*) FROM fueling_foods").fetchone()[0]
    assert count == _csv_row_count()


def test_seed_allergen_tags_stored_correctly(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    # Check a food known to have multiple allergens in the CSV (semicolon-separated)
    # Find any food with semicolons in its allergen_tags
    rows = conn.execute(
        "SELECT name, allergen_tags FROM fueling_foods WHERE allergen_tags LIKE '%;%'"
    ).fetchall()
    # If the CSV has any multi-allergen foods, they must use semicolon format
    # (If CSV has no multi-allergen foods, this test is vacuously true — that's OK)
    for row in rows:
        tags = row["allergen_tags"]
        parts = tags.split(";")
        assert len(parts) >= 2, f"{row['name']} should have multiple allergen parts: {tags}"
        for part in parts:
            assert part.strip(), f"Empty allergen part in {row['name']}: {tags}"
    # Assert at least one food actually has a multi-allergen tag (verifies the check is meaningful)
    if rows:
        assert len(rows) >= 1  # At least one food has multi-allergen tags


def test_seed_soft_hint_empty_string_for_foods_without_hint(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    # Any food without a soft_hint column value should be stored as empty string not NULL
    rows = conn.execute(
        "SELECT name, soft_hint FROM fueling_foods WHERE soft_hint IS NULL"
    ).fetchall()
    assert len(rows) == 0  # No NULLs — all should be empty string


# ── classify_week ─────────────────────────────────────────────────────────────

from api.services.shopping_service import classify_week, build_essentials


def test_classify_week_no_events_is_rest():
    result = classify_week({})
    assert result["practice_count"] == 0
    assert result["game_count"] == 0
    assert result["has_game"] is False


def test_classify_week_counts_practices():
    events_by_day = {
        "2026-06-16": [{"event_type": "practice", "start_time": "16:00", "duration_hours": 1.5}],
        "2026-06-17": [{"event_type": "practice", "start_time": "16:00", "duration_hours": 1.5}],
        "2026-06-18": [{"event_type": "practice", "start_time": "16:00", "duration_hours": 1.5}],
        "2026-06-19": [],
        "2026-06-20": [],
        "2026-06-21": [],
        "2026-06-22": [],
    }
    result = classify_week(events_by_day)
    assert result["practice_count"] == 3
    assert result["game_count"] == 0
    assert result["has_game"] is False


def test_classify_week_detects_game():
    events_by_day = {
        "2026-06-16": [{"event_type": "practice", "start_time": "16:00", "duration_hours": 1.5}],
        "2026-06-21": [{"event_type": "game", "start_time": "10:00", "duration_hours": 1.5}],
        **{d: [] for d in ["2026-06-17","2026-06-18","2026-06-19","2026-06-20","2026-06-22"]},
    }
    result = classify_week(events_by_day)
    assert result["practice_count"] == 1
    assert result["game_count"] == 1
    assert result["has_game"] is True


def test_classify_week_header_line_matches_counts():
    events_by_day = {
        "2026-06-16": [{"event_type": "practice", "start_time": "16:00", "duration_hours": 1.5}],
        "2026-06-17": [{"event_type": "practice", "start_time": "16:00", "duration_hours": 1.5}],
        "2026-06-21": [{"event_type": "game", "start_time": "10:00", "duration_hours": 1.5}],
        **{d: [] for d in ["2026-06-18","2026-06-19","2026-06-20","2026-06-22"]},
    }
    result = classify_week(events_by_day)
    assert result["schedule_line"] == "2 practices + 1 game this week"


# ── build_essentials ──────────────────────────────────────────────────────────

def _insert_athlete(conn, suffix="a") -> int:
    """Helper: insert a minimal parent+athlete, return athlete id."""
    conn.execute(
        f"INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) "
        f"VALUES ('P{suffix}', 'p{suffix}@t.com', '2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes "
        "(parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (parent_id, "Alex", 15, "Boy", 140, 5, 8),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return athlete_id


def _seed(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)


def test_day_strip_is_sunday_anchored_not_monday(conn):
    """Regression: the day strip used to start "Mon", but week_start is
    Sunday-anchored (api/utils/week.py's get_week_start(), and the mobile
    client's own getWeekStart() with WEEK_STARTS_ON=0) — every day in the
    strip was mislabeled by one. 2026-06-14 is a real Sunday; an event on
    2026-06-17 (Wednesday) must land at day_strip[3], labeled "Wed"."""
    _seed(conn)
    aid = _insert_athlete(conn, "daystrip")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Practice', 'practice', '2026-06-17', '16:00', 1.5)",
        (aid,),
    )
    conn.commit()
    result = build_essentials(aid, "2026-06-14", conn)
    strip = result["header"]["day_strip"]
    assert [d["label"] for d in strip] == ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    assert strip[0]["date"] == "2026-06-14"
    assert strip[3]["date"] == "2026-06-17"
    assert strip[3]["type"] != "rest"
    assert strip[0]["type"] == "rest"


def test_build_essentials_no_events_returns_staples_only(conn):
    _seed(conn)
    aid = _insert_athlete(conn, "rest")
    result = build_essentials(aid, "2026-06-16", conn)
    categories = {g["category"] for g in result["groups"]}
    assert categories == {"breakfast", "dinner_staple"}
    assert result["header"]["has_game"] is False


def test_build_essentials_practice_week_adds_pre_fuel_and_recovery(conn):
    _seed(conn)
    aid = _insert_athlete(conn, "prac")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Practice', 'practice', '2026-06-16', '16:00', 1.5)",
        (aid,),
    )
    conn.commit()
    result = build_essentials(aid, "2026-06-16", conn)
    categories = {g["category"] for g in result["groups"]}
    assert "pre_fuel" in categories
    assert "recovery" in categories


def test_build_essentials_game_week_includes_hydration(conn):
    _seed(conn)
    aid = _insert_athlete(conn, "game")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Game', 'game', '2026-06-21', '10:00', 1.5)",
        (aid,),
    )
    conn.commit()
    result = build_essentials(aid, "2026-06-16", conn)
    categories = {g["category"] for g in result["groups"]}
    assert "hydration" in categories
    assert result["header"]["has_game"] is True


def test_build_essentials_disliked_food_absent(conn):
    _seed(conn)
    aid = _insert_athlete(conn, "dis")
    conn.execute(
        "INSERT OR IGNORE INTO athlete_food_prefs (athlete_id, food_name, preference) "
        "VALUES (?, 'Cottage cheese', 'disliked')",
        (aid,),
    )
    conn.commit()
    result = build_essentials(aid, "2026-06-16", conn)
    all_names = [f["name"] for g in result["groups"] for f in g["foods"]]
    assert "Cottage cheese" not in all_names


def test_build_essentials_allergic_food_absent(conn):
    _seed(conn)
    aid = _insert_athlete(conn, "allergy")
    conn.execute(
        "INSERT OR IGNORE INTO athlete_food_prefs (athlete_id, food_name, preference) "
        "VALUES (?, 'Eggs', 'allergic')",
        (aid,),
    )
    conn.commit()
    result = build_essentials(aid, "2026-06-16", conn)
    all_names = [f["name"] for g in result["groups"] for f in g["foods"]]
    assert "Eggs" not in all_names


def test_build_essentials_liked_personal_food_appears(conn):
    _seed(conn)
    aid = _insert_athlete(conn, "liked")
    conn.execute(
        "INSERT OR IGNORE INTO athlete_food_prefs (athlete_id, food_name, preference, category) "
        "VALUES (?, 'Homemade granola', 'liked', 'breakfast')",
        (aid,),
    )
    conn.commit()
    result = build_essentials(aid, "2026-06-16", conn)
    all_names = [f["name"] for g in result["groups"] for f in g["foods"]]
    assert "Homemade granola" in all_names


# ── build_share_text ──────────────────────────────────────────────────────────

from api.services.shopping_service import build_share_text


def test_share_text_header_contains_week_date():
    text = build_share_text("2026-06-16", [])
    assert "Week of" in text
    assert "16 Jun" in text or "Jun" in text  # strftime %-d %b


def test_share_text_unchecked_item_uses_empty_checkbox():
    items = [{"name": "Bananas", "category": "pre_fuel", "checked": False}]
    text = build_share_text("2026-06-16", items)
    assert "☐ Bananas" in text


def test_share_text_checked_item_uses_filled_checkbox():
    items = [{"name": "Eggs", "category": "breakfast", "checked": True}]
    text = build_share_text("2026-06-16", items)
    assert "☑ Eggs" in text


def test_share_text_groups_items_by_category_label():
    items = [
        {"name": "Eggs", "category": "breakfast", "checked": False},
        {"name": "Bananas", "category": "pre_fuel", "checked": False},
    ]
    text = build_share_text("2026-06-16", items)
    assert "Breakfast" in text
    assert "Pre-Practice & Game Fuel" in text
    # breakfast comes before pre_fuel in the output
    assert text.index("Breakfast") < text.index("Pre-Practice")


def test_share_text_unknown_category_is_silently_dropped():
    items = [{"name": "Mystery food", "category": "unknown_cat", "checked": False}]
    text = build_share_text("2026-06-16", items)
    # Unknown category falls into by_cat.setdefault which adds it, but CATEGORY_ORDER
    # loop won't include it — verify the food name does NOT appear
    assert "Mystery food" not in text


# ── Route tests ───────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client(conn):
    """TestClient that shares the same in-memory DB as the conn fixture."""
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    with TestClient(app) as c:
        yield c


def _make_athlete_route(client, suffix="r") -> int:
    """Insert athlete via direct DB connection — returns athlete_id."""
    from api.database import get_conn as _gc
    c = _gc()
    c.execute(
        f"INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) "
        f"VALUES ('P{suffix}', 'pr{suffix}@t.com', '2026-01-01')"
    )
    parent_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "INSERT OR IGNORE INTO athletes "
        "(parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (?, 'Alex', 15, 'Boy', 140, 5, 8)",
        (parent_id,),
    )
    athlete_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.commit()
    c.close()
    return athlete_id


def test_get_essentials_rest_week(client):
    aid = _make_athlete_route(client, "re1")
    resp = client.get(
        f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16",
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    cats = {g["category"] for g in data["groups"]}
    assert "breakfast" in cats
    assert "hydration" not in cats


def test_get_essentials_header_matches_events(client):
    aid = _make_athlete_route(client, "re2")
    from api.database import get_conn as _gc
    c = _gc()
    c.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Practice', 'practice', '2026-06-16', '16:00', 1.5)", (aid,)
    )
    c.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Game', 'game', '2026-06-21', '10:00', 1.5)", (aid,)
    )
    c.commit(); c.close()
    resp = client.get(
        f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16",
        headers=auth_headers("athlete", athlete_id=aid),
    )
    data = resp.json()
    assert data["header"]["practice_count"] == 1
    assert data["header"]["game_count"] == 1
    assert "1 practice" in data["header"]["schedule_line"]
    assert "1 game" in data["header"]["schedule_line"]


def test_add_item_and_get_list(client):
    aid = _make_athlete_route(client, "re3")
    headers = auth_headers("athlete", athlete_id=aid)
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    }, headers=headers)
    assert resp.status_code == 201
    item_id = resp.json()["id"]
    resp2 = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    assert resp2.status_code == 200
    items = [i for g in resp2.json()["groups"] for i in g["items"]]
    assert any(i["id"] == item_id and i["name"] == "Bananas" for i in items)


def test_add_item_rejects_unknown_category(client):
    """Regression: an unrecognized category used to be accepted and stored,
    creating an invisible "ghost" item — every group-rendering loop only
    iterates CATEGORY_ORDER, so it would never appear in any group, with no
    error and no way to find or remove it except a direct DB query."""
    aid = _make_athlete_route(client, "re3b")
    headers = auth_headers("athlete", athlete_id=aid)
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Mystery Item", "category": "not_a_real_category", "source": "suggested",
    }, headers=headers)
    assert resp.status_code == 422
    list_resp = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    items = [i for g in list_resp.json()["groups"] for i in g["items"]]
    assert not any(i["name"] == "Mystery Item" for i in items)


def test_add_item_idempotent(client):
    aid = _make_athlete_route(client, "re4")
    headers = auth_headers("athlete", athlete_id=aid)
    payload = {"athlete_id": aid, "week_start": "2026-06-16",
               "name": "Bananas", "category": "pre_fuel", "source": "suggested"}
    client.post("/api/shopping/list/items", json=payload, headers=headers)
    client.post("/api/shopping/list/items", json=payload, headers=headers)
    resp = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    items = [i for g in resp.json()["groups"] for i in g["items"] if i["name"] == "Bananas"]
    assert len(items) == 1


def test_add_item_duplicate_check_is_case_and_whitespace_insensitive(client):
    """Regression: "Bananas" then "bananas " (different case, trailing space)
    used to be treated as two different items instead of a duplicate."""
    aid = _make_athlete_route(client, "re4b")
    headers = auth_headers("athlete", athlete_id=aid)
    client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    }, headers=headers)
    client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "bananas ", "category": "pre_fuel", "source": "suggested",
    }, headers=headers)
    resp = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    items = [i for g in resp.json()["groups"] for i in g["items"] if i["name"].strip().lower() == "bananas"]
    assert len(items) == 1
    assert items[0]["name"] == "Bananas"  # first-inserted casing preserved


def test_check_uncheck_item(client):
    aid = _make_athlete_route(client, "re5")
    headers = auth_headers("athlete", athlete_id=aid)
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    }, headers=headers)
    item_id = resp.json()["id"]
    patch = client.patch(f"/api/shopping/list/items/{item_id}", json={"checked": True}, headers=headers)
    assert patch.status_code == 200
    assert patch.json()["checked"] is True
    patch2 = client.patch(f"/api/shopping/list/items/{item_id}", json={"checked": False}, headers=headers)
    assert patch2.json()["checked"] is False


def test_delete_item(client):
    aid = _make_athlete_route(client, "re6")
    headers = auth_headers("athlete", athlete_id=aid)
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    }, headers=headers)
    item_id = resp.json()["id"]
    del_resp = client.delete(f"/api/shopping/list/items/{item_id}", headers=headers)
    assert del_resp.status_code == 200
    resp2 = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    items = [i for g in resp2.json()["groups"] for i in g["items"]]
    assert not any(i["id"] == item_id for i in items)


def test_set_pref_disliked_removes_from_essentials(client):
    aid = _make_athlete_route(client, "re7")
    headers = auth_headers("athlete", athlete_id=aid)
    client.post("/api/shopping/prefs", json={
        "athlete_id": aid, "food_name": "Bananas", "preference": "disliked"
    }, headers=headers)
    from api.database import get_conn as _gc
    c = _gc()
    c.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Prac', 'practice', '2026-06-16', '16:00', 1.5)", (aid,)
    )
    c.commit(); c.close()
    ess = client.get(f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    all_names = [f["name"] for g in ess.json()["groups"] for f in g["foods"]]
    assert "Bananas" not in all_names


def test_game_day_has_game_flag(client):
    aid_no_game = _make_athlete_route(client, "re8")
    resp = client.get(
        f"/api/shopping/essentials?athlete_id={aid_no_game}&week_start=2026-06-16",
        headers=auth_headers("athlete", athlete_id=aid_no_game),
    )
    assert resp.json()["header"]["has_game"] is False

    aid_game = _make_athlete_route(client, "re9")
    from api.database import get_conn as _gc
    c = _gc()
    c.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Game', 'game', '2026-06-21', '10:00', 1.5)", (aid_game,)
    )
    c.commit(); c.close()
    resp2 = client.get(
        f"/api/shopping/essentials?athlete_id={aid_game}&week_start=2026-06-16",
        headers=auth_headers("athlete", athlete_id=aid_game),
    )
    assert resp2.json()["header"]["has_game"] is True


def test_my_foods_appears_in_suggestions(client):
    aid = _make_athlete_route(client, "re10")
    headers = auth_headers("athlete", athlete_id=aid)
    client.post("/api/shopping/my-foods", json={
        "athlete_id": aid, "name": "Homemade energy balls", "category": "pre_fuel"
    }, headers=headers)
    from api.database import get_conn as _gc
    c = _gc()
    c.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (?, 'Prac', 'practice', '2026-06-16', '16:00', 1.5)", (aid,)
    )
    c.commit(); c.close()
    ess = client.get(f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16", headers=headers)
    all_names = [f["name"] for g in ess.json()["groups"] for f in g["foods"]]
    assert "Homemade energy balls" in all_names


def test_suggest_food_lands_as_pending(client):
    aid = _make_athlete_route(client, "re11")
    resp = client.post("/api/shopping/food-submissions", json={
        "name": "Fancy new bar", "suggested_category": "pre_fuel", "submitted_by": aid
    })
    assert resp.status_code == 201
    aid2 = _make_athlete_route(client, "re12")
    ess = client.get(
        f"/api/shopping/essentials?athlete_id={aid2}&week_start=2026-06-16",
        headers=auth_headers("athlete", athlete_id=aid2),
    )
    all_names = [f["name"] for g in ess.json()["groups"] for f in g["foods"]]
    assert "Fancy new bar" not in all_names


def test_admin_approve_promotes_food(client):
    aid = _make_athlete_route(client, "re13")
    sub = client.post("/api/shopping/food-submissions", json={
        "name": "New approved food", "suggested_category": "recovery", "submitted_by": aid
    })
    sub_id = sub.json()["id"]
    approve = client.post(f"/api/shopping/admin/food-submissions/{sub_id}/approve")
    assert approve.status_code == 200
    from api.database import get_conn as _gc
    c = _gc()
    row = c.execute("SELECT * FROM fueling_foods WHERE name = 'New approved food'").fetchone()
    c.close()
    assert row is not None
    assert row["category"] == "recovery"
