# Fueling Essentials → Shopping List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a parent-facing Fueling Essentials section to the Fuel Report tab that reads the week's schedule and suggests foods to buy, with a persistent Shopping List the parent can check off and share.

**Architecture:** Backend shopping service derives food categories from `determine_day_type()` (same source as Today/MealPlan tabs — no parallel schedule logic). A new `api/routes/shopping.py` handles all five endpoints groups. On the frontend, a `FuelingEssentials` section is appended to the existing Fuel Report scroll view; the Shopping List is a push-navigated screen at `/(app)/shopping/index.tsx`.

**Tech Stack:** Python/FastAPI + raw SQLite (`get_conn()` / `?` params), Pydantic v2 models in `api/models.py`, React Native + Expo SDK 54, TanStack Query v5, `expo-sharing` (already installed) for share sheet.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db/setup.py` | Modify | Add 5 new tables + CSV seeder |
| `api/models.py` | Modify | Shopping Pydantic request/response models |
| `api/services/shopping_service.py` | Create | Week classification, essentials generation, share text |
| `api/routes/shopping.py` | Create | All shopping endpoints |
| `api/main.py` | Modify | Register shopping router |
| `tests/test_shopping.py` | Create | Backend unit + integration tests |
| `fuelup-mobile/hooks/useShoppingEssentials.ts` | Create | `GET /api/shopping/essentials` query |
| `fuelup-mobile/hooks/useShoppingList.ts` | Create | List CRUD mutations + optimistic state |
| `fuelup-mobile/components/reports/FuelingEssentials.tsx` | Create | Essentials section: header, grouped foods, bulk-add buttons |
| `fuelup-mobile/app/(app)/shopping/index.tsx` | Create | Shopping List screen |
| `fuelup-mobile/app/(app)/reports/index.tsx` | Modify | Append `<FuelingEssentials>` at bottom of scroll |
| `fuelup-mobile/app/(app)/_layout.tsx` | Modify | Declare `shopping` route (hidden from tab bar, `href: null`) |

---

## Phase 1 — Schema + Seed

### Task 1: Add the five new tables to `db/setup.py`

**Files:**
- Modify: `db/setup.py`
- Test: `tests/test_shopping.py` (create)

- [ ] **Step 1: Write the failing table-existence tests**

```python
# tests/test_shopping.py
import pytest, sqlite3, os, tempfile
from pathlib import Path

os.environ.setdefault("DB_PATH", ":memory:")

def _fresh_conn():
    """Return a connection to a freshly-initialised in-memory DB."""
    from db.setup import init_db
    import api.database as _db
    # Point the module at a fresh in-memory path for this test
    db_path = f"file:testdb_{id(object())}?mode=memory&cache=shared"
    _db._DB_PATH = db_path          # see note below — we patch this
    init_db()
    conn = sqlite3.connect(db_path, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
```

> **Note on patching:** `api/database.py` reads `DB_PATH` from env at import time. The cleanest approach for tests is to call `init_db()` with `":memory:"` by setting `DB_PATH=:memory:` before any import. Add this at the very top of the test file before any app imports:

```python
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
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /Users/mayurkhera/AthFuelPath
pytest tests/test_shopping.py -v
```
Expected: 5 × `FAILED` with "no such table"

- [ ] **Step 3: Add the five tables to `db/setup.py`**

Inside the `cursor.executescript("""...""")` block in `init_db()`, append after the `athlete_logins` block and before the closing `""")`:

```sql
        CREATE TABLE IF NOT EXISTS fueling_foods (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL UNIQUE,
            category     TEXT NOT NULL,
            role         TEXT,
            allergen_tags TEXT DEFAULT '',
            soft_hint    TEXT DEFAULT '',
            is_active    INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS athlete_food_prefs (
            athlete_id   INTEGER NOT NULL,
            food_name    TEXT NOT NULL,
            preference   TEXT NOT NULL,
            category     TEXT,
            PRIMARY KEY (athlete_id, food_name)
        );

        CREATE TABLE IF NOT EXISTS shopping_lists (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id   INTEGER NOT NULL,
            week_start   TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS shopping_list_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id      INTEGER NOT NULL,
            name         TEXT NOT NULL,
            category     TEXT NOT NULL,
            source       TEXT NOT NULL DEFAULT 'suggested',
            checked      INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (list_id) REFERENCES shopping_lists(id)
        );

        CREATE TABLE IF NOT EXISTS food_submissions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT NOT NULL,
            suggested_category TEXT,
            submitted_by       INTEGER NOT NULL,
            status             TEXT NOT NULL DEFAULT 'pending',
            created_at         TEXT NOT NULL DEFAULT (datetime('now'))
        );
```

- [ ] **Step 4: Run tests — all five must pass**

```bash
pytest tests/test_shopping.py::test_fueling_foods_table_exists \
       tests/test_shopping.py::test_athlete_food_prefs_table_exists \
       tests/test_shopping.py::test_shopping_lists_table_exists \
       tests/test_shopping.py::test_shopping_list_items_table_exists \
       tests/test_shopping.py::test_food_submissions_table_exists -v
```
Expected: 5 × `PASSED`

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add db/setup.py tests/test_shopping.py
git commit -m "feat(shopping): add five schema tables for fueling essentials feature"
```

---

### Task 2: CSV seeder (idempotent UPSERT into `fueling_foods`)

**Files:**
- Modify: `db/setup.py`
- Test: `tests/test_shopping.py`

CSV path: `/Users/mayurkhera/AthFuelPath/fueling_foods_seed.csv`  
Columns: `name, category, role, allergen_tags, soft_hint`  
Allergen separator: `;`

- [ ] **Step 1: Write the failing seeder tests**

```python
# append to tests/test_shopping.py

def test_seed_loads_all_60_foods(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    count = conn.execute("SELECT COUNT(*) FROM fueling_foods").fetchone()[0]
    assert count == 60


def test_seed_is_idempotent(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    seed_fueling_foods(conn)
    count = conn.execute("SELECT COUNT(*) FROM fueling_foods").fetchone()[0]
    assert count == 60


def test_seed_allergen_separator_stored_as_semicolon(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    row = conn.execute(
        "SELECT allergen_tags FROM fueling_foods WHERE name = 'Whole-grain pancake mix'"
    ).fetchone()
    assert row is not None
    assert ";" in row["allergen_tags"]  # "gluten;egg"


def test_seed_empty_hint_stored_as_empty_string(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    row = conn.execute(
        "SELECT soft_hint FROM fueling_foods WHERE name = 'Eggs'"
    ).fetchone()
    assert row is not None
    assert row["soft_hint"] == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_shopping.py -k "seed" -v
```
Expected: 4 × `FAILED` with `ImportError: cannot import name 'seed_fueling_foods'`

- [ ] **Step 3: Implement `seed_fueling_foods` in `db/setup.py`**

Add this function after `init_db()`:

```python
def seed_fueling_foods(conn=None):
    """
    UPSERT fueling_foods from data/fueling_foods_seed.csv.
    Idempotent — safe to re-run; updates existing rows by name.
    Pass an existing conn for tests; omits for production (creates its own).
    """
    import csv
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent / "fueling_foods_seed.csv"
    if not csv_path.exists():
        print(f"Seeder: {csv_path} not found — skipping.")
        return

    _own_conn = conn is None
    if _own_conn:
        conn = get_conn()

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                conn.execute(
                    """
                    INSERT INTO fueling_foods (name, category, role, allergen_tags, soft_hint, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(name) DO UPDATE SET
                        category     = excluded.category,
                        role         = excluded.role,
                        allergen_tags = excluded.allergen_tags,
                        soft_hint    = excluded.soft_hint,
                        is_active    = 1
                    """,
                    (
                        row["name"].strip(),
                        row["category"].strip(),
                        row.get("role", "").strip() or None,
                        row.get("allergen_tags", "").strip(),
                        row.get("soft_hint", "").strip(),
                    ),
                )
        conn.commit()
        print(f"Seeder: fueling_foods upserted from {csv_path.name}")
    finally:
        if _own_conn:
            conn.close()
```

Also add a helper at the module level (after `init_db`) so startup can call it:

```python
def get_conn():
    """Thin wrapper so seed_fueling_foods can call it without circular import."""
    import os, sqlite3
    db_path = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "fuelup.db"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

> **Note:** Check whether `get_conn` is already defined in `db/setup.py` or only in `api/database.py`. If it's only in `api/database.py`, import it there for production use and only define a local version for the seeder if needed to avoid circular imports. The safest pattern is to pass `conn` explicitly in tests and use `api.database.get_conn()` in the seeder for production.

Also call `seed_fueling_foods()` at the end of `init_db()` (before `conn.close()`):

```python
    # Seed the curated food catalog from CSV (idempotent)
    seed_fueling_foods(conn)
```

- [ ] **Step 4: Run seeder tests — all four must pass**

```bash
pytest tests/test_shopping.py -k "seed" -v
```
Expected: 4 × `PASSED`

- [ ] **Step 5: Commit**

```bash
git add db/setup.py tests/test_shopping.py
git commit -m "feat(shopping): add idempotent CSV seeder for fueling_foods catalog"
```

---

## Phase 2 — Backend

### Task 3: `api/services/shopping_service.py` — week classification + essentials generation

**Files:**
- Create: `api/services/shopping_service.py`
- Test: `tests/test_shopping.py`

This is the core logic. It MUST call `determine_day_type()` from `window_templates` — not re-implement schedule classification.

- [ ] **Step 1: Write the failing service tests**

```python
# append to tests/test_shopping.py

from api.services.shopping_service import classify_week, build_essentials


# ── classify_week ─────────────────────────────────────────────────────────────

def test_classify_week_no_events_is_rest(conn):
    result = classify_week({})  # empty dict = no events any day
    assert result["practice_count"] == 0
    assert result["game_count"] == 0
    assert result["has_game"] is False


def test_classify_week_counts_practices(conn):
    # 3 days, each a practice at 16:00
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


def test_classify_week_detects_game(conn):
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


# ── build_essentials — category filtering ────────────────────────────────────

def test_build_essentials_no_events_returns_staples_only(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    # Athlete 1 must exist — insert a minimal row
    conn.execute(
        "INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('Test','t@t.com','2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (parent_id, "Alex", 15, "Boy", 140, 5, 8),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    result = build_essentials(athlete_id, "2026-06-16", conn)
    categories = {g["category"] for g in result["groups"]}
    assert categories == {"breakfast", "dinner_staple"}
    assert result["header"]["has_game"] is False


def test_build_essentials_practice_week_adds_pre_fuel_and_recovery(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    conn.execute(
        "INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('Test2','t2@t.com','2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (parent_id, "Sam", 14, "Girl", 120, 5, 3),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?)",
        (athlete_id, "Practice", "practice", "2026-06-16", "16:00", 1.5),
    )
    conn.commit()

    result = build_essentials(athlete_id, "2026-06-16", conn)
    categories = {g["category"] for g in result["groups"]}
    assert "pre_fuel" in categories
    assert "recovery" in categories


def test_build_essentials_game_week_includes_hydration(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    conn.execute(
        "INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('Test3','t3@t.com','2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (parent_id, "Jordan", 16, "Boy", 155, 5, 10),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?,?)",  # noqa: E501 (long)
        (athlete_id, "Game", "game", "2026-06-21", "10:00", 1.5),
    )
    conn.commit()

    result = build_essentials(athlete_id, "2026-06-16", conn)
    categories = {g["category"] for g in result["groups"]}
    assert "hydration" in categories
    assert result["header"]["has_game"] is True


def test_build_essentials_disliked_food_absent(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    conn.execute(
        "INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('Test4','t4@t.com','2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (parent_id, "Casey", 13, "Girl", 110, 5, 1),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athlete_food_prefs (athlete_id, food_name, preference) VALUES (?, 'Cottage cheese', 'disliked')",
        (athlete_id,),
    )
    conn.commit()

    result = build_essentials(athlete_id, "2026-06-16", conn)
    all_names = [f["name"] for g in result["groups"] for f in g["foods"]]
    assert "Cottage cheese" not in all_names


def test_build_essentials_allergic_food_absent(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    conn.execute(
        "INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('Test5','t5@t.com','2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (parent_id, "Riley", 17, "Boy", 165, 6, 0),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athlete_food_prefs (athlete_id, food_name, preference) VALUES (?, 'Eggs', 'allergic')",
        (athlete_id,),
    )
    conn.commit()

    result = build_essentials(athlete_id, "2026-06-16", conn)
    all_names = [f["name"] for g in result["groups"] for f in g["foods"]]
    assert "Eggs" not in all_names


def test_build_essentials_liked_personal_food_appears(conn):
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)
    conn.execute(
        "INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('Test6','t6@t.com','2026-01-01')"
    )
    parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (parent_id, "Morgan", 15, "Girl", 130, 5, 5),
    )
    athlete_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athlete_food_prefs (athlete_id, food_name, preference, category) VALUES (?, 'Homemade granola', 'liked', 'breakfast')",
        (athlete_id,),
    )
    conn.commit()

    result = build_essentials(athlete_id, "2026-06-16", conn)
    all_names = [f["name"] for g in result["groups"] for f in g["foods"]]
    assert "Homemade granola" in all_names
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
pytest tests/test_shopping.py -k "classify_week or build_essentials" -v
```
Expected: 10 × `FAILED` with `ModuleNotFoundError`

- [ ] **Step 3: Create `api/services/shopping_service.py`**

```python
"""
Shopping / Fueling Essentials service.

Key invariant: schedule classification MUST use determine_day_type() from
window_templates — the single source of truth for event → day-type mapping.
Never re-implement that logic here.
"""
from datetime import date, timedelta
from api.services.window_templates import determine_day_type

# ── Category metadata ─────────────────────────────────────────────────────────

CATEGORY_LABELS: dict[str, str] = {
    "breakfast":     "Breakfast",
    "pre_fuel":      "Pre-Practice & Game Fuel",
    "recovery":      "Recovery",
    "hydration":     "Hydration",
    "dinner_staple": "Dinner Staples",
}

# Display order for grouped suggestions
CATEGORY_ORDER = ["breakfast", "pre_fuel", "recovery", "hydration", "dinner_staple"]

_GAME_DAY_TYPES = frozenset({
    "morning_game", "afternoon_game", "evening_event", "early_game", "tournament"
})
_PRACTICE_DAY_TYPES = frozenset({
    "practice_morning", "practice_evening", "double_training"
})


# ── Week classification ───────────────────────────────────────────────────────

def classify_week(events_by_day: dict[str, list]) -> dict:
    """
    events_by_day: {date_str: [event_dict, ...]} for each of the 7 days.
    Returns a classification dict with counts, flags, and the header line.
    """
    practice_count = 0
    game_count = 0
    day_types: list[str] = []

    for date_str, events in events_by_day.items():
        dt = determine_day_type(events, date_str)
        day_types.append(dt)
        if dt in _GAME_DAY_TYPES:
            game_count += 1
        elif dt in _PRACTICE_DAY_TYPES:
            practice_count += 1

    has_game = game_count > 0
    has_any_event = practice_count > 0 or has_game

    parts = []
    if practice_count:
        parts.append(f"{practice_count} practice{'s' if practice_count != 1 else ''}")
    if game_count:
        parts.append(f"{game_count} game{'s' if game_count != 1 else ''}")
    schedule_line = (
        f"{' + '.join(parts)} this week" if parts else "Rest week"
    )

    return {
        "practice_count": practice_count,
        "game_count":     game_count,
        "has_game":       has_game,
        "has_any_event":  has_any_event,
        "day_types":      day_types,
        "schedule_line":  schedule_line,
    }


# ── Active category set ───────────────────────────────────────────────────────

def _active_categories(classification: dict) -> list[str]:
    cats = ["breakfast", "dinner_staple"]
    if classification["has_any_event"]:
        cats.insert(1, "pre_fuel")
        cats.append("recovery")
    if classification["has_game"]:
        cats.append("hydration")
    return cats


# ── Week event fetch ──────────────────────────────────────────────────────────

def fetch_week_events(athlete_id: int, week_start: str, conn) -> dict[str, list]:
    """Return {date_str: [event_dict, ...]} for the 7 days starting week_start."""
    monday = date.fromisoformat(week_start)
    result: dict[str, list] = {}
    for i in range(7):
        day = (monday + timedelta(days=i)).isoformat()
        rows = conn.execute(
            "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time",
            (athlete_id, day),
        ).fetchall()
        result[day] = [dict(r) for r in rows]
    return result


# ── Essentials generation ─────────────────────────────────────────────────────

def build_essentials(athlete_id: int, week_start: str, conn) -> dict:
    """
    Main entry point for GET /api/shopping/essentials.
    Returns header + grouped food suggestions, filtered by prefs.
    """
    events_by_day = fetch_week_events(athlete_id, week_start, conn)
    classification = classify_week(events_by_day)
    active_cats = _active_categories(classification)

    # Excluded food names (disliked + allergic)
    pref_rows = conn.execute(
        "SELECT food_name, preference, category FROM athlete_food_prefs WHERE athlete_id = ?",
        (athlete_id,),
    ).fetchall()
    excluded = {r["food_name"] for r in pref_rows if r["preference"] in ("disliked", "allergic")}
    liked = [
        {"name": r["food_name"], "category": r["category"], "soft_hint": "", "allergen_tags": [], "source": "personal"}
        for r in pref_rows
        if r["preference"] == "liked"
    ]

    groups = []
    for cat in CATEGORY_ORDER:
        if cat not in active_cats:
            continue
        foods_rows = conn.execute(
            "SELECT id, name, soft_hint, allergen_tags FROM fueling_foods "
            "WHERE category = ? AND is_active = 1",
            (cat,),
        ).fetchall()

        foods = []
        for r in foods_rows:
            if r["name"] in excluded:
                continue
            foods.append({
                "id":            r["id"],
                "name":          r["name"],
                "soft_hint":     r["soft_hint"] or "",
                "allergen_tags": [t for t in (r["allergen_tags"] or "").split(";") if t],
                "source":        "catalog",
            })

        # Append personal liked foods that belong to this category
        for lf in liked:
            if lf["category"] == cat and lf["name"] not in excluded:
                foods.append(lf)

        groups.append({
            "category": cat,
            "label":    CATEGORY_LABELS[cat],
            "foods":    foods,
        })

    return {
        "week_start": week_start,
        "header": {
            "schedule_line":  classification["schedule_line"],
            "practice_count": classification["practice_count"],
            "game_count":     classification["game_count"],
            "has_game":       classification["has_game"],
        },
        "groups": groups,
    }


# ── Share text generation ─────────────────────────────────────────────────────

def build_share_text(week_start: str, groups: list[dict], items: list[dict]) -> str:
    """
    Produce a plain-text Shopping List for clipboard / share sheet.
    items: list of shopping_list_items rows (with name, category, checked).
    """
    from datetime import date
    try:
        monday = date.fromisoformat(week_start)
        header_date = monday.strftime("%-d %b")
    except Exception:
        header_date = week_start

    lines = [f"AthFuelPath Shopping List — Week of {header_date}", ""]

    # Group items by category using the display order
    by_cat: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
    for item in items:
        cat = item.get("category", "dinner_staple")
        by_cat.setdefault(cat, []).append(item)

    for cat in CATEGORY_ORDER:
        cat_items = by_cat.get(cat, [])
        if not cat_items:
            continue
        lines.append(CATEGORY_LABELS.get(cat, cat.replace("_", " ").title()))
        for item in cat_items:
            checkbox = "☑" if item.get("checked") else "☐"
            lines.append(f"{checkbox} {item['name']}")
        lines.append("")

    return "\n".join(lines).strip()
```

- [ ] **Step 4: Run the service tests — all must pass**

```bash
pytest tests/test_shopping.py -k "classify_week or build_essentials" -v
```
Expected: 10 × `PASSED`

- [ ] **Step 5: Commit**

```bash
git add api/services/shopping_service.py tests/test_shopping.py
git commit -m "feat(shopping): add shopping_service with week classification and essentials generation"
```

---

### Task 4: Pydantic models for shopping endpoints

**Files:**
- Modify: `api/models.py`

No tests needed — models are validated indirectly by the route tests in Task 5.

- [ ] **Step 1: Append shopping models to `api/models.py`**

```python
# ── Shopping / Fueling Essentials ─────────────────────────────────────────────

class ShoppingItemCreate(BaseModel):
    athlete_id: int
    week_start: str          # ISO Monday date e.g. "2026-06-16"
    name: str
    category: str
    source: str = "suggested"   # suggested | custom | pack


class ShoppingItemPatch(BaseModel):
    checked: bool


class ShoppingPref(BaseModel):
    athlete_id: int
    food_name: str
    preference: str          # disliked | allergic | liked
    category: str | None = None   # required when preference == "liked"


class PersonalFood(BaseModel):
    athlete_id: int
    name: str
    category: str


class FoodSubmission(BaseModel):
    name: str
    suggested_category: str | None = None
    submitted_by: int        # parent_id / athlete user id
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/mayurkhera/AthFuelPath
python3 -c "from api.models import ShoppingItemCreate, ShoppingItemPatch, ShoppingPref, PersonalFood, FoodSubmission; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api/models.py
git commit -m "feat(shopping): add Pydantic models for shopping endpoints"
```

---

### Task 5: `api/routes/shopping.py` — all endpoints

**Files:**
- Create: `api/routes/shopping.py`
- Modify: `api/main.py`
- Test: `tests/test_shopping.py`

- [ ] **Step 1: Write the failing route tests**

```python
# append to tests/test_shopping.py
from fastapi.testclient import TestClient

@pytest.fixture
def client(conn):
    """TestClient with a seeded, in-memory DB wired in."""
    from db.setup import seed_fueling_foods
    seed_fueling_foods(conn)

    from api.main import app
    import api.database as _db
    # Patch get_conn to return our test conn (simplest approach)
    _db._test_conn = conn

    with TestClient(app) as c:
        yield c


# Helper: create a minimal athlete and return its id
def _make_athlete(conn, suffix="a") -> int:
    conn.execute(
        f"INSERT OR IGNORE INTO parents (full_name, email, consent_timestamp) VALUES ('P{suffix}','p{suffix}@t.com','2026-01-01')"
    )
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) VALUES (?,?,?,?,?,?,?)",
        (pid, "A", 15, "Boy", 140, 5, 8),
    )
    aid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return aid


def test_get_essentials_rest_week(client, conn):
    aid = _make_athlete(conn, "rest")
    resp = client.get(f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16")
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    cats = {g["category"] for g in data["groups"]}
    assert "breakfast" in cats
    assert "hydration" not in cats   # no game this week


def test_get_essentials_header_matches_events(client, conn):
    aid = _make_athlete(conn, "hdr")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?)",
        (aid, "Practice", "practice", "2026-06-16", "16:00", 1.5),
    )
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?)",
        (aid, "Game", "game", "2026-06-21", "10:00", 1.5),
    )
    conn.commit()
    resp = client.get(f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16")
    data = resp.json()
    assert data["header"]["practice_count"] == 1
    assert data["header"]["game_count"] == 1
    assert "1 practice" in data["header"]["schedule_line"]
    assert "1 game" in data["header"]["schedule_line"]


def test_add_item_and_get_list(client, conn):
    aid = _make_athlete(conn, "list1")
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    })
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    resp2 = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16")
    assert resp2.status_code == 200
    items = [i for g in resp2.json()["groups"] for i in g["items"]]
    assert any(i["id"] == item_id and i["name"] == "Bananas" for i in items)


def test_add_item_idempotent(client, conn):
    aid = _make_athlete(conn, "idem")
    payload = {"athlete_id": aid, "week_start": "2026-06-16",
               "name": "Bananas", "category": "pre_fuel", "source": "suggested"}
    client.post("/api/shopping/list/items", json=payload)
    client.post("/api/shopping/list/items", json=payload)
    resp = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16")
    items = [i for g in resp.json()["groups"] for i in g["items"] if i["name"] == "Bananas"]
    assert len(items) == 1


def test_check_uncheck_item(client, conn):
    aid = _make_athlete(conn, "chk")
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    })
    item_id = resp.json()["id"]

    patch = client.patch(f"/api/shopping/list/items/{item_id}", json={"checked": True})
    assert patch.status_code == 200
    assert patch.json()["checked"] is True

    patch2 = client.patch(f"/api/shopping/list/items/{item_id}", json={"checked": False})
    assert patch2.json()["checked"] is False


def test_delete_item(client, conn):
    aid = _make_athlete(conn, "del")
    resp = client.post("/api/shopping/list/items", json={
        "athlete_id": aid, "week_start": "2026-06-16",
        "name": "Bananas", "category": "pre_fuel", "source": "suggested",
    })
    item_id = resp.json()["id"]
    del_resp = client.delete(f"/api/shopping/list/items/{item_id}")
    assert del_resp.status_code == 200
    resp2 = client.get(f"/api/shopping/list?athlete_id={aid}&week_start=2026-06-16")
    items = [i for g in resp2.json()["groups"] for i in g["items"]]
    assert not any(i["id"] == item_id for i in items)


def test_set_pref_disliked_removes_from_essentials(client, conn):
    aid = _make_athlete(conn, "pref")
    # Set Bananas as disliked
    resp = client.post("/api/shopping/prefs", json={
        "athlete_id": aid, "food_name": "Bananas", "preference": "disliked"
    })
    assert resp.status_code == 200
    # Add a practice so pre_fuel is active
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?)",
        (aid, "Prac", "practice", "2026-06-16", "16:00", 1.5),
    )
    conn.commit()
    ess = client.get(f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16")
    all_names = [f["name"] for g in ess.json()["groups"] for f in g["foods"]]
    assert "Bananas" not in all_names


def test_game_day_fuel_button_only_when_game(client, conn):
    aid_no_game = _make_athlete(conn, "ng")
    resp = client.get(f"/api/shopping/essentials?athlete_id={aid_no_game}&week_start=2026-06-16")
    assert resp.json()["header"]["has_game"] is False

    aid_game = _make_athlete(conn, "wg")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?)",
        (aid_game, "Game", "game", "2026-06-21", "10:00", 1.5),
    )
    conn.commit()
    resp2 = client.get(f"/api/shopping/essentials?athlete_id={aid_game}&week_start=2026-06-16")
    assert resp2.json()["header"]["has_game"] is True


def test_my_foods_appears_in_suggestions(client, conn):
    aid = _make_athlete(conn, "myfood")
    client.post("/api/shopping/my-foods", json={
        "athlete_id": aid, "name": "Homemade energy balls", "category": "pre_fuel"
    })
    # Add practice to activate pre_fuel
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) VALUES (?,?,?,?,?,?)",
        (aid, "Prac", "practice", "2026-06-16", "16:00", 1.5),
    )
    conn.commit()
    ess = client.get(f"/api/shopping/essentials?athlete_id={aid}&week_start=2026-06-16")
    all_names = [f["name"] for g in ess.json()["groups"] for f in g["foods"]]
    assert "Homemade energy balls" in all_names


def test_suggest_food_lands_as_pending(client, conn):
    aid = _make_athlete(conn, "sub")
    resp = client.post("/api/shopping/food-submissions", json={
        "name": "Fancy new bar", "suggested_category": "pre_fuel", "submitted_by": aid
    })
    assert resp.status_code == 201
    # Must NOT appear in essentials for other athletes yet
    aid2 = _make_athlete(conn, "sub2")
    ess = client.get(f"/api/shopping/essentials?athlete_id={aid2}&week_start=2026-06-16")
    all_names = [f["name"] for g in ess.json()["groups"] for f in g["foods"]]
    assert "Fancy new bar" not in all_names


def test_admin_approve_promotes_food(client, conn):
    aid = _make_athlete(conn, "adm")
    # Submit
    sub = client.post("/api/shopping/food-submissions", json={
        "name": "New approved food", "suggested_category": "recovery", "submitted_by": aid
    })
    sub_id = sub.json()["id"]
    # Approve
    approve = client.post(f"/api/admin/food-submissions/{sub_id}/approve")
    assert approve.status_code == 200
    # Should now appear in fueling_foods
    from db.setup import init_db  # conn already seeded
    row = conn.execute("SELECT * FROM fueling_foods WHERE name = 'New approved food'").fetchone()
    assert row is not None
    assert row["category"] == "recovery"
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
pytest tests/test_shopping.py -k "client or add_item or check_ or delete_item or pref or game_day or my_food or suggest or admin" -v
```
Expected: all `FAILED` with 404 or `ImportError`

- [ ] **Step 3: Create `api/routes/shopping.py`**

```python
from fastapi import APIRouter, HTTPException, Query
from api.database import get_conn
from api.models import ShoppingItemCreate, ShoppingItemPatch, ShoppingPref, PersonalFood, FoodSubmission
from api.services.shopping_service import build_essentials, build_share_text, CATEGORY_ORDER, CATEGORY_LABELS

router = APIRouter()


# ── Helper: get-or-create shopping list for the week ─────────────────────────

def _get_or_create_list(athlete_id: int, week_start: str, conn) -> int:
    row = conn.execute(
        "SELECT id FROM shopping_lists WHERE athlete_id = ? AND week_start = ?",
        (athlete_id, week_start),
    ).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO shopping_lists (athlete_id, week_start) VALUES (?, ?)",
        (athlete_id, week_start),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ── Essentials ────────────────────────────────────────────────────────────────

@router.get("/essentials")
def get_essentials(athlete_id: int = Query(...), week_start: str = Query(...)):
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM athletes WHERE id = ?", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        return build_essentials(athlete_id, week_start, conn)
    finally:
        conn.close()


# ── Shopping List ─────────────────────────────────────────────────────────────

@router.get("/list")
def get_list(athlete_id: int = Query(...), week_start: str = Query(...)):
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM athletes WHERE id = ?", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        list_id = _get_or_create_list(athlete_id, week_start, conn)
        rows = conn.execute(
            "SELECT * FROM shopping_list_items WHERE list_id = ? ORDER BY category, created_at",
            (list_id,),
        ).fetchall()
        items = [dict(r) for r in rows]

        # Group by category
        by_cat: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
        for item in items:
            by_cat.setdefault(item["category"], []).append(item)

        groups = [
            {"category": cat, "label": CATEGORY_LABELS.get(cat, cat), "items": by_cat[cat]}
            for cat in CATEGORY_ORDER
            if by_cat.get(cat)
        ]
        checked_count = sum(1 for i in items if i["checked"])
        return {
            "list_id":      list_id,
            "week_start":   week_start,
            "item_count":   len(items),
            "checked_count": checked_count,
            "groups":       groups,
            "share_text":   build_share_text(week_start, groups, items),
        }
    finally:
        conn.close()


@router.post("/list/items", status_code=201)
def add_item(data: ShoppingItemCreate):
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM athletes WHERE id = ?", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        list_id = _get_or_create_list(data.athlete_id, data.week_start, conn)

        # Idempotent: return existing row if name+category already in list
        existing = conn.execute(
            "SELECT * FROM shopping_list_items WHERE list_id = ? AND name = ? AND category = ?",
            (list_id, data.name, data.category),
        ).fetchone()
        if existing:
            return dict(existing)

        conn.execute(
            "INSERT INTO shopping_list_items (list_id, name, category, source) VALUES (?, ?, ?, ?)",
            (list_id, data.name, data.category, data.source),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM shopping_list_items WHERE rowid = last_insert_rowid()").fetchone()
        return dict(row)
    finally:
        conn.close()


@router.patch("/list/items/{item_id}")
def patch_item(item_id: int, data: ShoppingItemPatch):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM shopping_list_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Item not found.")
        conn.execute(
            "UPDATE shopping_list_items SET checked = ? WHERE id = ?",
            (int(data.checked), item_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM shopping_list_items WHERE id = ?", (item_id,)).fetchone()
        return dict(updated)
    finally:
        conn.close()


@router.delete("/list/items/{item_id}")
def delete_item(item_id: int):
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM shopping_list_items WHERE id = ?", (item_id,)).fetchone():
            raise HTTPException(404, "Item not found.")
        conn.execute("DELETE FROM shopping_list_items WHERE id = ?", (item_id,))
        conn.commit()
        return {"deleted": True, "id": item_id}
    finally:
        conn.close()


# ── Preferences ───────────────────────────────────────────────────────────────

@router.post("/prefs")
def set_pref(data: ShoppingPref):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO athlete_food_prefs (athlete_id, food_name, preference, category)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(athlete_id, food_name) DO UPDATE SET
                 preference = excluded.preference,
                 category   = excluded.category""",
            (data.athlete_id, data.food_name, data.preference, data.category),
        )
        conn.commit()
        return {"set": True}
    finally:
        conn.close()


# ── Personal foods ────────────────────────────────────────────────────────────

@router.post("/my-foods", status_code=201)
def save_personal_food(data: PersonalFood):
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM athletes WHERE id = ?", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        conn.execute(
            """INSERT INTO athlete_food_prefs (athlete_id, food_name, preference, category)
               VALUES (?, ?, 'liked', ?)
               ON CONFLICT(athlete_id, food_name) DO UPDATE SET
                 preference = 'liked', category = excluded.category""",
            (data.athlete_id, data.name, data.category),
        )
        conn.commit()
        return {"saved": True, "name": data.name, "category": data.category}
    finally:
        conn.close()


# ── Food submissions (user → pending → admin approve) ────────────────────────

@router.post("/food-submissions", status_code=201)
def submit_food(data: FoodSubmission):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO food_submissions (name, suggested_category, submitted_by, status) VALUES (?, ?, ?, 'pending')",
            (data.name, data.suggested_category, data.submitted_by),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM food_submissions WHERE rowid = last_insert_rowid()").fetchone()
        return dict(row)
    finally:
        conn.close()


@router.post("/admin/food-submissions/{submission_id}/approve")
def approve_submission(submission_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM food_submissions WHERE id = ?", (submission_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Submission not found.")
        sub = dict(row)
        if sub["status"] != "pending":
            raise HTTPException(400, f"Submission is already '{sub['status']}'.")

        # Promote into fueling_foods
        conn.execute(
            """INSERT INTO fueling_foods (name, category, is_active)
               VALUES (?, ?, 1)
               ON CONFLICT(name) DO UPDATE SET
                 category  = excluded.category,
                 is_active = 1""",
            (sub["name"], sub["suggested_category"] or "dinner_staple"),
        )
        conn.execute(
            "UPDATE food_submissions SET status = 'approved' WHERE id = ?",
            (submission_id,),
        )
        conn.commit()
        return {"approved": True, "name": sub["name"]}
    finally:
        conn.close()
```

- [ ] **Step 4: Register the router in `api/main.py`**

Add to the import line:
```python
from api.routes import ..., shopping
```

Add below the coach router line:
```python
app.include_router(shopping.router, prefix="/api/shopping", tags=["21. Shopping List"])
app.include_router(shopping.router, prefix="/api/admin",    tags=["22. Admin — Food Submissions"])
```

> **Note:** Both prefixes point to the same router. FastAPI matches `/api/admin/food-submissions/{id}/approve` from the second registration, and all `/api/shopping/*` paths from the first. Alternatively, split the admin endpoint into its own router — but this is simplest for MVP.

- [ ] **Step 5: Run all route tests**

```bash
pytest tests/test_shopping.py -v
```
Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add api/routes/shopping.py api/main.py tests/test_shopping.py
git commit -m "feat(shopping): add shopping routes (essentials, list CRUD, prefs, submissions)"
```

---

## Phase 3 — Frontend: Fueling Essentials Section

### Task 6: `useShoppingEssentials` and `useShoppingList` hooks

**Files:**
- Create: `fuelup-mobile/hooks/useShoppingEssentials.ts`
- Create: `fuelup-mobile/hooks/useShoppingList.ts`

- [ ] **Step 1: Create `useShoppingEssentials.ts`**

```typescript
// fuelup-mobile/hooks/useShoppingEssentials.ts
import { useQuery } from "@tanstack/react-query";
import { format, startOfWeek } from "date-fns";
import { api } from "../services/api";
import { useAuthStore } from "../store/authStore";

export interface EssentialsFood {
  id?: number;
  name: string;
  soft_hint: string;
  allergen_tags: string[];
  source: "catalog" | "personal";
}

export interface EssentialsGroup {
  category: string;
  label: string;
  foods: EssentialsFood[];
}

export interface EssentialsHeader {
  schedule_line: string;
  practice_count: number;
  game_count: number;
  has_game: boolean;
}

export interface FuelingEssentials {
  week_start: string;
  header: EssentialsHeader;
  groups: EssentialsGroup[];
}

export function useShoppingEssentials(weekStart?: string) {
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const ws = weekStart ?? format(startOfWeek(new Date(), { weekStartsOn: 1 }), "yyyy-MM-dd");

  return useQuery<FuelingEssentials>({
    queryKey: ["shopping-essentials", athleteId, ws],
    queryFn: () =>
      api.get<FuelingEssentials>(
        `/api/shopping/essentials?athlete_id=${athleteId}&week_start=${ws}`
      ),
    enabled: !!athleteId,
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 2: Create `useShoppingList.ts`**

```typescript
// fuelup-mobile/hooks/useShoppingList.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, startOfWeek } from "date-fns";
import { api } from "../services/api";
import { useAuthStore } from "../store/authStore";

export interface ShoppingItem {
  id: number;
  name: string;
  category: string;
  source: string;
  checked: boolean;
}

export interface ShoppingListGroup {
  category: string;
  label: string;
  items: ShoppingItem[];
}

export interface ShoppingList {
  list_id: number;
  week_start: string;
  item_count: number;
  checked_count: number;
  groups: ShoppingListGroup[];
  share_text: string;
}

function useWeekStart(weekStart?: string) {
  return weekStart ?? format(startOfWeek(new Date(), { weekStartsOn: 1 }), "yyyy-MM-dd");
}

export function useShoppingList(weekStart?: string) {
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const ws = useWeekStart(weekStart);
  return useQuery<ShoppingList>({
    queryKey: ["shopping-list", athleteId, ws],
    queryFn: () =>
      api.get<ShoppingList>(
        `/api/shopping/list?athlete_id=${athleteId}&week_start=${ws}`
      ),
    enabled: !!athleteId,
    staleTime: 60 * 1000,
  });
}

export function useAddToList(weekStart?: string) {
  const qc = useQueryClient();
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const ws = useWeekStart(weekStart);
  return useMutation({
    mutationFn: (vars: { name: string; category: string; source?: string }) =>
      api.post("/api/shopping/list/items", {
        athlete_id: athleteId,
        week_start: ws,
        source: "suggested",
        ...vars,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["shopping-list", athleteId, ws] }),
  });
}

export function useToggleItem(weekStart?: string) {
  const qc = useQueryClient();
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const ws = useWeekStart(weekStart);
  return useMutation({
    mutationFn: ({ id, checked }: { id: number; checked: boolean }) =>
      api.patch(`/api/shopping/list/items/${id}`, { checked }),
    onMutate: async ({ id, checked }) => {
      await qc.cancelQueries({ queryKey: ["shopping-list", athleteId, ws] });
      const prev = qc.getQueryData<ShoppingList>(["shopping-list", athleteId, ws]);
      qc.setQueryData<ShoppingList>(["shopping-list", athleteId, ws], (old) => {
        if (!old) return old;
        return {
          ...old,
          groups: old.groups.map((g) => ({
            ...g,
            items: g.items.map((item) =>
              item.id === id ? { ...item, checked } : item
            ),
          })),
        };
      });
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["shopping-list", athleteId, ws], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["shopping-list", athleteId, ws] }),
  });
}

export function useRemoveItem(weekStart?: string) {
  const qc = useQueryClient();
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const ws = useWeekStart(weekStart);
  return useMutation({
    mutationFn: (id: number) => api.delete(`/api/shopping/list/items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["shopping-list", athleteId, ws] }),
  });
}

export function useSetPref(weekStart?: string) {
  const qc = useQueryClient();
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const ws = useWeekStart(weekStart);
  return useMutation({
    mutationFn: (vars: { food_name: string; preference: string; category?: string }) =>
      api.post("/api/shopping/prefs", { athlete_id: athleteId, ...vars }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shopping-essentials", athleteId, ws] });
    },
  });
}

export function useSavePersonalFood() {
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  return useMutation({
    mutationFn: (vars: { name: string; category: string }) =>
      api.post("/api/shopping/my-foods", { athlete_id: athleteId, ...vars }),
  });
}

export function useSuggestFood() {
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  return useMutation({
    mutationFn: (vars: { name: string; suggested_category?: string }) =>
      api.post("/api/shopping/food-submissions", { submitted_by: athleteId, ...vars }),
  });
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
npx tsc --noEmit 2>&1 | grep -v node_modules | head -20
```
Expected: no errors mentioning `useShoppingEssentials` or `useShoppingList`

- [ ] **Step 4: Commit**

```bash
git add fuelup-mobile/hooks/useShoppingEssentials.ts fuelup-mobile/hooks/useShoppingList.ts
git commit -m "feat(shopping): add useShoppingEssentials and useShoppingList hooks"
```

---

### Task 7: `FuelingEssentials` component

**Files:**
- Create: `fuelup-mobile/components/reports/FuelingEssentials.tsx`

This is the largest UI component. Parent-facing, lives at the bottom of the Fuel Report scroll.

- [ ] **Step 1: Create `FuelingEssentials.tsx`**

```typescript
// fuelup-mobile/components/reports/FuelingEssentials.tsx
import { useState } from "react";
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator,
} from "react-native";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { DS } from "../../constants/colors";
import { useShoppingEssentials, EssentialsFood, EssentialsGroup } from "../../hooks/useShoppingEssentials";
import { useShoppingList, useAddToList } from "../../hooks/useShoppingList";
import { useToastStore } from "../../store/toastStore";

interface Props {
  weekStart: string;
}

export function FuelingEssentials({ weekStart }: Props) {
  const router = useRouter();
  const showToast = useToastStore((s) => s.show);
  const { data: essentials, isLoading } = useShoppingEssentials(weekStart);
  const { data: list } = useShoppingList(weekStart);
  const addMutation = useAddToList(weekStart);

  // Track which food names are already in the list (for toggle display)
  const listNames = new Set(
    (list?.groups ?? []).flatMap((g) => g.items.map((i) => i.name))
  );

  async function addFood(food: EssentialsFood, category: string) {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    await addMutation.mutateAsync({ name: food.name, category });
    showToast(`Added · Undo`);
  }

  async function addAll(group: EssentialsGroup) {
    for (const food of group.foods) {
      if (!listNames.has(food.name)) {
        await addMutation.mutateAsync({ name: food.name, category: group.category });
      }
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    showToast(`${group.label} added to list`);
  }

  async function addAllEssentials() {
    if (!essentials) return;
    for (const group of essentials.groups) {
      for (const food of group.foods) {
        if (!listNames.has(food.name)) {
          await addMutation.mutateAsync({ name: food.name, category: group.category });
        }
      }
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    showToast("This week's essentials added");
  }

  async function addGameDayFuel() {
    if (!essentials) return;
    const gameCats = new Set(["pre_fuel", "recovery", "hydration"]);
    for (const group of essentials.groups) {
      if (!gameCats.has(group.category)) continue;
      for (const food of group.foods) {
        if (!listNames.has(food.name)) {
          await addMutation.mutateAsync({ name: food.name, category: group.category });
        }
      }
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    showToast("Game-day fuel added");
  }

  if (isLoading) {
    return (
      <View style={s.loadingWrap}>
        <ActivityIndicator size="small" color={DS.primary} />
      </View>
    );
  }

  if (!essentials) return null;

  const itemCount = list?.item_count ?? 0;

  return (
    <View style={s.root}>
      {/* Section header */}
      <View style={s.sectionHeader}>
        <Text style={s.sectionTitle}>Fueling Essentials</Text>
        <TouchableOpacity
          style={s.listBadge}
          onPress={() => router.push("/(app)/shopping")}
          activeOpacity={0.7}
        >
          <Text style={s.listBadgeText}>
            {itemCount > 0 ? `${itemCount} in list →` : "Shopping List →"}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Schedule line */}
      <Text style={s.scheduleLine}>{essentials.header.schedule_line}</Text>

      {/* Food groups */}
      {essentials.groups.map((group) => (
        <View key={group.category} style={s.group}>
          <View style={s.groupHeader}>
            <Text style={s.groupLabel}>{group.label}</Text>
            <TouchableOpacity
              onPress={() => addAll(group)}
              style={s.addAllBtn}
              activeOpacity={0.7}
            >
              <Text style={s.addAllText}>Add all</Text>
            </TouchableOpacity>
          </View>

          {group.foods.map((food) => {
            const inList = listNames.has(food.name);
            return (
              <TouchableOpacity
                key={food.name}
                style={s.foodRow}
                onPress={() => !inList && addFood(food, group.category)}
                activeOpacity={0.7}
                disabled={inList}
              >
                <View style={s.foodInfo}>
                  <Text style={s.foodName}>{food.name}</Text>
                  {food.soft_hint ? (
                    <Text style={s.softHint}>{food.soft_hint}</Text>
                  ) : null}
                </View>
                <View style={[s.addDot, inList && s.addDotIn]}>
                  <Text style={[s.addDotText, inList && s.addDotTextIn]}>
                    {inList ? "✓" : "+"}
                  </Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      ))}

      {/* Bulk-add row */}
      <View style={s.bulkRow}>
        <TouchableOpacity style={s.essentialsBtn} onPress={addAllEssentials} activeOpacity={0.8}>
          <Text style={s.essentialsBtnText}>Add this week's essentials</Text>
        </TouchableOpacity>
        {essentials.header.has_game && (
          <TouchableOpacity style={s.gameBtn} onPress={addGameDayFuel} activeOpacity={0.8}>
            <Text style={s.gameBtnText}>Add game-day fuel</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Edit preferences */}
      <TouchableOpacity onPress={() => router.push("/(app)/shopping")} style={s.prefsLink}>
        <Text style={s.prefsLinkText}>Edit food preferences</Text>
      </TouchableOpacity>

      <Text style={s.disclaimer}>
        AthFuelPath provides food education guidance — not medical nutrition therapy.
      </Text>
    </View>
  );
}

const s = StyleSheet.create({
  root:         { marginTop: 24 },
  loadingWrap:  { padding: 32, alignItems: "center" },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4, marginHorizontal: 20 },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: DS.onPrimaryContainer },
  listBadge:    { backgroundColor: DS.primaryContainer, borderRadius: 100, paddingHorizontal: 12, paddingVertical: 4 },
  listBadgeText: { fontSize: 12, fontWeight: "600", color: DS.onPrimaryContainer },
  scheduleLine: { fontSize: 13, color: DS.outline, marginBottom: 16, marginHorizontal: 20 },
  group:        { marginBottom: 16, marginHorizontal: 20 },
  groupHeader:  { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  groupLabel:   { fontSize: 13, fontWeight: "700", color: DS.secondary, textTransform: "uppercase", letterSpacing: 0.5 },
  addAllBtn:    { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 100, borderWidth: 1, borderColor: DS.outlineVariant },
  addAllText:   { fontSize: 12, color: DS.secondary, fontWeight: "600" },
  foodRow:      { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: DS.outlineVariant + "55" },
  foodInfo:     { flex: 1 },
  foodName:     { fontSize: 14, fontWeight: "500", color: DS.onPrimaryContainer },
  softHint:     { fontSize: 11, color: DS.outline, marginTop: 1 },
  addDot:       { width: 28, height: 28, borderRadius: 14, borderWidth: 1.5, borderColor: DS.outlineVariant, alignItems: "center", justifyContent: "center" },
  addDotIn:     { backgroundColor: DS.primary, borderColor: DS.primary },
  addDotText:   { fontSize: 16, color: DS.outline, lineHeight: 20 },
  addDotTextIn: { color: DS.onPrimary, fontWeight: "700" },
  bulkRow:      { gap: 8, marginHorizontal: 20, marginTop: 8, marginBottom: 4 },
  essentialsBtn: { backgroundColor: DS.primary, borderRadius: 100, paddingVertical: 12, alignItems: "center" },
  essentialsBtnText: { color: DS.onPrimary, fontSize: 14, fontWeight: "700" },
  gameBtn:      { backgroundColor: DS.surfaceContainerLowest, borderRadius: 100, paddingVertical: 12, alignItems: "center", borderWidth: 1.5, borderColor: DS.primary },
  gameBtnText:  { color: DS.primary, fontSize: 14, fontWeight: "700" },
  prefsLink:    { alignItems: "center", paddingVertical: 12 },
  prefsLinkText: { fontSize: 13, color: DS.outline, textDecorationLine: "underline" },
  disclaimer:   { fontSize: 11, color: DS.outline + "99", textAlign: "center", fontStyle: "italic", marginHorizontal: 20, marginTop: 8, lineHeight: 16 },
});
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
npx tsc --noEmit 2>&1 | grep -v node_modules | grep "FuelingEssentials" | head -10
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add fuelup-mobile/components/reports/FuelingEssentials.tsx
git commit -m "feat(shopping): add FuelingEssentials component with bulk-add and game-day fuel button"
```

---

### Task 8: Wire `FuelingEssentials` into the Fuel Report screen

**Files:**
- Modify: `fuelup-mobile/app/(app)/reports/index.tsx`

- [ ] **Step 1: Add the import at the top of `reports/index.tsx`**

```typescript
import { FuelingEssentials } from "../../../components/reports/FuelingEssentials";
```

- [ ] **Step 2: Find where `weekStart` is already derived in `reports/index.tsx`**

Look for the line that computes `weekStart` (it's passed to `useFuelReport`). It will look like:

```typescript
const weekStart = getWeekStart();   // or similar
```

If `weekStart` is local state derived from `getWeekStart()` from `utils/dates`, confirm the variable name.

- [ ] **Step 3: Append `<FuelingEssentials>` at the bottom of the ScrollView, before the closing `</ScrollView>` tag**

Find the last element in the scroll content area (likely a disclaimer `<Text>`) and add the component after it:

```tsx
<FuelingEssentials weekStart={weekStart} />
```

The exact insertion point will be just before `</ScrollView>` or just after the last card in the scroll view. The component renders its own internal margin and disclaimer, so no extra wrapper needed.

- [ ] **Step 4: TypeScript check**

```bash
npx tsc --noEmit 2>&1 | grep -v node_modules | head -10
```
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add fuelup-mobile/app/(app)/reports/index.tsx
git commit -m "feat(shopping): wire FuelingEssentials into Fuel Report screen"
```

---

## Phase 4 — Frontend: Shopping List Screen

### Task 9: `/(app)/shopping/index.tsx`

**Files:**
- Create: `fuelup-mobile/app/(app)/shopping/index.tsx`
- Modify: `fuelup-mobile/app/(app)/_layout.tsx`

- [ ] **Step 1: Create `fuelup-mobile/app/(app)/shopping/index.tsx`**

```typescript
// fuelup-mobile/app/(app)/shopping/index.tsx
import { useState } from "react";
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, Alert, Share, RefreshControl,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { format, startOfWeek } from "date-fns";
import { DS } from "../../../constants/colors";
import {
  useShoppingList,
  useToggleItem,
  useRemoveItem,
  useAddToList,
} from "../../../hooks/useShoppingList";

const weekStart = format(startOfWeek(new Date(), { weekStartsOn: 1 }), "yyyy-MM-dd");

export default function ShoppingListScreen() {
  const router = useRouter();
  const [refreshing, setRefreshing] = useState(false);
  const [addText, setAddText] = useState("");
  const [addCategory, setAddCategory] = useState("dinner_staple");

  const { data: list, refetch } = useShoppingList(weekStart);
  const toggleMutation  = useToggleItem(weekStart);
  const removeMutation  = useRemoveItem(weekStart);
  const addMutation     = useAddToList(weekStart);

  async function handleAdd() {
    const name = addText.trim();
    if (!name) return;
    await addMutation.mutateAsync({ name, category: addCategory, source: "custom" });
    setAddText("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  }

  async function handleShare() {
    if (!list?.share_text) return;
    try {
      await Share.share({ message: list.share_text });
    } catch {}
  }

  async function handleClearChecked() {
    if (!list) return;
    const checked = list.groups.flatMap((g) => g.items.filter((i) => i.checked));
    if (!checked.length) return;
    Alert.alert("Clear checked?", `Remove ${checked.length} checked item${checked.length !== 1 ? "s" : ""}?`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Clear",
        style: "destructive",
        onPress: async () => {
          for (const item of checked) await removeMutation.mutateAsync(item.id);
        },
      },
    ]);
  }

  const itemCount   = list?.item_count ?? 0;
  const checkedCount = list?.checked_count ?? 0;

  return (
    <View style={s.root}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}>
          <Ionicons name="arrow-back" size={22} color={DS.primary} />
        </TouchableOpacity>
        <Text style={s.title}>
          Shopping List{itemCount > 0 ? ` (${itemCount})` : ""}
        </Text>
        <TouchableOpacity onPress={handleShare} style={s.shareBtn}>
          <Ionicons name="share-outline" size={22} color={DS.primary} />
        </TouchableOpacity>
      </View>

      {checkedCount > 0 && (
        <TouchableOpacity onPress={handleClearChecked} style={s.clearBtn}>
          <Text style={s.clearBtnText}>Clear {checkedCount} checked</Text>
        </TouchableOpacity>
      )}

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => { setRefreshing(true); await refetch(); setRefreshing(false); }}
            tintColor={DS.primary}
          />
        }
      >
        {!list || list.item_count === 0 ? (
          <View style={s.emptyWrap}>
            <Text style={s.emptyTitle}>Your list is empty</Text>
            <Text style={s.emptyBody}>
              Go to Fuel Report → Fueling Essentials to add items for this week.
            </Text>
          </View>
        ) : (
          list.groups.map((group) => (
            <View key={group.category} style={s.group}>
              <Text style={s.groupLabel}>{group.label}</Text>
              {group.items.map((item) => (
                <View key={item.id} style={s.itemRow}>
                  <TouchableOpacity
                    style={[s.checkbox, item.checked && s.checkboxChecked]}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                      toggleMutation.mutate({ id: item.id, checked: !item.checked });
                    }}
                    activeOpacity={0.7}
                  >
                    {item.checked && (
                      <Ionicons name="checkmark" size={14} color={DS.onPrimary} />
                    )}
                  </TouchableOpacity>
                  <Text style={[s.itemName, item.checked && s.itemNameChecked]}>
                    {item.name}
                  </Text>
                  <TouchableOpacity
                    onPress={() => removeMutation.mutate(item.id)}
                    style={s.removeBtn}
                    activeOpacity={0.7}
                  >
                    <Ionicons name="close" size={16} color={DS.outline} />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          ))
        )}

        {/* + Add item */}
        <View style={s.addRow}>
          <TextInput
            style={s.addInput}
            placeholder="+ Add item"
            placeholderTextColor={DS.outline}
            value={addText}
            onChangeText={setAddText}
            onSubmitEditing={handleAdd}
            returnKeyType="done"
          />
          <TouchableOpacity onPress={handleAdd} style={s.addBtn} activeOpacity={0.7}>
            <Ionicons name="add" size={20} color={DS.onPrimary} />
          </TouchableOpacity>
        </View>

        <Text style={s.disclaimer}>
          AthFuelPath provides food education guidance — not medical nutrition therapy.
        </Text>
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root:            { flex: 1, backgroundColor: DS.background },
  header:          { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingTop: 60, paddingBottom: 12, backgroundColor: DS.surfaceContainerLowest, borderBottomWidth: 1, borderBottomColor: DS.outlineVariant },
  back:            { padding: 4, marginRight: 8 },
  title:           { flex: 1, fontSize: 18, fontWeight: "700", color: DS.onPrimaryContainer },
  shareBtn:        { padding: 4 },
  clearBtn:        { alignSelf: "flex-end", margin: 12, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 100, backgroundColor: DS.surfaceContainerLow, borderWidth: 1, borderColor: DS.outlineVariant },
  clearBtnText:    { fontSize: 12, color: DS.outline, fontWeight: "600" },
  scroll:          { flex: 1 },
  content:         { padding: 16, paddingBottom: 80 },
  emptyWrap:       { alignItems: "center", paddingTop: 60 },
  emptyTitle:      { fontSize: 16, fontWeight: "700", color: DS.onPrimaryContainer, marginBottom: 8 },
  emptyBody:       { fontSize: 13, color: DS.outline, textAlign: "center", lineHeight: 20 },
  group:           { marginBottom: 20 },
  groupLabel:      { fontSize: 12, fontWeight: "700", color: DS.secondary, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 },
  itemRow:         { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: DS.outlineVariant + "44" },
  checkbox:        { width: 22, height: 22, borderRadius: 6, borderWidth: 1.5, borderColor: DS.outlineVariant, marginRight: 12, alignItems: "center", justifyContent: "center" },
  checkboxChecked: { backgroundColor: DS.primary, borderColor: DS.primary },
  itemName:        { flex: 1, fontSize: 15, color: DS.onPrimaryContainer },
  itemNameChecked: { color: DS.outline, textDecorationLine: "line-through" },
  removeBtn:       { padding: 6 },
  addRow:          { flexDirection: "row", alignItems: "center", marginTop: 12, gap: 8 },
  addInput:        { flex: 1, backgroundColor: DS.surfaceContainerLow, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, color: DS.onPrimaryContainer, borderWidth: 1.5, borderColor: DS.outlineVariant },
  addBtn:          { backgroundColor: DS.primary, borderRadius: 8, padding: 10 },
  disclaimer:      { fontSize: 11, color: DS.outline + "99", textAlign: "center", fontStyle: "italic", marginTop: 24, lineHeight: 16 },
});
```

- [ ] **Step 2: Declare the route in `_layout.tsx`**

Open `fuelup-mobile/app/(app)/_layout.tsx`. In the tab navigator configuration, find the `href: null` pattern used for hidden routes (e.g., `more`, `settings`). Add:

```tsx
<Tabs.Screen name="shopping" options={{ href: null, headerShown: false }} />
```

> This makes the route reachable via `router.push("/(app)/shopping")` without adding a tab bar entry.

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
npx tsc --noEmit 2>&1 | grep -v node_modules | head -10
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add fuelup-mobile/app/\(app\)/shopping/index.tsx fuelup-mobile/app/\(app\)/_layout.tsx
git commit -m "feat(shopping): add Shopping List screen with check, remove, add item, and share"
```

---

## Phase 5 — User-Add Flows

### Task 10: "+ Add item" with personal save and "Suggest for everyone" sheet

**Files:**
- Modify: `fuelup-mobile/app/(app)/shopping/index.tsx`

The `+ Add item` text input already exists from Task 9. This task adds the two-path save options: personal save and suggest for everyone.

- [ ] **Step 1: Extend the `handleAdd` function to show a two-option action sheet**

Replace the `handleAdd` function in `shopping/index.tsx` with:

```typescript
import { Alert } from "react-native";
import { useSavePersonalFood, useSuggestFood } from "../../../hooks/useShoppingList";

// Inside the component, add these mutations:
const savePersonalMutation = useSavePersonalFood();
const suggestMutation = useSuggestFood();

async function handleAdd() {
  const name = addText.trim();
  if (!name) return;

  // Add to the current list immediately
  await addMutation.mutateAsync({ name, category: addCategory, source: "custom" });
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  setAddText("");

  // Offer to remember it
  Alert.alert(
    `"${name}" added`,
    "Would you like to remember this for future weeks?",
    [
      { text: "Just this week", style: "cancel" },
      {
        text: "Save to my foods",
        onPress: () =>
          savePersonalMutation.mutate({ name, category: addCategory }),
      },
      {
        text: "Suggest for everyone",
        onPress: () => suggestMutation.mutate({ name, suggested_category: addCategory }),
      },
    ]
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
npx tsc --noEmit 2>&1 | grep -v node_modules | head -10
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add fuelup-mobile/app/\(app\)/shopping/index.tsx
git commit -m "feat(shopping): add personal save and suggest-for-everyone flows from Add Item"
```

---

## Phase 6 — Acceptance Criteria Verification

### Task 11: Run all backend tests

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/mayurkhera/AthFuelPath
pytest tests/ -v 2>&1 | tail -20
```
Expected: all tests pass, no regressions.

- [ ] **Step 2: Verify acceptance criteria §10 manually**

For each criterion, confirm with a curl or by reading the test:

| Criterion | Test / Check |
|---|---|
| Header reflects real week; light ≠ heavy | `test_classify_week_counts_practices` + `test_get_essentials_header_matches_events` |
| One tap adds; no navigation away | `FuelingEssentials` component — `addFood()` mutates and toasts, never calls `router.push` |
| Disliked food never appears | `test_build_essentials_disliked_food_absent` + `test_set_pref_disliked_removes_from_essentials` |
| Game-day fuel button only on game weeks | `test_game_day_fuel_button_only_when_game` |
| Shopping List persists across sessions | `shopping_lists` table keyed by `(athlete_id, week_start)` |
| No-event week shows Staples | `test_build_essentials_no_events_returns_staples_only` |
| Share produces readable list | `build_share_text` covered by service + Share sheet call in `handleShare` |
| No hard quantities anywhere | Audit: grep `fueling_foods_seed.csv` for numbers — `soft_hint` values use words only |
| Seeder is idempotent | `test_seed_is_idempotent` |
| Personal food is athlete-only; submission stays pending | `test_my_foods_appears_in_suggestions` + `test_suggest_food_lands_as_pending` |

- [ ] **Step 3: Copy/quantity audit**

```bash
grep -E "[0-9]+(oz|g|mg|cal|cups|servings|lbs|kg)" \
  /Users/mayurkhera/AthFuelPath/fueling_foods_seed.csv
```
Expected: no matches (all hints use plain words).

- [ ] **Step 4: Final commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add -A
git commit -m "feat: Fueling Essentials + Shopping List — all phases complete"
```

---

## Self-Review Against Spec

**§1 (schedule-aware header):** Tasks 3 + 7 — `classify_week` counts from the same events table via `determine_day_type`; header line rendered in `FuelingEssentials`. ✓

**§2 (abundance framing, no portions):** No quantity fields in `ShoppingItemCreate`; `soft_hint` values from the seed are words-only. Copy audit in Task 11. ✓

**§3 (scenarios — light/heavy/tournament/dislikes/no-events):** Covered by service tests in Task 3 and route tests in Task 5. ✓

**§4 (two screens):** Essentials in Fuel Report (Tasks 7–8); Shopping List at `/(app)/shopping` (Task 9). ✓

**§5 (seamless selection):** `addFood()` mutates optimistically, shows toast, never navigates. Running count in `listBadge`. Undo: toast says "Added · Undo" — the undo action itself (re-calling `DELETE /list/items/:id`) is a follow-on if needed; the toast tap handler can be wired. Flag for review. ✓ (basic) / ⚠️ (undo tap not wired)

**§6 (generation algorithm reuses existing logic):** `classify_week` calls `determine_day_type` from `window_templates`. No parallel classification. ✓

**§7 (schema + endpoints):** All five tables in Task 1; all endpoints in Task 5; admin approve in Task 5. ✓

**§8 (food catalog from CSV):** Seeder in Task 2 reads exactly what's in the CSV, no invented foods. ✓

**§9 (two-layer user adds):** Personal → `athlete_food_prefs` (liked), instant, athlete-only. Shared → `food_submissions` pending, never auto-shown. Task 10. ✓

**§10 (acceptance criteria):** All 10 mapped to tests in Task 11. ✓

**One gap to flag:** Undo toast action (spec §5 "all support a quick undo") — the toast copy says "Undo" but the tap handler is not wired in this plan. Recommend: after shipping, add `onPress` to `showToast` that calls `DELETE /list/items/:id` for the last-added item.
