# Youth Fuel Streak — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a forgiving daily "Fuel Streak" for the youth athlete, surfaced on the mobile Today screen, that advances when they confirm a fuel window and never shames a missed day.

**Architecture:** One new backend service (`streak_service.py`) is the single source of truth. It computes the streak on-read from the existing `confirmations` table (∪ `window_logs`), with a tiny new `streak_state` table holding only non-derivable state (freeze tokens, last-celebrated milestone). The streak is added as one new field on the existing `GET /today` response and persisted milestone state is updated on the `POST /confirmations` write path. The mobile Today screen renders a flame + 7-dot week strip below the (number-free) hero and fires a one-time celebration on milestone crossings.

**Tech Stack:** Python 3.12 / FastAPI / raw SQLite (`sqlite3`), pytest (in-memory DB fixtures); React Native / Expo SDK 54 / TypeScript, TanStack Query, expo-haptics.

**Approved design decisions (from `docs/STREAK_DESIGN.md`):**
- Mechanic: forgiving consecutive-day streak.
- Qualifying day: ≥1 confirmed fuel window (`report_config.streak_min_confirms_per_day`, default 1).
- Source of truth: `confirmations` ∪ `window_logs` (confirmations primary).
- Today-grace: today not-yet-logged never breaks the streak (counts back from yesterday).
- Freeze: one auto-applied freeze per rolling 7 days bridges a single missed day.
- Milestones: **2 / 5 / 10 / 21** days, celebrated once each.
- Display: `🔥 N` count + 7-dot week strip, below the number-free hero.

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `api/services/streak_service.py` | **Create** | All streak logic: qualifying days, current/best streak, week strip, milestones, freeze, milestone-celebration bookkeeping. |
| `tests/test_streak_service.py` | **Create** | Unit tests for every streak rule, using in-memory SQLite (mirrors `tests/test_fuel_report_service.py`). |
| `api/services/db_migrations.py` | **Modify** | Add additive `streak_state` table creation, wired into `run_all()`. |
| `api/routes/fuel_report.py` | **Modify** | `POST /confirmations` registers the confirmation with the streak service and returns the streak block (incl. milestone). |
| `api/services/today_service.py` | **Modify** | `build_today_view()` adds a `streak` block to its response. |
| `hooks/useTodayView.ts` *(mobile repo)* | **Modify** | Add `TodayStreak` type + `streak` field on `TodayView`. |
| `components/today/StreakStrip.tsx` *(mobile repo)* | **Create** | Renders flame count + 7-dot week strip + best + no-shame empty state. |
| `app/(app)/today/index.tsx` *(mobile repo)* | **Modify** | Render `<StreakStrip>` below the hero; fire celebration toast/haptic on milestone. |

> **Repo note:** The backend lives in `/Users/mayurkhera/AthFuelPath`. The mobile app lives in `/Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile`. Mobile paths in this plan are relative to the mobile repo root. Run mobile commands from that directory.

> **Backend test command:** from `/Users/mayurkhera/AthFuelPath`, run `source venv/bin/activate` once, then the `pytest` commands below.

---

## Task 1: `streak_state` migration

**Files:**
- Modify: `api/services/db_migrations.py`
- Test: `tests/test_streak_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_streak_service.py` with:

```python
"""Unit tests for the Fuel Streak service (api/services/streak_service.py)."""

import sqlite3
from datetime import date, timedelta

import pytest

from api.services.db_migrations import _create_streak_state


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_streak_state_table_is_created():
    conn = _mk_conn()
    _create_streak_state(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(streak_state)").fetchall()}
    assert cols == {
        "athlete_id",
        "freeze_tokens",
        "last_celebrated_milestone",
        "updated_at",
    }
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_streak_service.py::test_streak_state_table_is_created -v`
Expected: FAIL with `ImportError: cannot import name '_create_streak_state'`.

- [ ] **Step 3: Add the migration**

In `api/services/db_migrations.py`, add a call inside `run_all()` (after `_create_notification_log(conn)`):

```python
        _create_notification_log(conn)
        _create_streak_state(conn)
        _add_timezone_to_tokens(conn)
```

Then add this function at the end of the file:

```python
def _create_streak_state(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS streak_state (
            athlete_id                INTEGER PRIMARY KEY,
            freeze_tokens             INTEGER NOT NULL DEFAULT 1,
            last_celebrated_milestone INTEGER NOT NULL DEFAULT 0,
            updated_at                TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_streak_service.py::test_streak_state_table_is_created -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/db_migrations.py tests/test_streak_service.py
git commit -m "feat(streak): add streak_state table migration"
```

---

## Task 2: Qualifying days, best streak, week strip

**Files:**
- Create: `api/services/streak_service.py`
- Test: `tests/test_streak_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_streak_service.py`:

```python
from api.services import streak_service as ss


def _streak_db():
    """In-memory DB with the tables the streak service reads."""
    conn = _mk_conn()
    conn.executescript("""
        CREATE TABLE confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            window_key TEXT NOT NULL,
            window_type TEXT NOT NULL
        );
        CREATE TABLE window_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            window_id TEXT NOT NULL,
            log_date TEXT NOT NULL
        );
        CREATE TABLE report_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL,
            description TEXT,
            updated_at TEXT
        );
        INSERT INTO report_config VALUES ('streak_min_confirms_per_day', 1.0, '', datetime('now'));
    """)
    return conn


def _confirm(conn, athlete_id, log_date, window_key="pre_event_meal", window_type="pre_fuel"):
    conn.execute(
        "INSERT INTO confirmations (athlete_id, log_date, window_key, window_type) VALUES (?, ?, ?, ?)",
        (athlete_id, log_date, window_key, window_type),
    )
    conn.commit()


def test_qualifying_dates_from_confirmations():
    conn = _streak_db()
    _confirm(conn, 1, "2026-06-10")
    _confirm(conn, 1, "2026-06-11")
    assert ss._qualifying_dates(1, conn) == {"2026-06-10", "2026-06-11"}
    conn.close()


def test_qualifying_dates_union_with_window_logs():
    conn = _streak_db()
    _confirm(conn, 1, "2026-06-10")
    conn.execute(
        "INSERT INTO window_logs (athlete_id, window_id, log_date) VALUES (1, 'breakfast', '2026-06-12')"
    )
    conn.commit()
    assert ss._qualifying_dates(1, conn) == {"2026-06-10", "2026-06-12"}
    conn.close()


def test_best_streak_finds_longest_run():
    # 06-01,02,03 (run of 3), gap, 06-05,06 (run of 2) -> best 3
    qual = {"2026-06-01", "2026-06-02", "2026-06-03", "2026-06-05", "2026-06-06"}
    assert ss._best_streak(qual) == 3


def test_week_strip_is_monday_to_sunday():
    # Wednesday 2026-06-17; Monday of that week is 2026-06-15
    qual = {"2026-06-15", "2026-06-17"}
    strip = ss._week_strip(qual, date(2026, 6, 17))
    assert strip == [True, False, True, False, False, False, False]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_streak_service.py -k "qualifying or best_streak or week_strip" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.services.streak_service'`.

- [ ] **Step 3: Create the service with the helpers**

Create `api/services/streak_service.py`:

```python
"""
Fuel Streak — single source of truth for the youth daily streak.

A "qualifying day" is a calendar day on which the athlete completed at least
`streak_min_confirms_per_day` fuel windows. Completion is read from the
`confirmations` table (the Today-screen confirm tap) unioned with `window_logs`
(the photo/voice/text capture path), so a day counts regardless of which path
the athlete used.

current/best streak are ALWAYS computed from those tables — never cached — so
they cannot drift. The streak_state table stores only non-derivable state
(freeze tokens, last-celebrated milestone).
"""

import sqlite3
from datetime import date, timedelta

MILESTONES = [2, 5, 10, 21]
DEFAULT_FREEZE_TOKENS = 1


def _as_date(value) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _min_confirms(conn) -> int:
    row = conn.execute(
        "SELECT value FROM report_config WHERE key = 'streak_min_confirms_per_day'"
    ).fetchone()
    return int(row["value"]) if row else 1


def _qualifying_dates(athlete_id: int, conn) -> set:
    """Set of YYYY-MM-DD strings the athlete qualified on (confirmations ∪ window_logs)."""
    min_c = _min_confirms(conn)
    rows = conn.execute(
        "SELECT log_date, COUNT(*) AS c FROM confirmations WHERE athlete_id = ? GROUP BY log_date",
        (athlete_id,),
    ).fetchall()
    days = {r["log_date"] for r in rows if r["c"] >= min_c}
    try:
        wl = conn.execute(
            "SELECT DISTINCT log_date FROM window_logs WHERE athlete_id = ?",
            (athlete_id,),
        ).fetchall()
        days |= {r["log_date"] for r in wl}
    except sqlite3.OperationalError:
        pass  # window_logs may be absent in minimal/legacy DBs
    return days


def _best_streak(qual: set) -> int:
    """Longest run of consecutive calendar days ever."""
    if not qual:
        return 0
    dates = sorted(date.fromisoformat(d) for d in qual)
    best = cur = 1
    for i in range(1, len(dates)):
        cur = cur + 1 if (dates[i] - dates[i - 1]).days == 1 else 1
        best = max(best, cur)
    return best


def _week_strip(qual: set, today: date) -> list:
    """Mon..Sun booleans for the week containing `today`."""
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)).isoformat() in qual for i in range(7)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_streak_service.py -k "qualifying or best_streak or week_strip" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/streak_service.py tests/test_streak_service.py
git commit -m "feat(streak): qualifying days, best streak, week strip helpers"
```

---

## Task 3: Current streak with today-grace and freeze

**Files:**
- Modify: `api/services/streak_service.py`
- Test: `tests/test_streak_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_streak_service.py`:

```python
def test_current_streak_counts_consecutive_days():
    conn = _streak_db()
    today = date(2026, 6, 17)
    for days_ago in range(3):  # 06-17, 06-16, 06-15
        _confirm(conn, 1, (today - timedelta(days=days_ago)).isoformat())
    assert ss.compute_current_streak(1, conn, today)["current"] == 3
    conn.close()


def test_today_not_logged_does_not_break_streak():
    """Today is still 'open' — a prior streak stays alive until the day ends."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())  # yesterday
    _confirm(conn, 1, (today - timedelta(days=2)).isoformat())  # day before
    # today NOT logged -> streak counts back from yesterday = 2 (not 0)
    assert ss.compute_current_streak(1, conn, today)["current"] == 2
    conn.close()


def test_freeze_bridges_one_missed_day():
    """One missed day within the last 7 is auto-protected (freeze)."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())                          # today
    # 06-16 MISSED
    _confirm(conn, 1, (today - timedelta(days=2)).isoformat())    # 06-15
    _confirm(conn, 1, (today - timedelta(days=3)).isoformat())    # 06-14
    result = ss.compute_current_streak(1, conn, today)
    assert result["current"] == 3          # today + 06-15 + 06-14, bridging 06-16
    assert result["freeze_used_this_week"] is True
    conn.close()


def test_freeze_bridges_at_most_one_day():
    """Two consecutive missed days cannot both be bridged with a single token."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())                          # today
    # 06-16 and 06-15 BOTH missed
    _confirm(conn, 1, (today - timedelta(days=3)).isoformat())    # 06-14
    # streak = just today; cannot reach 06-14 across a 2-day gap
    assert ss.compute_current_streak(1, conn, today)["current"] == 1
    conn.close()


def test_no_confirmations_is_zero():
    conn = _streak_db()
    assert ss.compute_current_streak(1, conn, date(2026, 6, 17))["current"] == 0
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_streak_service.py -k "current_streak or today_not_logged or freeze or no_confirmations" -v`
Expected: FAIL with `AttributeError: module 'api.services.streak_service' has no attribute 'compute_current_streak'`.

- [ ] **Step 3: Implement `compute_current_streak`**

Append to `api/services/streak_service.py`:

```python
def _freeze_tokens(athlete_id: int, conn) -> int:
    try:
        row = conn.execute(
            "SELECT freeze_tokens FROM streak_state WHERE athlete_id = ?",
            (athlete_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return DEFAULT_FREEZE_TOKENS
    return int(row["freeze_tokens"]) if row else DEFAULT_FREEZE_TOKENS


def compute_current_streak(athlete_id: int, conn, today=None) -> dict:
    """
    Consecutive qualifying days ending today (or yesterday if today is not yet
    logged — today never breaks the streak). Up to `freeze_tokens` missed days
    that fall within the rolling 7-day window are bridged (auto-freeze).
    """
    today_d = _as_date(today)
    qual = _qualifying_dates(athlete_id, conn)
    max_bridges = _freeze_tokens(athlete_id, conn)
    bridges_used = 0

    # Today-grace: if today is not yet logged, anchor on yesterday.
    anchor = today_d if today_d.isoformat() in qual else today_d - timedelta(days=1)
    streak = 0
    d = anchor
    while streak <= 3650:  # safety bound (~10y)
        if d.isoformat() in qual:
            streak += 1
            d -= timedelta(days=1)
            continue
        within_7 = d >= today_d - timedelta(days=6)
        if bridges_used < max_bridges and within_7:
            bridges_used += 1
            d -= timedelta(days=1)
            continue
        break

    return {"current": streak, "freeze_used_this_week": bridges_used > 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_streak_service.py -k "current_streak or today_not_logged or freeze or no_confirmations" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/streak_service.py tests/test_streak_service.py
git commit -m "feat(streak): current streak with today-grace and freeze"
```

---

## Task 4: Streak block, milestones, and confirmation registration

**Files:**
- Modify: `api/services/streak_service.py`
- Test: `tests/test_streak_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_streak_service.py`:

```python
def _streak_db_with_state():
    conn = _streak_db()
    _create_streak_state(conn)
    return conn


def test_get_streak_block_shape():
    conn = _streak_db_with_state()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())
    block = ss.get_streak(1, conn, today)
    assert block["current"] == 2
    assert block["today_done"] is True
    assert block["next_milestone"] == 5          # ladder 2/5/10/21, current 2 -> next 5
    assert block["just_reached_milestone"] is None  # read path never celebrates
    assert len(block["week_strip"]) == 7
    conn.close()


def test_register_confirmation_fires_milestone_once():
    conn = _streak_db_with_state()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())  # current = 2 -> tier 2

    first = ss.register_confirmation(1, conn, today)
    assert first["just_reached_milestone"] == 2   # crosses tier 2

    second = ss.register_confirmation(1, conn, today)
    assert second["just_reached_milestone"] is None  # already celebrated
    conn.close()


def test_register_confirmation_recelebrates_after_reset():
    conn = _streak_db_with_state()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())
    assert ss.register_confirmation(1, conn, today)["just_reached_milestone"] == 2

    # Simulate a later day where the streak has fallen back to 1, then climbs to 2 again.
    conn.execute("DELETE FROM confirmations")
    later = date(2026, 7, 1)
    _confirm(conn, 1, later.isoformat())
    _confirm(conn, 1, (later - timedelta(days=1)).isoformat())
    # last_celebrated reset happens on the intervening low-streak registration
    ss.register_confirmation(1, conn, later - timedelta(days=1))  # current 1 -> tier 0, resets marker
    assert ss.register_confirmation(1, conn, later)["just_reached_milestone"] == 2
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_streak_service.py -k "get_streak_block or register_confirmation" -v`
Expected: FAIL with `AttributeError: module 'api.services.streak_service' has no attribute 'get_streak'`.

- [ ] **Step 3: Implement `get_streak`, `register_confirmation`, `_ensure_streak_state`**

Append to `api/services/streak_service.py`:

```python
def _ensure_streak_state(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS streak_state (
            athlete_id                INTEGER PRIMARY KEY,
            freeze_tokens             INTEGER NOT NULL DEFAULT 1,
            last_celebrated_milestone INTEGER NOT NULL DEFAULT 0,
            updated_at                TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def get_streak(athlete_id: int, conn, today=None) -> dict:
    """Read-path streak block for the Today screen. Never celebrates (that is
    the write path's job), so `just_reached_milestone` is always None here."""
    today_d = _as_date(today)
    qual = _qualifying_dates(athlete_id, conn)
    cur = compute_current_streak(athlete_id, conn, today_d)
    next_m = next((m for m in MILESTONES if m > cur["current"]), None)
    return {
        "current": cur["current"],
        "best": _best_streak(qual),
        "week_strip": _week_strip(qual, today_d),
        "today_done": today_d.isoformat() in qual,
        "freeze_used_this_week": cur["freeze_used_this_week"],
        "next_milestone": next_m,
        "just_reached_milestone": None,
    }


def register_confirmation(athlete_id: int, conn, today=None) -> dict:
    """Write-path hook. Call after a confirmation is recorded. Updates the
    milestone marker and returns the streak block with `just_reached_milestone`
    set when the athlete crosses a new tier."""
    _ensure_streak_state(conn)
    block = get_streak(athlete_id, conn, today)
    cur = block["current"]
    reached = max((m for m in MILESTONES if m <= cur), default=0)

    row = conn.execute(
        "SELECT last_celebrated_milestone FROM streak_state WHERE athlete_id = ?",
        (athlete_id,),
    ).fetchone()
    last = int(row["last_celebrated_milestone"]) if row else 0

    just = None
    if reached != last:
        conn.execute(
            "INSERT INTO streak_state (athlete_id, last_celebrated_milestone) VALUES (?, ?) "
            "ON CONFLICT(athlete_id) DO UPDATE SET "
            "last_celebrated_milestone = excluded.last_celebrated_milestone, "
            "updated_at = datetime('now')",
            (athlete_id, reached),
        )
        conn.commit()
        if reached > last:          # climbing up -> celebrate; dropping -> just reset marker
            just = reached

    block["just_reached_milestone"] = just
    return block
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_streak_service.py -v`
Expected: PASS (all streak service tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/streak_service.py tests/test_streak_service.py
git commit -m "feat(streak): streak block, milestone tiers, confirmation registration"
```

---

## Task 5: Wire the streak into the confirmations route

**Files:**
- Modify: `api/routes/fuel_report.py:23-58`
- Test: `tests/test_streak_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_streak_service.py`:

```python
def test_register_is_importable_by_route_layer():
    # Guards the exact call the route makes: register_confirmation(athlete_id, conn, today=log_date)
    conn = _streak_db_with_state()
    _confirm(conn, 7, "2026-06-17")
    block = ss.register_confirmation(7, conn, today="2026-06-17")
    assert block["current"] == 1
    assert "just_reached_milestone" in block
    conn.close()
```

- [ ] **Step 2: Run test to verify it passes the service contract**

Run: `python -m pytest tests/test_streak_service.py::test_register_is_importable_by_route_layer -v`
Expected: PASS (the service already supports this signature — this test locks the contract the route depends on).

- [ ] **Step 3: Modify the route to register and return the streak**

In `api/routes/fuel_report.py`, in `record_confirmation`, replace everything from `from api.database import get_conn` (≈ line 43) through the end of the function (the `conn = get_conn()` block and its `try/finally`) with the following. Leave the validation above it (`window_key`/`window_type`/`log_date` checks) unchanged:

```python
    from api.database import get_conn
    from api.services import streak_service
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO confirmations (athlete_id, log_date, window_key, window_type) "
            "VALUES (?, ?, ?, ?)",
            (athlete_id, log_date, window_key, window_type),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM confirmations WHERE athlete_id = ? AND window_key = ? AND log_date = ?",
            (athlete_id, window_key, log_date),
        ).fetchone()
        streak = streak_service.register_confirmation(athlete_id, conn, today=log_date)
        return {**dict(row), "streak": streak}
    finally:
        conn.close()
```

- [ ] **Step 4: Verify the full backend test suite still passes**

Run: `python -m pytest tests/test_streak_service.py tests/test_fuel_report_service.py -v`
Expected: PASS (no regressions in the existing fuel-report tests).

- [ ] **Step 5: Commit**

```bash
git add api/routes/fuel_report.py tests/test_streak_service.py
git commit -m "feat(streak): confirmations endpoint returns streak block + milestone"
```

---

## Task 6: Surface the streak on `GET /today`

**Files:**
- Modify: `api/services/today_service.py:893-902`
- Test: `tests/test_streak_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_streak_service.py`:

```python
def test_build_today_view_includes_streak(monkeypatch):
    """build_today_view must add a 'streak' block computed from confirmations."""
    import api.services.today_service as tsvc

    conn = _streak_db_with_state()
    # Minimal athletes/events/meal_plans so build_today_view runs.
    conn.executescript("""
        CREATE TABLE athletes (id INTEGER PRIMARY KEY, first_name TEXT, sport TEXT);
        CREATE TABLE events (id INTEGER PRIMARY KEY, athlete_id INTEGER, event_type TEXT,
            event_name TEXT, event_date TEXT, start_time TEXT, duration_hours REAL);
        CREATE TABLE meal_plans (id INTEGER PRIMARY KEY, athlete_id INTEGER, plan_date TEXT,
            slot_name TEXT, logged INTEGER DEFAULT 0);
        INSERT INTO athletes (id, first_name, sport) VALUES (1, 'Alex', 'soccer');
    """)
    today = "2026-06-17"
    _confirm(conn, 1, today)

    # build_today_view imports these locally from their own modules, so patch THERE.
    import api.services.window_templates as wt
    import api.services.nutrition_analysis as na
    monkeypatch.setattr(
        wt, "generate_windows_for_day",
        lambda athlete_id, day, events, force_v2=False: {"day_type": "rest", "windows": []},
        raising=False,
    )
    monkeypatch.setattr(na, "get_week_start", lambda: "2026-06-15", raising=False)
    monkeypatch.setattr(na, "get_week_dates",
                        lambda ws: [f"2026-06-{15+i:02d}" for i in range(7)], raising=False)

    view = tsvc.build_today_view(1, conn, today=today)
    assert "streak" in view
    assert view["streak"]["current"] == 1
    assert view["streak"]["today_done"] is True
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_streak_service.py::test_build_today_view_includes_streak -v`
Expected: FAIL with `KeyError: 'streak'` (or `assert "streak" in view`).

- [ ] **Step 3: Add the streak block to `build_today_view`**

In `api/services/today_service.py`, inside `build_today_view`, change the final `return` dict (currently ending with `"readiness_grid": readiness_grid,`) to include the streak:

```python
    from api.services.streak_service import get_streak

    return {
        "athlete":        {"first_name": athlete["first_name"], "sport": athlete.get("sport", "soccer")},
        "today_event":    today_event,
        "today_events":   today_events,
        "day_type":       event_type,
        "readiness":      readiness,
        "windows":        windows,
        "next_game":      next_game,
        "readiness_grid": readiness_grid,
        "streak":         get_streak(athlete_id, conn, today_str),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_streak_service.py::test_build_today_view_includes_streak -v`
Expected: PASS.

- [ ] **Step 5: Run the whole backend streak suite**

Run: `python -m pytest tests/test_streak_service.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add api/services/today_service.py tests/test_streak_service.py
git commit -m "feat(streak): add streak block to GET /today response"
```

---

## Task 7: Mobile — extend the `TodayView` type

**Files:**
- Modify: `hooks/useTodayView.ts` *(mobile repo)*

> Run mobile commands from `/Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile`.

- [ ] **Step 1: Add the `TodayStreak` interface and field**

In `hooks/useTodayView.ts`, add this interface above `export interface TodayView`:

```ts
export interface TodayStreak {
  current: number;
  best: number;
  week_strip: boolean[];          // Mon..Sun
  today_done: boolean;
  freeze_used_this_week: boolean;
  next_milestone: number | null;
  just_reached_milestone: number | null;
}
```

Then add `streak` to the `TodayView` interface (after `readiness_grid`):

```ts
  readiness_grid: TodayGridDay[];
  streak: TodayStreak;
```

- [ ] **Step 2: Typecheck**

Run: `npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no new errors referencing `useTodayView.ts`.

- [ ] **Step 3: Commit**

```bash
git add hooks/useTodayView.ts
git commit -m "feat(streak): add TodayStreak type to TodayView"
```

---

## Task 8: Mobile — StreakStrip component, render, and celebration

**Files:**
- Create: `components/today/StreakStrip.tsx` *(mobile repo)*
- Modify: `app/(app)/today/index.tsx` *(mobile repo)*

- [ ] **Step 1: Create the StreakStrip component**

Create `components/today/StreakStrip.tsx`:

```tsx
import { View, Text, StyleSheet } from "react-native";
import { DS } from "../../constants/colors";
import { TodayStreak } from "../../hooks/useTodayView";

const DAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

export function StreakStrip({ streak }: { streak: TodayStreak | undefined }) {
  if (!streak) return null;

  const { current, best, week_strip, freeze_used_this_week } = streak;
  const hasStreak = current > 0;

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={styles.countWrap}>
          <Text style={styles.flame}>🔥</Text>
          <Text style={styles.count}>{current}</Text>
          <Text style={styles.label}>
            {hasStreak ? "day fuel streak" : "Start your streak today"}
          </Text>
        </View>
        {best > 0 ? <Text style={styles.best}>Best: {best}</Text> : null}
      </View>

      <View style={styles.dots}>
        {week_strip.map((filled, i) => (
          <View key={i} style={styles.dotCol}>
            <View style={[styles.dot, filled ? styles.dotOn : styles.dotOff]} />
            <Text style={styles.dotLabel}>{DAY_LABELS[i]}</Text>
          </View>
        ))}
      </View>

      {freeze_used_this_week ? (
        <Text style={styles.freezeNote}>❄️ A freeze kept your streak alive this week.</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 20,
    marginBottom: 12,
    padding: 16,
    backgroundColor: DS.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: DS.outlineVariant,
    borderRadius: 12,
  },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  countWrap: { flexDirection: "row", alignItems: "baseline" },
  flame: { fontSize: 20, marginRight: 6 },
  count: { fontSize: 26, fontWeight: "900", color: DS.primary, marginRight: 8 },
  label: { fontSize: 13, fontWeight: "600", color: DS.onPrimaryContainer },
  best: { fontSize: 12, fontWeight: "600", color: DS.outline },
  dots: { flexDirection: "row", justifyContent: "space-between", marginTop: 14 },
  dotCol: { alignItems: "center" },
  dot: { width: 16, height: 16, borderRadius: 8, marginBottom: 4 },
  dotOn: { backgroundColor: DS.primary },
  dotOff: { backgroundColor: DS.surfaceDim },
  dotLabel: { fontSize: 10, color: DS.outline },
  freezeNote: { marginTop: 10, fontSize: 11, color: DS.outline },
});
```

- [ ] **Step 2: Render StreakStrip below the hero**

In `app/(app)/today/index.tsx`, add the import near the other `components/today` imports:

```tsx
import { StreakStrip } from "../../../components/today/StreakStrip";
```

Then render it as the first child inside the `ScrollView` content, immediately before `<NextWindowCard ...>`:

```tsx
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={handleRefresh}
                tintColor={DS.primary}
              />
            }
            showsVerticalScrollIndicator={false}
          >
            <StreakStrip streak={displayData.streak} />

            <NextWindowCard
```

- [ ] **Step 3: Fire the milestone celebration in `handleConfirm`**

In `app/(app)/today/index.tsx`, replace the `try { ... }` block inside `handleConfirm` (the fetch + refetch) with a version that reads the response and celebrates on a milestone:

```tsx
    // 3. POST confirmation + refresh server state
    try {
      const res = await fetch(`${API_BASE}/api/athletes/${athleteId}/confirmations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          window_key:  window.slot_name,
          window_type: window.window_type ?? "pre_fuel",
          log_date:    getLocalDateStr(),
        }),
      });
      const body = await res.json().catch(() => null);
      const reached = body?.streak?.just_reached_milestone;
      if (reached) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        toast.show(`${reached}-day streak! You're on fire 🔥`);
      }
      await refetch();
    } catch {
      // Optimistic state stays; server truth reconciles on next pull-to-refresh
    }
```

- [ ] **Step 4: Typecheck**

Run: `npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no new errors referencing `StreakStrip.tsx` or `today/index.tsx`.

- [ ] **Step 5: Commit**

```bash
git add components/today/StreakStrip.tsx "app/(app)/today/index.tsx"
git commit -m "feat(streak): Today streak strip + milestone celebration"
```

---

## Task 9 (OPTIONAL, fast-follow): consolidate legacy streak callers

> v1 ships the Today streak without touching the legacy callers, to avoid behavioural regressions in `daily-summary` / `weekly-summary` / `fuel-report`. This task converges them onto the single service when you are ready. Skip for the first ship.

**Files:**
- Modify: `api/services/today_service.py` (`get_athlete_streak`)
- Modify: `api/services/fuel_report_service.py` (`compute_streak`)
- Test: `tests/test_streak_service.py`, `tests/test_fuel_report_service.py`

- [ ] **Step 1: Write a parity test**

Append to `tests/test_streak_service.py`:

```python
def test_get_athlete_streak_matches_service_current():
    """After consolidation, the legacy daily-summary streak equals the service current streak."""
    import api.services.today_service as tsvc
    conn = _streak_db_with_state()
    today = date.today()
    for days_ago in range(3):
        _confirm(conn, 1, (today - timedelta(days=days_ago)).isoformat())
    legacy = tsvc.get_athlete_streak(1, conn)
    assert legacy["current_streak"] == ss.compute_current_streak(1, conn, today)["current"]
    conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_streak_service.py::test_get_athlete_streak_matches_service_current -v`
Expected: FAIL (legacy reads `meal_logs`, service reads `confirmations`).

- [ ] **Step 3: Delegate `get_athlete_streak` to the service**

In `api/services/today_service.py`, replace the body of `get_athlete_streak` so `current_streak`/`best_streak` come from the service while preserving the existing return keys (`current_streak`, `best_streak`, `best_streak_date`, `week_logged`):

```python
def get_athlete_streak(athlete_id: int, conn) -> dict:
    from api.services import streak_service
    today = date.today()
    block = streak_service.get_streak(athlete_id, conn, today)
    qual = streak_service._qualifying_dates(athlete_id, conn)
    # Preserve best_streak_date for callers that display it.
    best_end = None
    if qual:
        dates = sorted(qual)
        best = run = 1
        from datetime import datetime as _dt
        for i in range(1, len(dates)):
            prev = _dt.strptime(dates[i - 1], "%Y-%m-%d").date()
            curr = _dt.strptime(dates[i], "%Y-%m-%d").date()
            run = run + 1 if (curr - prev).days == 1 else 1
            if run >= best:
                best, best_end = run, dates[i]
        if best_end is None:
            best_end = dates[-1]
    return {
        "current_streak": block["current"],
        "best_streak": block["best"],
        "best_streak_date": best_end,
        "week_logged": block["week_strip"],
    }
```

- [ ] **Step 4: Run to verify it passes (and no regressions)**

Run: `python -m pytest tests/test_streak_service.py tests/test_fuel_report_service.py tests/test_today_service.py -v`
Expected: PASS. If `tests/test_today_service.py` asserts the old `meal_logs` behaviour, update those assertions to the `confirmations`-union behaviour (this is the intended fix — the streak now reflects the athlete's real Today action).

- [ ] **Step 5: Commit**

```bash
git add api/services/today_service.py tests/test_streak_service.py
git commit -m "refactor(streak): legacy get_athlete_streak delegates to streak_service"
```

---

## Final Verification Checklist (manual)

- [ ] **Backend unit tests green:** `python -m pytest tests/test_streak_service.py tests/test_fuel_report_service.py -v`
- [ ] **Migration applies on a fresh DB:** start the API (`uvicorn api.main:app --reload --port 8000`); confirm startup logs no migration error and `streak_state` exists (`sqlite3 fuelup.db ".tables" | grep streak_state`).
- [ ] **`GET /today` returns the streak block:** `curl "localhost:8000/api/athletes/1/today?date=$(date +%F)" | python -m json.tool | grep -A8 '"streak"'`.
- [ ] **Confirm advances the streak:** `POST /api/athletes/1/confirmations` with `{window_key, window_type:"pre_fuel", log_date}` returns a `streak` object; re-fetch `/today` shows `current` incremented and `today_done: true`.
- [ ] **Milestone fires once:** drive the streak to 2 consecutive days; the confirmation response that crosses day 2 returns `just_reached_milestone: 2`; the next confirmation returns `null`.
- [ ] **Freeze forgives one miss:** with a 3-day history missing the middle day, `/today` shows the streak unbroken and `freeze_used_this_week: true`.
- [ ] **No-shame empty state:** an athlete with no confirmations sees "Start your streak today" and an empty week strip — never a "missed"/"lost" message.
- [ ] **Mobile typechecks:** from the mobile repo, `npx tsc --noEmit 2>&1 | grep -v node_modules` is clean.
- [ ] **Mobile renders:** Today screen shows 🔥 + count + 7 dots below the hero; confirming a window ticks the count and (at a tier) shows the celebration toast + haptic.
- [ ] **No nutrition number leaked:** the strip shows only the streak/consistency counters — never calories, macros, grams, or readiness score (honours the Today "no number" rule).

---

## Notes for the implementing agent

- **TDD order matters:** write each test, watch it fail, then implement. The in-memory SQLite fixture pattern mirrors `tests/test_fuel_report_service.py` exactly.
- **Timezone invariant:** always pass `today`/`log_date` from the client; never let the service fall back to `date.today()` in request paths (the mobile already sends `getLocalDateStr()`).
- **Cache vs truth:** `current`/`best` are always recomputed. `streak_state` stores only `freeze_tokens` and `last_celebrated_milestone`. Do not cache the streak count.
- **Scope discipline (YAGNI):** do NOT add push nudges, earned freezes, leaderboards, or parent surfaces — those are Phase 2 (see `docs/STREAK_DESIGN.md` §7).
