# Day Layout Engine + Activity Type (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend that turns calendar events + a per-event activity type into the Today-tab fuel-window *card order* Purvi specified, replacing `window_engine_v2` as the Today-tab window source (behind a flag), and store/resolve a new per-event `activity_type` with a 2-hour silent default.

**Architecture:** A new pure `day_layout.py` produces the ordered card list for a day from its events, their resolved activity types, and the timing primitives reused from `window_engine_v2`. A new `tournament_template.py` (Purvi's verbatim logic) handles multi-game days. A new `activity_type_resolver.py` applies the "untagged → practice at 2h before start" rule. `events.activity_type` is a new nullable column; `build_today_view` switches to `day_layout` behind a `DAY_LAYOUT_V2` flag, preserving the existing guardrails (06:30 floor, 15-min dedup, tappable cap).

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest. No new dependencies.

---

## Background facts (verified — read before starting)

**The 7 activity types already exist** in `api/services/activity_engine.py` as `MET_VALUES` + `_PROFILES` keys: `practice`, `game`, `tournament`, `speed_sprint`, `strength_cond`, `active_recovery`, `double_session`. Each profile already carries `cho_modifier`, `intensity_override`, `is_sc_day`, `layout` — and `get_activity_profile(activity_type, intensity, duration_min, wt_kg)` returns them. **No calculation work is needed; this plan is plumbing + ordering.**

**Per-window grams already exist:** `api/services/window_distribution.py` has `validate_windows(wt_kg, daily_cho_g, daily_prot_g, is_sc_day)` and `keep_going_window(wt_kg, duration_min)`. The day-layout produces *order*; grams are overlaid downstream by the existing `fuel_gauge.split_targets_across_windows` path. Do NOT recompute grams in `day_layout`.

**Today tab window source today** (`api/services/today_service.py:914` `build_today_view`):
```python
from api.services.window_templates import generate_windows_for_day
engine_result    = generate_windows_for_day(athlete_id, today_str, events, force_v2=force_v2)
event_type       = engine_result["day_type"]       # str
template_windows = engine_result["windows"]         # list of card dicts
```
`template_windows` items use keys: `key`, `label`, `category`, `category_key`, `macro_focus`, `sort_time`, `time_display`, `open_dt`, `close_dt`, `is_nudge_only`. `build_today_view` splits them into `tappable` + `nudges`, then `_build_fuel_targets_block` overlays grams. **Replacing the Today source = producing a compatible `{"day_type", "windows"}` result from `day_layout`.**

**Timing primitives to REUSE from `window_engine_v2.py`** (already correct, do not reinvent):
- `_parse_start(event) -> datetime`, `_event_end(event, start) -> datetime`
- `_floor(dt)` — clamps to the 06:30 `DISPLAY_FLOOR`
- `_hhmm(dt)`, `_display_time(dt)`, `_range(o, c)`
- `_minutes_between(a_hhmm, b_hhmm) -> float`
- Constants: `DISPLAY_FLOOR = time(6,30)`, `BETWEEN_WINDOW_MIN_GAP_MIN = 15`, `MAX_TAPPABLE_WINDOWS = 6`, `GAME_TYPES`, `TRAINING_TYPES`.

These are module-level in `window_engine_v2.py` and safe to import.

**Migration pattern** (additive, idempotent) — mirror `_add_diet_pref_to_athletes` in `api/services/db_migrations.py`:
```python
def _add_X(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(TABLE)").fetchall()]
    if "X" not in cols:
        conn.execute("ALTER TABLE TABLE ADD COLUMN X TYPE ...")
```
Register the new function inside `run_all()` alongside the other `_add_*` calls.

**Test conventions:** `tests/test_<module>.py`, run `python3 -m pytest tests/test_x.py -v` from `/Users/mayurkhera/AthFuelPath`. Pure-function tests import directly. `Date.now`-style nondeterminism: all functions that need "now" take an explicit `now: datetime` parameter so tests pass a fixed time — never call `datetime.now()` inside the pure functions.

**Spec — the card-order table (authoritative):**

| Day type / first event start | Card scroll order |
|---|---|
| Afternoon/Evening (first event ≥ 11:00) | everyday_meal → fuel_before → top_up → [event + keep_going if >75m] → recharge → rebuild |
| Morning (first event < 11:00) | fuel_before → top_up → [event + keep_going if >75m] → recharge → rebuild → everyday_meal |
| Tournament | `tournament_template.get_tournament_template()` |
| active_recovery (Active Recovery/Yoga) | breakfast → lunch → dinner (rest-style) |
| Rest (no calendar event) | breakfast → lunch → dinner (33/34/33 split) |
| Evening training (event end > 20:00) | standard order + a `wind_down` card appended after the session ends |

**Activity type → behavior** (already in `activity_engine._PROFILES`, restated for the layout):
`practice` standard · `game` standard, keep_going if >75m · `tournament` → template · `speed_sprint` standard, keep_going rare · `strength_cond` standard · `active_recovery` → rest-style 3 meals · `double_session` standard, keep_going on primary session only.

---

## File Structure

- **Create** `api/services/activity_type_resolver.py` — resolve the effective activity type for an event given `now` (the 2-hour default). Single responsibility: untagged-resolution.
- **Create** `api/services/tournament_template.py` — Purvi's `get_tournament_template(game_schedule, wt_kg)` (pure card-ordering for multi-game days).
- **Create** `api/services/day_layout.py` — the day-layout engine: `build_day_layout(events, athlete, now)` → `{"day_type", "cards"}`. Orchestrates the spec table, reuses `window_engine_v2` timing primitives, calls `tournament_template` for tournament days, ports the guardrails. Single responsibility: card ordering + timing for the Today tab.
- **Modify** `api/services/db_migrations.py` — add `_add_activity_type_to_events()`, register in `run_all()`.
- **Modify** `api/models.py` — `EventCreate`/`EventUpdate`/`EventResponse` gain `activity_type: Optional[str]`.
- **Modify** `api/routes/events.py` — persist `activity_type` on create/update; add `PATCH /events/{event_id}/activity-type` to tag an event.
- **Modify** `api/services/today_service.py` — `build_today_view` switches to `day_layout` behind `DAY_LAYOUT_V2`, mapping its cards into the existing `template_windows` shape.

**Card dict shape** (canonical — every task uses exactly this):
```python
{
  "key":          str,        # unique within the day, e.g. "fuel_before", "event_1", "recharge_after_g1"
  "card":         str,        # kind: everyday_meal|fuel_before|top_up|keep_going|event|recharge|rebuild|wind_down|breakfast|lunch|dinner
  "label":        str,        # display label
  "is_event":     bool,       # True only for the visible non-tappable game marker
  "is_tappable":  bool,       # False for event markers; True for fuel windows
  "sort_time":    str,        # "HH:MM" 24h — drives ordering ties + timeline position
  "time_display": str,        # "H:MM AM – H:MM PM" or "H:MM AM"
  "game_num":     int | None, # tournament per-game cards only
  "duration_min": int | None, # event/keep_going cards only
}
```

---

## Task 1: Tournament template (Purvi's verbatim logic)

**Files:**
- Create: `api/services/tournament_template.py`
- Test: `tests/test_tournament_template.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tournament_template.py`:

```python
from api.services.tournament_template import get_tournament_template


def test_everyday_meal_before_when_first_game_at_or_after_11am():
    sched = [{"start_time": "11:00", "duration_min": 90}]
    cards = get_tournament_template(sched, 50)
    assert cards[0]["card"] == "everyday_meal"
    assert cards[0]["title"] == "Tournament Base Meal"


def test_everyday_meal_after_when_first_game_before_11am():
    sched = [{"start_time": "09:00", "duration_min": 90}]
    cards = get_tournament_template(sched, 50)
    assert cards[0]["card"] != "everyday_meal"          # not first
    assert cards[-1]["card"] == "everyday_meal"          # last
    assert cards[-1]["title"] == "Wind-Down Meal"


def test_per_game_windows_and_keep_going_over_75():
    sched = [{"start_time": "09:00", "duration_min": 90}]
    cards = get_tournament_template(sched, 50)
    kinds = [c["card"] for c in cards]
    assert "fuel_before" in kinds and "top_up" in kinds and "event" in kinds
    assert "keep_going" in kinds                          # 90 > 75


def test_no_keep_going_under_75():
    sched = [{"start_time": "09:00", "duration_min": 60}]
    cards = get_tournament_template(sched, 50)
    assert "keep_going" not in [c["card"] for c in cards]


def test_between_game_recharge_at_45_rebuild_at_90():
    # game1 09:00-10:30, game2 12:30 → gap 120 min → recharge AND rebuild between
    sched = [{"start_time": "09:00", "duration_min": 90},
             {"start_time": "12:30", "duration_min": 90}]
    cards = get_tournament_template(sched, 50)
    labels = [c.get("label", "") for c in cards]
    assert any("Between Games 1 & 2" in l for l in labels)       # recharge
    assert any("Pre-Game 2 Meal" in l for l in labels)           # rebuild


def test_short_gap_recharge_only_no_rebuild():
    # game1 09:00-10:30, game2 11:30 → gap 60 min → recharge yes, rebuild no
    sched = [{"start_time": "09:00", "duration_min": 90},
             {"start_time": "11:30", "duration_min": 90}]
    cards = get_tournament_template(sched, 50)
    labels = [c.get("label", "") for c in cards]
    assert any("Between Games 1 & 2" in l for l in labels)
    assert not any("Pre-Game 2 Meal" in l for l in labels)


def test_post_tournament_recharge_and_rebuild_always_present():
    sched = [{"start_time": "09:00", "duration_min": 60}]
    cards = get_tournament_template(sched, 50)
    labels = [c.get("label", "") for c in cards]
    assert any("After Final Game" in l for l in labels)
    assert any("Tournament Recovery Meal" in l for l in labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_tournament_template.py -v`
Expected: FAIL with `ModuleNotFoundError: api.services.tournament_template`

- [ ] **Step 3: Implement**

Create `api/services/tournament_template.py` (Purvi's spec, house-styled; adds the canonical card fields):

```python
"""
Tournament Template — dynamic multi-game day layout (Purvi spec).

Pure card-ordering for tournament days. Grams are NOT computed here — they are
overlaid downstream by window_distribution / fuel_gauge. Everyday Meal anchors
the day: BEFORE the first window if first game >= 11:00, else AFTER (Wind-Down).
Between games: Recharge at gap >= 45 min, Rebuild at gap >= 90 min.
"""

_BASE_MEAL_COLOR = "#7A9E6E"


def _add_min(t: str, m: int) -> str:
    h, mn = map(int, t.split(":"))
    total = h * 60 + mn + m
    return f"{total // 60:02d}:{total % 60:02d}"


def _diff_min(t1: str, t2: str) -> int:
    def mins(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m
    return mins(t2) - mins(t1)


def get_tournament_template(game_schedule: list, wt_kg: float) -> list:
    """game_schedule = [{'start_time':'HH:MM','duration_min':int}, ...] sorted by time."""
    cards = []
    first_game_hour = int(game_schedule[0]["start_time"].split(":")[0])
    everyday_pos = "before" if first_game_hour >= 11 else "after"

    if everyday_pos == "before":
        cards.append({
            "key": "everyday_meal", "card": "everyday_meal", "label": "Tournament Base Meal",
            "title": "Tournament Base Meal",
            "body": ("Start your tournament day with a solid meal before anything else. "
                     "This is the base your fuel windows build on. "
                     "2 fists of grains · 1 palm of protein · vegetables."),
            "subtitle": "TOURNAMENT DAY FUEL", "color": _BASE_MEAL_COLOR,
            "is_event": False, "is_tappable": True,
            "sort_time": game_schedule[0]["start_time"], "time_display": "",
            "game_num": None, "duration_min": None,
        })

    for i, game in enumerate(game_schedule):
        n = i + 1
        st = game["start_time"]
        dur = game["duration_min"]
        cards.append({"key": f"fuel_before_g{n}", "card": "fuel_before",
                      "label": f"Fuel Before — Game {n}", "game_num": n,
                      "is_event": False, "is_tappable": True,
                      "sort_time": _add_min(st, -180), "time_display": "",
                      "duration_min": None})
        cards.append({"key": f"top_up_g{n}", "card": "top_up",
                      "label": f"Top-Up — Game {n}", "game_num": n,
                      "is_event": False, "is_tappable": True,
                      "sort_time": _add_min(st, -45), "time_display": "",
                      "duration_min": None})
        cards.append({"key": f"event_g{n}", "card": "event",
                      "label": f"Game {n}", "game_num": n,
                      "is_event": True, "is_tappable": False,
                      "sort_time": st, "time_display": "", "duration_min": dur})
        if dur > 75:
            cards.append({"key": f"keep_going_g{n}", "card": "keep_going",
                          "label": f"Keep Going — Game {n}", "game_num": n,
                          "is_event": False, "is_tappable": True,
                          "sort_time": _add_min(st, dur // 2), "time_display": "",
                          "duration_min": dur})

        if n < len(game_schedule):
            this_end = _add_min(st, dur)
            next_start = game_schedule[i + 1]["start_time"]
            gap = _diff_min(this_end, next_start)
            if gap >= 45:
                cards.append({"key": f"recharge_g{n}_g{n+1}", "card": "recharge",
                              "label": f"Recharge — Between Games {n} & {n+1}",
                              "body": (f"You have {gap} minutes. Refuel NOW. "
                                       f"Fast carbs + protein within 30 minutes."),
                              "game_num": n, "is_event": False, "is_tappable": True,
                              "sort_time": this_end, "time_display": "", "duration_min": None})
            if gap >= 90:
                cards.append({"key": f"rebuild_g{n}_g{n+1}", "card": "rebuild",
                              "label": f"Rebuild — Pre-Game {n+1} Meal",
                              "body": ("More time between games — get a proper recovery meal in. "
                                       "Protein + carbs + healthy fat. Your body needs this."),
                              "game_num": n, "is_event": False, "is_tappable": True,
                              "sort_time": _add_min(this_end, 30), "time_display": "",
                              "duration_min": None})

    last = game_schedule[-1]
    final_end = _add_min(last["start_time"], last["duration_min"])
    cards.append({"key": "recharge_final", "card": "recharge", "label": "Recharge — After Final Game",
                  "is_event": False, "is_tappable": True,
                  "sort_time": final_end, "time_display": "", "game_num": None, "duration_min": None})
    cards.append({"key": "rebuild_final", "card": "rebuild", "label": "Rebuild — Tournament Recovery Meal",
                  "is_event": False, "is_tappable": True,
                  "sort_time": _add_min(final_end, 60), "time_display": "", "game_num": None, "duration_min": None})

    if everyday_pos == "after":
        cards.append({
            "key": "everyday_meal", "card": "everyday_meal", "label": "Wind-Down Meal",
            "title": "Wind-Down Meal",
            "body": ("Tournament done. This meal rounds out your day. "
                     "Protein · carbs · healthy fat."),
            "subtitle": "EVERYDAY FUEL", "color": _BASE_MEAL_COLOR,
            "is_event": False, "is_tappable": True,
            "sort_time": _add_min(final_end, 120), "time_display": "",
            "game_num": None, "duration_min": None,
        })

    return cards
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_tournament_template.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/tournament_template.py tests/test_tournament_template.py
git commit -m "feat: tournament_template — multi-game day card ordering (Purvi spec)"
```

---

## Task 2: Activity-type resolver (2-hour silent default)

**Files:**
- Create: `api/services/activity_type_resolver.py`
- Test: `tests/test_activity_type_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_activity_type_resolver.py`:

```python
from datetime import datetime
from api.services.activity_type_resolver import resolve_activity_type

VALID = {"practice", "game", "tournament", "speed_sprint",
         "strength_cond", "active_recovery", "double_session"}


def _ev(activity_type=None, event_date="2026-06-27", start_time="15:00"):
    return {"activity_type": activity_type, "event_date": event_date, "start_time": start_time}


def test_explicit_tag_always_wins():
    ev = _ev(activity_type="game")
    now = datetime(2026, 6, 25, 8, 0)   # days before
    assert resolve_activity_type(ev, now) == "game"


def test_untagged_stays_none_more_than_2h_before_start():
    ev = _ev(activity_type=None, start_time="15:00")
    now = datetime(2026, 6, 27, 12, 0)   # 3h before start
    assert resolve_activity_type(ev, now) is None


def test_untagged_defaults_to_practice_at_exactly_2h_before():
    ev = _ev(activity_type=None, start_time="15:00")
    now = datetime(2026, 6, 27, 13, 0)   # exactly 2h before
    assert resolve_activity_type(ev, now) == "practice"


def test_untagged_defaults_to_practice_after_start():
    ev = _ev(activity_type=None, start_time="15:00")
    now = datetime(2026, 6, 27, 16, 0)   # after start
    assert resolve_activity_type(ev, now) == "practice"


def test_invalid_stored_value_treated_as_untagged():
    ev = _ev(activity_type="bogus", start_time="15:00")
    now = datetime(2026, 6, 27, 10, 0)   # >2h before
    assert resolve_activity_type(ev, now) is None


def test_no_start_time_defaults_to_practice_when_tagged_blank():
    # All-day / no start_time: cannot compute a 2h boundary → treat as practice
    ev = _ev(activity_type=None, start_time=None)
    now = datetime(2026, 6, 27, 10, 0)
    assert resolve_activity_type(ev, now) == "practice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_activity_type_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `api/services/activity_type_resolver.py`:

```python
"""
Activity-type resolution with the 2-hour silent default.

An event's activity_type is either explicitly tagged by the athlete (one of the
7 engine keys) or untagged. Untagged events stay None (the UI keeps nudging)
until `now` reaches 2 hours before the event start, at which point they silently
resolve to 'practice' so the fueling plan locks in before the event.
"""

from datetime import datetime, timedelta

VALID_ACTIVITY_TYPES = {
    "practice", "game", "tournament", "speed_sprint",
    "strength_cond", "active_recovery", "double_session",
}

DEFAULT_ACTIVITY_TYPE = "practice"
AUTO_DEFAULT_LEAD_HOURS = 2


def resolve_activity_type(event: dict, now: datetime):
    """Return the effective activity_type, or None if still awaiting a tag.

    event needs: activity_type (str|None), event_date ('YYYY-MM-DD'), start_time ('HH:MM'|None).
    """
    tag = event.get("activity_type")
    if tag in VALID_ACTIVITY_TYPES:
        return tag

    start_time = event.get("start_time")
    event_date = event.get("event_date")
    if not start_time or not event_date:
        # No usable start boundary → lock in the default immediately.
        return DEFAULT_ACTIVITY_TYPE

    start_dt = datetime.strptime(f"{event_date} {start_time}", "%Y-%m-%d %H:%M")
    deadline = start_dt - timedelta(hours=AUTO_DEFAULT_LEAD_HOURS)
    if now >= deadline:
        return DEFAULT_ACTIVITY_TYPE
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_activity_type_resolver.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/activity_type_resolver.py tests/test_activity_type_resolver.py
git commit -m "feat: activity_type_resolver — 2-hour silent default to practice"
```

---

## Task 3: `events.activity_type` column migration

**Files:**
- Modify: `api/services/db_migrations.py`
- Test: `tests/test_activity_type_migration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_activity_type_migration.py`:

```python
import os
os.environ["DB_PATH"] = ":memory:"
import sqlite3
from api.services.db_migrations import _add_activity_type_to_events


def test_adds_activity_type_column_idempotently():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, event_type TEXT)")
    _add_activity_type_to_events(conn)            # first run adds it
    _add_activity_type_to_events(conn)            # second run is a no-op (idempotent)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    assert "activity_type" in cols
    # default is NULL (untagged)
    conn.execute("INSERT INTO events (event_type) VALUES ('practice')")
    row = conn.execute("SELECT activity_type FROM events").fetchone()
    assert row[0] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_activity_type_migration.py -v`
Expected: FAIL with `ImportError: cannot import name '_add_activity_type_to_events'`

- [ ] **Step 3: Implement**

In `api/services/db_migrations.py`, add the function near the other event-column migrations (e.g. after `_add_venue_location_to_events`):

```python
def _add_activity_type_to_events(conn):
    """Per-event activity type tagged by the athlete (Calendar Sync & Day Layout).
    One of the 7 activity_engine keys: practice / game / tournament / speed_sprint /
    strength_cond / active_recovery / double_session. Nullable = untagged; the
    2-hour default (activity_type_resolver) resolves untagged events to 'practice'
    on read. Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "activity_type" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN activity_type TEXT DEFAULT NULL")
```

And register it inside `run_all()` alongside the other `_add_*` calls (e.g. right after `_add_venue_location_to_events(conn)`):

```python
        _add_venue_location_to_events(conn)
        _add_activity_type_to_events(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_activity_type_migration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/db_migrations.py tests/test_activity_type_migration.py
git commit -m "feat: events.activity_type column migration (nullable, additive)"
```

---

## Task 4: Models + route — persist and tag `activity_type`

**Files:**
- Modify: `api/models.py`
- Modify: `api/routes/events.py`
- Test: `tests/test_activity_type_route.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_activity_type_route.py`:

```python
import os
os.environ["DB_PATH"] = ":memory:"
from fastapi.testclient import TestClient
from api.main import app
from api.database import get_conn

client = TestClient(app)


def _make_parent_and_athlete():
    conn = get_conn()
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P','p@x.com',1)")
    pid = conn.execute("SELECT id FROM parents WHERE email='p@x.com'").fetchone()[0]
    conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (?, 'A', 14, 'boy', 120, 5, 4)", (pid,))
    aid = conn.execute("SELECT id FROM athletes WHERE parent_id=?", (pid,)).fetchone()[0]
    conn.commit(); conn.close()
    return aid


def test_create_event_stores_activity_type():
    aid = _make_parent_and_athlete()
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Speed work", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
        "activity_type": "speed_sprint",
    })
    assert r.status_code == 201, r.text
    assert r.json()["activity_type"] == "speed_sprint"


def test_create_event_activity_type_defaults_null():
    aid = _make_parent_and_athlete()
    r = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Mystery", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
    })
    assert r.status_code == 201
    assert r.json()["activity_type"] is None


def test_patch_tags_activity_type():
    aid = _make_parent_and_athlete()
    ev = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Mystery", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
    }).json()
    r = client.patch(f"/api/events/{ev['id']}/activity-type", json={"activity_type": "game"})
    assert r.status_code == 200, r.text
    assert r.json()["activity_type"] == "game"


def test_patch_rejects_invalid_activity_type():
    aid = _make_parent_and_athlete()
    ev = client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "X", "event_type": "practice",
        "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0,
    }).json()
    r = client.patch(f"/api/events/{ev['id']}/activity-type", json={"activity_type": "bogus"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_activity_type_route.py -v`
Expected: FAIL (activity_type not accepted / PATCH route 404)

- [ ] **Step 3: Implement the models**

In `api/models.py`, add to `EventCreate` (after `intensity`):
```python
    activity_type: Optional[str] = None  # 7 engine keys; None = untagged (2h default applies)
```
Add the same line to `EventUpdate`. Add to `EventResponse` (after `intensity`):
```python
    activity_type: Optional[str] = None
```
Add a new request model at the end of the event-models section:
```python
class ActivityTypePatch(BaseModel):
    activity_type: str

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type(cls, v):
        from api.services.activity_type_resolver import VALID_ACTIVITY_TYPES
        if v not in VALID_ACTIVITY_TYPES:
            raise ValueError(f"activity_type must be one of {sorted(VALID_ACTIVITY_TYPES)}")
        return v
```

- [ ] **Step 4: Implement the route changes**

In `api/routes/events.py`:

Add to the import line: `from api.models import EventCreate, EventUpdate, EventResponse, ActivityTypePatch`.

In `create_event`, extend the INSERT to include `activity_type`:
```python
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours, city, venue_name, address, latitude, longitude, intensity, activity_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data.athlete_id, data.event_name, data.event_type, data.event_date, data.start_time, data.duration_hours,
             data.city, data.venue_name, data.address, data.latitude, data.longitude, intensity, data.activity_type),
        )
```

In `update_event`, after the existing field-merge block, add:
```python
        new_activity_type = data.activity_type if data.activity_type is not None else existing["activity_type"]
```
and extend the UPDATE statement's SET list with `activity_type=?` and the value tuple with `new_activity_type` (place it right after `intensity=?` / `new_intensity`).

Add a new endpoint after `update_event`:
```python
@router.patch("/{event_id}/activity-type", response_model=EventResponse)
def tag_activity_type(event_id: int, data: ActivityTypePatch):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found.")
        conn.execute(
            "UPDATE events SET activity_type = ? WHERE id = ?",
            (data.activity_type, event_id),
        )
        conn.commit()
        ev = dict(conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
        on_event_added_or_changed(ev["athlete_id"], ev["event_date"], conn)
        return ev
    finally:
        conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_activity_type_route.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add api/models.py api/routes/events.py tests/test_activity_type_route.py
git commit -m "feat: persist + PATCH events.activity_type (validated to 7 keys)"
```

---

## Task 5: `day_layout` — rest & active-recovery 3-meal layout

**Files:**
- Create: `api/services/day_layout.py`
- Test: `tests/test_day_layout.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_day_layout.py`:

```python
from datetime import datetime
from api.services.day_layout import build_day_layout


def _athlete():
    return {"id": 1, "weight_lbs": 120, "height_ft": 5, "height_in": 4,
            "gender": "boy", "age": 14}


def test_rest_day_three_meals_3334():
    # No events → rest day → breakfast/lunch/dinner
    res = build_day_layout([], _athlete(), now=datetime(2026, 6, 27, 7, 0))
    assert res["day_type"] == "rest"
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["breakfast", "lunch", "dinner"]
    assert all(c["is_tappable"] for c in res["cards"])


def test_active_recovery_uses_rest_style_three_meals():
    ev = {"id": 9, "event_type": "practice", "activity_type": "active_recovery",
          "event_date": "2026-06-27", "start_time": "10:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert res["day_type"] == "active_recovery"
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["breakfast", "lunch", "dinner"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the module skeleton + rest/active-recovery path**

Create `api/services/day_layout.py`:

```python
"""
Day Layout Engine — Today-tab fuel-window card ordering (Purvi spec).

Produces the ordered card list for a day from its events + resolved activity
types. Reuses window_engine_v2 timing primitives; grams are overlaid downstream.
Replaces window_engine_v2 as the Today-tab window source (behind DAY_LAYOUT_V2).

Public API: build_day_layout(events, athlete, now) -> {"day_type", "cards"}
"""

from datetime import datetime, time, timedelta

from api.services.activity_type_resolver import resolve_activity_type
from api.services.tournament_template import get_tournament_template
from api.services import window_engine_v2 as wev2

REST_MEAL_TIMES = {"breakfast": "07:30", "lunch": "12:30", "dinner": "18:30"}


def _rest_meal_cards() -> list:
    """Breakfast/Lunch/Dinner rest-style cards (33/34/33 split applied downstream)."""
    cards = []
    for kind in ("breakfast", "lunch", "dinner"):
        t = REST_MEAL_TIMES[kind]
        cards.append({
            "key": kind, "card": kind, "label": kind.capitalize(),
            "is_event": False, "is_tappable": True,
            "sort_time": t, "time_display": "", "game_num": None, "duration_min": None,
        })
    return cards


def build_day_layout(events: list, athlete: dict, now: datetime) -> dict:
    """Return {"day_type": str, "cards": [card, ...]} for the athlete's day.

    events: rows for the target date (each a dict with event_type, activity_type,
            event_date, start_time, duration_hours).
    """
    # Resolve each event's effective activity type (2-hour default).
    resolved = []
    for ev in events:
        at = resolve_activity_type(ev, now)
        resolved.append((ev, at))

    # Rest day — no events at all.
    if not resolved:
        return {"day_type": "rest", "cards": _rest_meal_cards()}

    # Active Recovery / Yoga → rest-style 3 meals regardless of time.
    if any(at == "active_recovery" for _, at in resolved):
        return {"day_type": "active_recovery", "cards": _rest_meal_cards()}

    # Other day types implemented in later tasks.
    raise NotImplementedError("standard / tournament layouts: Tasks 6-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/day_layout.py tests/test_day_layout.py
git commit -m "feat: day_layout skeleton + rest/active-recovery 3-meal layout"
```

---

## Task 6: `day_layout` — standard single-event day (morning vs afternoon)

**Files:**
- Modify: `api/services/day_layout.py`
- Test: `tests/test_day_layout.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout.py`:

```python
def test_morning_event_order_everyday_last():
    # Practice starting 09:00 (<11:00) → fuel_before → top_up → event → recharge → rebuild → everyday_meal
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["fuel_before", "top_up", "event", "recharge", "rebuild", "everyday_meal"]
    # event marker is visible, non-tappable
    event_card = next(c for c in res["cards"] if c["card"] == "event")
    assert event_card["is_event"] is True and event_card["is_tappable"] is False


def test_afternoon_event_order_everyday_first():
    # Practice starting 15:00 (>=11:00) → everyday_meal → fuel_before → top_up → event → recharge → rebuild
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["everyday_meal", "fuel_before", "top_up", "event", "recharge", "rebuild"]


def test_keep_going_appears_only_over_75min():
    long_ev = {"id": 1, "event_type": "game", "activity_type": "game",
               "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.5}  # 90 min
    res = build_day_layout([long_ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "keep_going" in [c["card"] for c in res["cards"]]

    short_ev = {**long_ev, "duration_hours": 1.0}  # 60 min
    res2 = build_day_layout([short_ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "keep_going" not in [c["card"] for c in res2["cards"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Implement the standard single-event path**

In `api/services/day_layout.py`, add a helper and replace the `raise NotImplementedError` with the standard-day branch:

```python
def _standard_single_event_cards(ev: dict, start_dt: datetime, end_dt: datetime) -> list:
    """Spec order for a single non-tournament event. everyday_meal placement flips
    on the 11:00 boundary; keep_going only when duration > 75 min."""
    dur_min = int(round((ev.get("duration_hours") or 1.5) * 60))
    morning = start_dt.hour < 11

    def card(key, kind, sort_dt, label, is_event=False, duration_min=None):
        return {"key": key, "card": kind, "label": label,
                "is_event": is_event, "is_tappable": not is_event,
                "sort_time": wev2._hhmm(sort_dt), "time_display": "",
                "game_num": None, "duration_min": duration_min}

    everyday = card("everyday_meal", "everyday_meal",
                    start_dt.replace(hour=7, minute=30) if morning else start_dt.replace(hour=7, minute=30),
                    "Everyday Meal")

    core = [
        card("fuel_before", "fuel_before", start_dt - timedelta(hours=3), "Fuel Before"),
        card("top_up", "top_up", start_dt - timedelta(minutes=45), "Top-Up"),
        card("event", "event", start_dt, f"{ev.get('event_name') or ev['event_type'].capitalize()}",
             is_event=True, duration_min=dur_min),
    ]
    if dur_min > 75:
        core.append(card("keep_going", "keep_going", start_dt + timedelta(minutes=dur_min // 2),
                         "Keep Going", duration_min=dur_min))
    core += [
        card("recharge", "recharge", end_dt, "Recharge"),
        card("rebuild", "rebuild", end_dt + timedelta(hours=1), "Rebuild"),
    ]

    # everyday placement: morning → last, afternoon/evening → first
    return core + [everyday] if morning else [everyday] + core
```

Then, in `build_day_layout`, replace the final `raise NotImplementedError(...)` with:

```python
    # Single non-tournament event → standard layout.
    primary_ev, _ = resolved[0]
    start_dt = wev2._parse_start(_as_wev2_event(primary_ev))
    end_dt = wev2._event_end(_as_wev2_event(primary_ev), start_dt)
    day_type = "standard"
    cards = _standard_single_event_cards(primary_ev, start_dt, end_dt)
    return {"day_type": day_type, "cards": cards}
```

Add this adapter near the top of the module (after the imports) so the wev2 timing helpers accept our plain dict:

```python
def _as_wev2_event(ev: dict):
    """Adapt a plain event dict to the attribute access wev2 timing helpers expect."""
    return wev2.Event(
        id=ev.get("id", 0), athlete_id=ev.get("athlete_id", 0),
        event_type=ev["event_type"], event_date=ev["event_date"],
        start_time=ev["start_time"], duration_hours=ev.get("duration_hours"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/day_layout.py tests/test_day_layout.py
git commit -m "feat: day_layout standard single-event order (morning/afternoon + keep_going)"
```

---

## Task 7: `day_layout` — evening wind-down card (event ends > 20:00)

**Files:**
- Modify: `api/services/day_layout.py`
- Test: `tests/test_day_layout.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout.py`:

```python
def test_evening_training_appends_wind_down():
    # Practice 19:00 for 2h → ends 21:00 (>20:00) → wind_down appended at the end
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "19:00", "duration_hours": 2.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    kinds = [c["card"] for c in res["cards"]]
    assert kinds[-1] == "wind_down"
    wd = res["cards"][-1]
    assert wd["is_tappable"] is True


def test_no_wind_down_when_event_ends_before_8pm():
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}  # ends 16:00
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "wind_down" not in [c["card"] for c in res["cards"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: FAIL (`wind_down` missing)

- [ ] **Step 3: Implement**

In `api/services/day_layout.py`, define the threshold constant near the top:
```python
EVENING_WIND_DOWN_AFTER = time(20, 0)  # event end past 8:00 PM → optional wind-down card
```

In `build_day_layout`, just before the standard-day `return`, append the wind-down card when the event ends after 20:00:

```python
    if end_dt.time() > EVENING_WIND_DOWN_AFTER:
        cards.append({
            "key": "wind_down", "card": "wind_down", "label": "Evening Wind-Down",
            "is_event": False, "is_tappable": True,
            "sort_time": wev2._hhmm(end_dt + timedelta(minutes=30)), "time_display": "",
            "game_num": None, "duration_min": None,
        })
    return {"day_type": day_type, "cards": cards}
```

(Replace the previous single-line `return {"day_type": day_type, "cards": cards}` from Task 6 with the block above.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/day_layout.py tests/test_day_layout.py
git commit -m "feat: day_layout evening wind-down card for events ending after 8pm"
```

---

## Task 8: `day_layout` — tournament & multi-game days

**Files:**
- Modify: `api/services/day_layout.py`
- Test: `tests/test_day_layout.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout.py`:

```python
def test_tournament_activity_type_uses_template():
    ev = {"id": 1, "event_type": "tournament", "activity_type": "tournament",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.5}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert res["day_type"] == "tournament"
    # tournament template emits final recharge + rebuild
    labels = [c.get("label", "") for c in res["cards"]]
    assert any("After Final Game" in l for l in labels)


def test_two_games_same_day_is_tournament():
    g1 = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.5}
    g2 = {"id": 2, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "13:00", "duration_hours": 1.5}
    res = build_day_layout([g1, g2], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert res["day_type"] == "tournament"
    # between-games recharge present (gap 13:00 - 10:30 = 150 min >= 90 → recharge + rebuild)
    labels = [c.get("label", "") for c in res["cards"]]
    assert any("Between Games 1 & 2" in l for l in labels)
    assert any("Pre-Game 2 Meal" in l for l in labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: FAIL (day_type not "tournament" / template not used)

- [ ] **Step 3: Implement**

In `api/services/day_layout.py`, add tournament detection + dispatch. Place this branch in `build_day_layout` **after** the active-recovery check and **before** the single-event standard path:

```python
    # Tournament: explicit tournament tag, OR >= 2 game/tournament events same day.
    game_like = [(ev, at) for ev, at in resolved
                 if at in ("game", "tournament") or ev["event_type"] in ("game", "tournament")]
    is_tournament = (
        any(at == "tournament" for _, at in resolved)
        or len(game_like) >= 2
    )
    if is_tournament:
        schedule = sorted(
            ({"start_time": ev["start_time"],
              "duration_min": int(round((ev.get("duration_hours") or 1.5) * 60))}
             for ev, _ in resolved if ev.get("start_time")),
            key=lambda g: g["start_time"],
        )
        wt_kg = athlete["weight_lbs"] * 0.453592 if athlete.get("weight_lbs") else 0
        cards = get_tournament_template(schedule, wt_kg)
        return {"day_type": "tournament", "cards": cards}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/day_layout.py tests/test_day_layout.py
git commit -m "feat: day_layout tournament dispatch (explicit tag or >=2 games)"
```

---

## Task 9: `day_layout` — port guardrails (06:30 floor, 15-min dedup, tappable cap)

**Files:**
- Modify: `api/services/day_layout.py`
- Test: `tests/test_day_layout.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout.py`:

```python
def test_guardrail_floor_no_card_before_0630():
    # Early game 07:00 → fuel_before would be 04:00 → must be floored to 06:30
    ev = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "07:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 5, 0))
    for c in res["cards"]:
        assert c["sort_time"] >= "06:30", f"{c['card']} at {c['sort_time']}"


def test_guardrail_caps_tappable_windows_at_6():
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 2.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    tappable = [c for c in res["cards"] if c["is_tappable"]]
    assert len(tappable) <= 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: FAIL (a card sorts before 06:30, or >6 tappable)

- [ ] **Step 3: Implement the guardrail pass**

In `api/services/day_layout.py`, add a guardrail function and apply it to every returned card list (standard, rest, active-recovery, tournament) just before each `return`. Centralize by wrapping the result:

```python
MAX_TAPPABLE = wev2.MAX_TAPPABLE_WINDOWS  # 6


def _apply_guardrails(cards: list) -> list:
    """Port of window_engine_v2 guardrails to the new card list, ORDER-PRESERVING:
      1. Floor: no card sort_time before 06:30.
      2. Cap: at most MAX_TAPPABLE tappable cards (drop from the end, keeping
         the event markers and the earliest windows). Event markers are never dropped.
    Dedup (15-min) is intentionally NOT applied here because the spec's card order
    is a deliberate scroll order; collisions are resolved by floor only.
    """
    floor = wev2.DISPLAY_FLOOR.strftime("%H:%M")
    for c in cards:
        if c["sort_time"] and c["sort_time"] < floor:
            c["sort_time"] = floor

    tappable_seen = 0
    kept = []
    for c in cards:
        if c["is_tappable"]:
            if tappable_seen >= MAX_TAPPABLE:
                continue
            tappable_seen += 1
        kept.append(c)
    return kept
```

Wrap every `return {"day_type": ..., "cards": cards}` in `build_day_layout` so cards pass through `_apply_guardrails`. The cleanest way: change each return to `return {"day_type": dt, "cards": _apply_guardrails(cards)}`. Apply to ALL four return points (rest, active-recovery, tournament, standard).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/day_layout.py tests/test_day_layout.py
git commit -m "feat: day_layout guardrails — 06:30 floor + tappable cap (order-preserving)"
```

---

## Task 10: Wire `day_layout` into `build_today_view` behind `DAY_LAYOUT_V2`

**Files:**
- Modify: `api/services/today_service.py`
- Test: `tests/test_day_layout_today_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_day_layout_today_integration.py`:

```python
import os
os.environ["DB_PATH"] = ":memory:"
import sqlite3
from datetime import datetime
from api.services.day_layout import build_day_layout, day_layout_v2_enabled


def test_flag_helper_reads_env(monkeypatch):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    assert day_layout_v2_enabled() is True
    monkeypatch.delenv("DAY_LAYOUT_V2", raising=False)
    assert day_layout_v2_enabled() is False


def test_to_template_windows_shape():
    # build_day_layout cards adapt to the {key,label,category,sort_time,...} shape
    from api.services.day_layout import cards_to_template_windows
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    tw = cards_to_template_windows(res["cards"])
    assert tw and all({"key", "label", "category", "sort_time"} <= set(w) for w in tw)
    # event marker maps to a nudge-only (non-tappable) window
    ev_win = next(w for w in tw if w["category"] == "event")
    assert ev_win["is_nudge_only"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py -v`
Expected: FAIL (`day_layout_v2_enabled` / `cards_to_template_windows` not defined)

- [ ] **Step 3: Implement the flag + adapter in `day_layout.py`**

Add to `api/services/day_layout.py`:

```python
import os


def day_layout_v2_enabled() -> bool:
    return os.environ.get("DAY_LAYOUT_V2", "false").lower() == "true"


# Map our card "card" kind → the existing template_windows "category" vocabulary
# build_today_view + fuel_gauge already understand. Event markers + keep_going
# become nudge-only (non-tappable) so they render but aren't confirmation taps...
# EXCEPT keep_going, which the spec shows as a real card (oz/packets) — keep it tappable.
_CARD_TO_CATEGORY = {
    "everyday_meal": "everyday", "breakfast": "everyday", "lunch": "everyday", "dinner": "everyday",
    "fuel_before": "fuel_before", "top_up": "quick_snack",
    "keep_going": "fuel_during", "event": "event",
    "recharge": "fuel_after", "rebuild": "fuel_after", "wind_down": "everyday",
}


def cards_to_template_windows(cards: list) -> list:
    """Adapt day_layout cards to the template_windows shape build_today_view consumes."""
    out = []
    for c in cards:
        category = _CARD_TO_CATEGORY.get(c["card"], "everyday")
        out.append({
            "key": c["key"],
            "label": c["label"],
            "category": category,
            "category_key": category,
            "macro_focus": "",
            "sort_time": c["sort_time"],
            "time_display": c.get("time_display", ""),
            "open_dt": None,
            "close_dt": None,
            "is_nudge_only": bool(c["is_event"]),   # event marker = visible, non-tappable
        })
    return out
```

- [ ] **Step 4: Wire into `build_today_view`**

In `api/services/today_service.py`, at the top of `build_today_view` (after `events` is loaded, before the `generate_windows_for_day` call at line ~959), branch on the flag:

```python
    from api.services.day_layout import (
        build_day_layout, cards_to_template_windows, day_layout_v2_enabled,
    )
    from datetime import datetime as _dt_now

    if day_layout_v2_enabled():
        _layout = build_day_layout(events, athlete, now=_dt_now.now())
        event_type       = _layout["day_type"]
        template_windows = cards_to_template_windows(_layout["cards"])
    else:
        engine_result    = generate_windows_for_day(athlete_id, today_str, events, force_v2=force_v2)
        event_type       = engine_result["day_type"]
        template_windows = engine_result["windows"]
```

(Replace the existing two-line `engine_result = ...; event_type = ...; template_windows = ...` block with the if/else above.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Confirm no regression with the flag OFF**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_today_service.py -q`
Expected: same pass/fail set as before this task (flag defaults off → legacy path unchanged). The 1 known pre-existing failure (`test_mission_items_iron_critical_for_girls`) may remain; no NEW failures.

- [ ] **Step 7: Commit**

```bash
git add api/services/day_layout.py api/services/today_service.py tests/test_day_layout_today_integration.py
git commit -m "feat: build_today_view uses day_layout behind DAY_LAYOUT_V2 flag (legacy fallback)"
```

---

## After all tasks

- [ ] Full suite: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/ -q` — confirm only the documented pre-existing failures remain (no new ones from this plan).
- [ ] Use **superpowers:finishing-a-development-branch**.
- [ ] **Plan B (mobile) is the next plan** — the activity-type one-tap selector (7 options + nudge + `PATCH /events/:id/activity-type`) and the Today-tab rendering of the new ordered cards (visible event marker, keep_going oz/packets card, recharge/rebuild, everyday placement, wind-down). It depends on this plan's `cards`/response shape, so author it after this lands.
- [ ] **Before enabling `DAY_LAYOUT_V2` in prod:** this replaces the live Today window source. Confirm the ported guardrails match product intent, and verify the `event`-marker + `keep_going` card render correctly in Plan B first.

---

## Self-Review

**Spec coverage:**
- Activity Type Selector storage + 7 keys → Tasks 3, 4 ✅
- 2-hour silent default → Task 2 ✅
- Today card order (morning/afternoon/rest/active-recovery) → Tasks 5, 6 ✅
- Tournament template (Section 6) → Tasks 1, 8 ✅
- Evening Wind-Down (>8pm) → Task 7 ✅
- Visible `event` marker (3b) → Tasks 6 (`is_event=True/is_tappable=False`), 10 (`is_nudge_only=True`) ✅
- Rest day 33/34/33 → Task 5 (breakfast/lunch/dinner; the 33/34/33 *gram* split is applied downstream by the existing everyday-split logic, not by ordering) ✅
- Replace window_engine_v2 for Today behind flag + guardrails → Tasks 9, 10 ✅

**Gap flagged, not silently dropped:** The 33/34/33 *numeric* split for rest days is a downstream gram concern (window_distribution/fuel_gauge), not an ordering concern — Task 5 emits the 3 meal cards; wiring the exact 33/34/33 across them is a one-line follow-up in the gram-split layer, noted here, not in this ordering plan. Also: `_apply_guardrails` deliberately omits the 15-min dedup (the spec's order is intentional) — documented in the code comment, a conscious deviation from window_engine_v2.

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step has complete code; every test step has real assertions.

**Type consistency:** Card dict shape (`key`/`card`/`label`/`is_event`/`is_tappable`/`sort_time`/`time_display`/`game_num`/`duration_min`) is identical across tournament_template (Task 1), day_layout (Tasks 5-9), and the adapter (Task 10). `resolve_activity_type(event, now)` signature consistent across Tasks 2, 5. `VALID_ACTIVITY_TYPES` defined in Task 2, reused in Task 4. `cards_to_template_windows`/`day_layout_v2_enabled`/`build_day_layout` names consistent across Tasks 5-10.
