# Meal Planner Day View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static weekly meal planner grid with a day-by-day timeline view whose meal slots are dynamically calculated from the athlete's schedule using a timing engine.

**Architecture:** A new `compute_meal_slots()` function in `api/services/meal_timing.py` replaces the static `SLOTS_BY_EVENT` dictionary — it reads the event's start time and duration, applies timing formulas, detects conflicts (early game, late event, double day), and returns an ordered list of slot objects with calculated "Eat by" times, nutrition tags, and icons. `_build_week()` in `meal_plans.py` calls this function. The frontend `MealPlannerScreen.jsx` is redesigned around three new components — `WeekDots`, `DayHero`, `TimelineSlot` — that render the day-view timeline layout with a colour-coded hero card and no Generate or Mark-as-Eaten buttons.

**Tech Stack:** Python (datetime), FastAPI, React (hooks, inline styles), SQLite.

---

## File Map

| File | Change |
|------|--------|
| `api/services/meal_timing.py` | Add `compute_meal_slots()` and helpers alongside existing functions |
| `api/routes/meal_plans.py` | Replace `SLOTS_BY_EVENT`/`SLOT_LABELS`/`SLOT_TO_CATEGORY` with `compute_meal_slots()`; update `_build_week()` to fetch all events and pass new fields |
| `tests/test_meal_timing.py` | New — unit tests for the timing engine |
| `frontend/src/MealPlannerScreen.jsx` | Full redesign: remove `DayColumn`/`weekGrid`/generate logic; add `WeekDots`, `DayHero`, `TimelineSlot`; add day navigation state |

---

### Task 1: `compute_meal_slots()` timing engine

**Files:**
- Modify: `api/services/meal_timing.py`
- Create: `tests/test_meal_timing.py`

- [ ] **Step 1: Create the test file**

```bash
mkdir -p tests && touch tests/__init__.py tests/test_meal_timing.py
```

- [ ] **Step 2: Write failing tests for the timing engine**

Write `tests/test_meal_timing.py`:

```python
import pytest
from api.services.meal_timing import compute_meal_slots


def slot_names(slots):
    return [s["slot_name"] for s in slots]


def slot_by_name(slots, name):
    return next((s for s in slots if s["slot_name"] == name), None)


# ── Rest day ──────────────────────────────────────────────────────────────────

def test_rest_day_returns_7_slots():
    slots = compute_meal_slots(None, None, None)
    assert len(slots) == 7


def test_rest_day_slot_names():
    slots = compute_meal_slots(None, None, None)
    assert slot_names(slots) == [
        "breakfast", "mid-morning-snack", "lunch", "afternoon-snack",
        "dinner", "evening-recovery", "daily-hydration",
    ]


def test_rest_day_no_performance_slots():
    slots = compute_meal_slots(None, None, None)
    names = slot_names(slots)
    assert "pre-training" not in names
    assert "power-snack" not in names
    assert "halftime-fueling" not in names


def test_rest_day_hydration_slot_is_informational():
    slots = compute_meal_slots(None, None, None)
    hyd = slot_by_name(slots, "daily-hydration")
    assert hyd["is_hydration"] is True
    assert hyd["recipe_category"] is None


# ── Training day (normal — 4:00 PM) ──────────────────────────────────────────

def test_training_pre_event_calculated():
    slots = compute_meal_slots("practice", "16:00", 1.5)
    pre = slot_by_name(slots, "pre-training")
    assert pre is not None
    assert pre["eat_by_time"] == "1:00 PM"


def test_training_power_snack_calculated():
    slots = compute_meal_slots("practice", "16:00", 1.5)
    snack = slot_by_name(slots, "power-snack")
    assert snack is not None
    assert snack["eat_by_time"] == "3:15 PM"


def test_training_recovery_fuel_calculated():
    # 4:00 PM + 1.5h = 5:30 PM end; recovery = 5:30 PM + 30min = 6:00 PM
    slots = compute_meal_slots("practice", "16:00", 1.5)
    recovery = slot_by_name(slots, "recovery-fuel")
    assert recovery is not None
    assert recovery["eat_by_time"] == "6:00 PM"


def test_training_separate_dinner_when_ends_before_19():
    slots = compute_meal_slots("practice", "16:00", 1.5)
    dinner = slot_by_name(slots, "dinner")
    assert dinner is not None
    recovery = slot_by_name(slots, "recovery-fuel")
    assert recovery is not None  # both present, not merged


# ── Late training (7:30 PM — ends 9:00 PM) ───────────────────────────────────

def test_late_training_merges_recovery_and_dinner():
    slots = compute_meal_slots("practice", "19:30", 1.5)
    assert slot_by_name(slots, "recovery-fuel") is None
    assert slot_by_name(slots, "night-fuel") is None
    merged = slot_by_name(slots, "recovery-dinner")
    assert merged is not None
    assert merged["is_merged"] is True


def test_late_training_merged_slot_has_correct_tags():
    slots = compute_meal_slots("practice", "19:30", 1.5)
    merged = slot_by_name(slots, "recovery-dinner")
    assert "High Protein" in merged["tags"]
    assert "Fast Carbs" in merged["tags"]


def test_late_training_has_note():
    slots = compute_meal_slots("practice", "19:30", 1.5)
    merged = slot_by_name(slots, "recovery-dinner")
    assert "recovery" in merged["note"].lower()


# ── Game day (normal — 2:00 PM) ───────────────────────────────────────────────

def test_game_has_halftime_slot():
    slots = compute_meal_slots("game", "14:00", 1.5)
    halftime = slot_by_name(slots, "halftime-fueling")
    assert halftime is not None
    assert halftime["eat_by_time"] == "2:45 PM"


def test_game_pre_game_fuel_calculated():
    slots = compute_meal_slots("game", "14:00", 1.5)
    pre = slot_by_name(slots, "pre-game-fuel")
    assert pre["eat_by_time"] == "11:00 AM"


# ── Early game (7:00 AM — pre-event at 4:00 AM) ──────────────────────────────

def test_early_game_removes_pre_game_fuel():
    slots = compute_meal_slots("game", "07:00", 1.5)
    assert slot_by_name(slots, "pre-game-fuel") is None


def test_early_game_keeps_power_snack():
    slots = compute_meal_slots("game", "07:00", 1.5)
    snack = slot_by_name(slots, "power-snack")
    assert snack is not None
    assert "Early" in snack["note"]


# ── Double day ────────────────────────────────────────────────────────────────

def test_double_day_adds_between_games_slot():
    slots = compute_meal_slots(
        "game", "10:00", 1.5,
        double_day=True, second_start_time="14:00"
    )
    between = slot_by_name(slots, "between-games")
    assert between is not None


def test_double_day_calorie_boost_flag():
    slots = compute_meal_slots(
        "game", "10:00", 1.5,
        double_day=True, second_start_time="14:00"
    )
    # First slot carries the double_day_alert flag
    assert any(s.get("double_day_alert") for s in slots)
```

- [ ] **Step 3: Run tests to confirm they all fail**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && pytest tests/test_meal_timing.py -v 2>&1 | head -40
```

Expected: all tests fail with `ImportError: cannot import name 'compute_meal_slots'`.

- [ ] **Step 4: Implement `compute_meal_slots()` in `api/services/meal_timing.py`**

Add the following to the bottom of `api/services/meal_timing.py` (keep all existing functions intact above):

```python
# ── compute_meal_slots ─────────────────────────────────────────────────────────

def _time_from_str(t: str) -> "datetime":
    return datetime.strptime(t, "%H:%M")


def _add(t: str, hours: float) -> str:
    """Return HH:MM 24h string offset by hours from t."""
    dt = _time_from_str(t) + timedelta(hours=hours)
    return dt.strftime("%H:%M")


def _fmt(t: str) -> str:
    """Format HH:MM 24h string as '4:30 PM'."""
    dt = _time_from_str(t)
    h = dt.hour % 12 or 12
    period = "AM" if dt.hour < 12 else "PM"
    if dt.minute == 0:
        return f"{h} {period}"
    return f"{h}:{dt.minute:02d} {period}"


def _hour(t: str) -> float:
    """Return hour as float (e.g. '19:30' → 19.5)."""
    dt = _time_from_str(t)
    return dt.hour + dt.minute / 60


_REST_SLOTS = [
    {"slot_name": "breakfast",        "display_label": "Breakfast",                          "eat_by_time": "8:30 AM",  "time_note": "Morning meal",            "tags": ["Complex Carbs", "Protein", "Healthy Fats"],    "icon": "🍳", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "practice",          "double_day_alert": False},
    {"slot_name": "mid-morning-snack","display_label": "Mid-Morning Snack",                   "eat_by_time": "11:00 AM", "time_note": "~10–11 AM",               "tags": ["Quick Carbs", "Light"],                        "icon": "🍎", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "pre-game-snack",    "double_day_alert": False},
    {"slot_name": "lunch",            "display_label": "Lunch",                              "eat_by_time": "1:30 PM",  "time_note": "Midday meal",             "tags": ["High Protein", "Complex Carbs", "Iron-Rich"],  "icon": "🥗", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "meal-prep",          "double_day_alert": False},
    {"slot_name": "afternoon-snack",  "display_label": "Afternoon Snack",                   "eat_by_time": "4:00 PM",  "time_note": "~2–4 PM",                 "tags": ["Protein", "Healthy Fats"],                    "icon": "🥜", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "pre-game-snack",    "double_day_alert": False},
    {"slot_name": "dinner",           "display_label": "Dinner",                            "eat_by_time": "7:00 PM",  "time_note": "Evening meal",            "tags": ["High Protein", "Complex Carbs", "Healthy Fats"],"icon": "🍽️","is_hydration": False, "is_merged": False, "note": "", "recipe_category": "practice",          "double_day_alert": False},
    {"slot_name": "evening-recovery", "display_label": "Evening Recovery / Pre-Bed Fueling","eat_by_time": "9:30 PM",  "time_note": "Before bed",              "tags": ["Casein Protein", "Light"],                    "icon": "🌙", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "post-game-recovery", "double_day_alert": False},
    {"slot_name": "daily-hydration",  "display_label": "Daily Hydration",                   "eat_by_time": "All day",  "time_note": "Water target for the day","tags": [],                                             "icon": "💧", "is_hydration": True,  "is_merged": False, "note": "", "recipe_category": None,               "double_day_alert": False},
]


def _make_slot(slot_name, display_label, eat_by_time, time_note, tags, icon,
               is_hydration=False, is_merged=False, note="",
               recipe_category=None, double_day_alert=False):
    return {
        "slot_name": slot_name, "display_label": display_label,
        "eat_by_time": eat_by_time, "time_note": time_note,
        "tags": tags, "icon": icon, "is_hydration": is_hydration,
        "is_merged": is_merged, "note": note,
        "recipe_category": recipe_category, "double_day_alert": double_day_alert,
    }


def compute_meal_slots(
    event_type: str | None,
    start_time: str | None,       # "HH:MM" 24h or None
    duration_hours: float | None, # e.g. 1.5
    double_day: bool = False,
    second_start_time: str | None = None,
) -> list[dict]:
    """
    Return ordered list of meal slot dicts for a given day.
    All slot dicts have keys: slot_name, display_label, eat_by_time, time_note,
    tags, icon, is_hydration, is_merged, note, recipe_category, double_day_alert.
    """
    import copy

    # Step 1: No event → Rest Day static template
    if not event_type or event_type.lower() == "rest":
        return [copy.copy(s) for s in _REST_SLOTS]

    norm = event_type.lower()
    is_game = "game" in norm or "tournament" in norm
    is_training = not is_game  # practice / training / strength

    # Guard: no start_time → fall back to rest
    if not start_time:
        return [copy.copy(s) for s in _REST_SLOTS]

    dur = duration_hours or 1.5
    event_end = _add(start_time, dur)

    # Step 2: Calculate timing formulas
    pre_event_time  = _add(start_time, -3.0)
    power_snack_time = _add(start_time, -0.75)
    halftime_time   = _add(start_time, 0.75)   # game only
    recovery_time   = _add(event_end,  0.5)

    # Step 3: Conflict checks
    is_early_event = _hour(pre_event_time) < 6.0
    is_late_event  = _hour(event_end) >= 19.0

    slots = []

    # ── Double-day alert banner slot ──────────────────────────────────────────
    if double_day:
        slots.append(_make_slot(
            "double-day-alert", "⚡ Double Event Day",
            "", "Two events today — +15% calories",
            [], "⚡", double_day_alert=True,
        ))

    # ── Fixed morning slots ───────────────────────────────────────────────────
    slots.append(_make_slot("breakfast", "Breakfast", "8:30 AM", "Morning meal",
        ["Complex Carbs", "Protein", "Healthy Fats"], "🍳", recipe_category="practice"))
    slots.append(_make_slot("mid-morning-snack", "Mid-Morning Snack", "11:00 AM", "~10–11 AM",
        ["Quick Carbs", "Light"], "🍎", recipe_category="pre-game-snack"))
    slots.append(_make_slot("lunch", "Lunch", "1:30 PM", "Midday meal",
        ["High Protein", "Complex Carbs", "Iron-Rich"], "🥗", recipe_category="meal-prep"))

    # ── Pre-event slots ───────────────────────────────────────────────────────
    if is_early_event:
        # Rule 1: Pre-event falls before 6 AM — remove it, keep power snack with note
        slots.append(_make_slot(
            "power-snack",
            "Power Snack",
            _fmt(power_snack_time),
            f"45 min before {'kick-off' if is_game else 'training'}",
            ["Quick Carbs"],
            "🍌",
            note="Early event — light snack only before kick-off",
            recipe_category="pre-game-snack",
        ))
    else:
        label = "Pre-Game Fuel" if is_game else "Pre-Training Fuel"
        note_str = "3 hrs before kick-off" if is_game else "3 hrs before training"
        slots.append(_make_slot(
            "pre-game-fuel" if is_game else "pre-training",
            label,
            _fmt(pre_event_time),
            note_str,
            ["Complex Carbs", "Light Protein"],
            "⚡",
            recipe_category="pre-game",
        ))
        slots.append(_make_slot(
            "power-snack",
            "Power Snack",
            _fmt(power_snack_time),
            f"45 min before {'kick-off' if is_game else 'training'}",
            ["Quick Carbs"],
            "🍌",
            recipe_category="pre-game-snack",
        ))

    # ── During event hydration ────────────────────────────────────────────────
    hydration_label = "During Game Hydration" if is_game else "During Practice Hydration"
    slots.append(_make_slot(
        "during-game-hydration" if is_game else "during-practice-hydration",
        hydration_label,
        f"{_fmt(start_time)} – {_fmt(event_end)}",
        "Electrolytes + fluids",
        ["Electrolytes", "Fluids"],
        "💦",
        is_hydration=True,
    ))

    # ── Halftime (game only) ──────────────────────────────────────────────────
    if is_game:
        slots.append(_make_slot(
            "halftime-fueling", "Halftime Fueling",
            _fmt(halftime_time), "At halftime",
            ["Quick Carbs", "Light"],
            "🍊", recipe_category="halftime",
        ))

    # ── Post-event: late event merges dinner + recovery + night fuel ──────────
    if is_late_event:
        # Rule 2: merge Recovery Fuel + Dinner + Night Fuel
        slots.append(_make_slot(
            "recovery-dinner",
            "Recovery Dinner",
            f"After {_fmt(event_end)}",
            "Post-event dinner = recovery meal",
            ["High Protein", "Complex Carbs", "Fast Carbs"],
            "🍽️🔋",
            is_merged=True,
            note="Post-event dinner doubles as your recovery meal tonight",
            recipe_category="post-game-recovery",
        ))
    else:
        slots.append(_make_slot(
            "recovery-fuel",
            "Recovery Fuel",
            _fmt(recovery_time),
            "Within 30 min after event",
            ["Protein", "Fast Carbs"],
            "🔋",
            recipe_category="post-game-recovery",
        ))
        slots.append(_make_slot(
            "dinner", "Dinner", "7:00 PM", "Evening meal",
            ["High Protein", "Complex Carbs", "Healthy Fats"],
            "🍽️", recipe_category="practice",
        ))
        slots.append(_make_slot(
            "night-fuel", "Night Fuel", "9:00 PM", "Before bed",
            ["Casein Protein", "Light"],
            "🌙", recipe_category="post-game-recovery",
        ))

    # ── Between-games slot (double day) ──────────────────────────────────────
    if double_day and second_start_time:
        between_time = f"After {_fmt(event_end)} – Before {_fmt(second_start_time)}"
        slots.append(_make_slot(
            "between-games",
            "Between Games Recovery + Refuel",
            between_time,
            "Recovery window between games",
            ["Protein", "Fast Carbs", "Electrolytes"],
            "🔄",
            is_merged=True,
            recipe_category="post-game-recovery",
        ))

    # ── Daily hydration (always last) ─────────────────────────────────────────
    slots.append(_make_slot(
        "daily-hydration", "Daily Hydration", "All day",
        "Water target for the day", [], "💧",
        is_hydration=True,
    ))

    return slots
```

- [ ] **Step 5: Run the tests**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && pytest tests/test_meal_timing.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add api/services/meal_timing.py tests/test_meal_timing.py tests/__init__.py
git commit -m "feat(meal-timing): add compute_meal_slots() dynamic timing engine"
```

---

### Task 2: Update `_build_week()` in `meal_plans.py`

**Files:**
- Modify: `api/routes/meal_plans.py:1-114`

- [ ] **Step 1: Replace static dicts and update `_build_week()`**

Open `api/routes/meal_plans.py`. Replace lines 1–114 with the following (keep everything from line 115 onwards unchanged):

```python
from fastapi import APIRouter, HTTPException, Query
from datetime import date, timedelta
from api.models import MealPlanSlotUpdate, MealPlanLogSlot, MealPlanGenerateRequest
from api.database import get_conn
from api.services import recipe_db, claude_ai
from api.routes.nutrition import get_targets
from api.services.meal_timing import compute_meal_slots

router = APIRouter()

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _get_monday(date_str: str) -> date:
    d = date.fromisoformat(date_str)
    return d - timedelta(days=d.weekday())


def _build_week(athlete_id: int, week_start: date, conn) -> list:
    days = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        date_str = day_date.isoformat()

        # Fetch ALL events for this day to detect double-day
        event_rows = conn.execute(
            "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time",
            (athlete_id, date_str),
        ).fetchall()
        events = [dict(r) for r in event_rows]

        event_type   = events[0]["event_type"] if events else "rest"
        event_name   = events[0]["event_name"] if events else None
        start_time   = events[0]["start_time"] if events else None
        duration_h   = events[0]["duration_hours"] if events else None
        double_day   = len(events) >= 2
        second_start = events[1]["start_time"] if double_day else None

        # Calorie target
        target_row = conn.execute(
            "SELECT total_calories FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
            (athlete_id, date_str),
        ).fetchone()
        calorie_target = dict(target_row)["total_calories"] if target_row else None

        # Filled slots from DB
        rows = conn.execute(
            "SELECT * FROM meal_plans WHERE athlete_id = ? AND plan_date = ?",
            (athlete_id, date_str),
        ).fetchall()
        filled = {dict(r)["slot_name"]: dict(r) for r in rows}

        # Compute dynamic slot list
        slot_defs = compute_meal_slots(
            event_type, start_time, duration_h,
            double_day=double_day, second_start_time=second_start,
        )

        slots = []
        planned_calories = 0
        for sd in slot_defs:
            sname = sd["slot_name"]
            f = filled.get(sname)
            slot = {
                "slot_name":       sname,
                "display_label":   sd["display_label"],
                "eat_by_time":     sd["eat_by_time"],
                "time_note":       sd["time_note"],
                "tags":            sd["tags"],
                "icon":            sd["icon"],
                "is_hydration":    sd["is_hydration"],
                "is_merged":       sd["is_merged"],
                "note":            sd["note"],
                "double_day_alert": sd.get("double_day_alert", False),
                "recipe_category": sd["recipe_category"],
                "recipe_id":       f["recipe_id"]   if f else None,
                "recipe_name":     f["recipe_name"] if f else None,
                "calories":        f["calories"]    if f else None,
                "carbs_g":         f["carbs_g"]     if f else None,
                "protein_g":       f["protein_g"]   if f else None,
                "fat_g":           f["fat_g"]       if f else None,
                "is_ai_generated": bool(f["is_ai_generated"]) if f else False,
                "logged":          bool(f["logged"]) if f else False,
            }
            if f and f["calories"]:
                planned_calories += f["calories"]
            slots.append(slot)

        days.append({
            "date":             date_str,
            "day_label":        DAY_LABELS[i],
            "event_type":       event_type,
            "event_name":       event_name,
            "calorie_target":   calorie_target,
            "planned_calories": round(planned_calories),
            "double_day":       double_day,
            "slots":            slots,
        })
    return days
```

- [ ] **Step 2: Verify the API still starts**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && python -c "from api.routes.meal_plans import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Test the API endpoint**

```bash
source venv/bin/activate && uvicorn api.main:app --port 8002 &
sleep 3 && curl -s "http://localhost:8002/api/meal-plans/1?week_start=2026-06-08" | python3 -c "
import json, sys
data = json.load(sys.stdin)
day = data['days'][1]  # Tuesday (practice day)
print('Event:', day['event_type'])
print('Slots:', [s['slot_name'] for s in day['slots']])
first = day['slots'][0]
print('First slot fields:', list(first.keys()))
" && kill $(lsof -ti:8002)
```

Expected output includes `eat_by_time`, `tags`, `icon`, `is_hydration` in the slot keys.

- [ ] **Step 4: Commit**

```bash
git add api/routes/meal_plans.py
git commit -m "feat(meal-plans): replace static SLOTS_BY_EVENT with dynamic compute_meal_slots()"
```

---

### Task 3: Frontend — constants, state, and navigation

**Files:**
- Modify: `frontend/src/MealPlannerScreen.jsx:1-36` (imports + top-level constants)
- Modify: `frontend/src/MealPlannerScreen.jsx:226-260` (MealPlannerScreen state + handlers)

- [ ] **Step 1: Replace the top of MealPlannerScreen.jsx**

Replace lines 1–12 (imports + `EVENT_COLORS`) with:

```jsx
import { useState, useEffect, useCallback } from "react";

const API = import.meta.env.VITE_API_URL ?? "";

const DAY_HERO = {
  rest:       { grad: ["#2d6a4f","#52b788"], emoji:"🌿", badge:"🌿 Rest Day",     title:"Recovery & Rebuild Day",           desc:"No training today — your body is repairing muscle and replenishing glycogen. Focus on protein to rebuild and complex carbs to restore energy stores. Prioritise iron-rich foods and calcium for bone health." },
  practice:   { grad: ["#b45309","#f59e0b"], emoji:"🏃", badge:"🏃 Training Day",  title:"Training Fuel Day",                desc:"Your body needs sustained energy before practice and fast recovery after. Load up on complex carbs at lunch and your pre-training meal, then hit the protein + carb recovery window right after finishing." },
  training:   { grad: ["#b45309","#f59e0b"], emoji:"🏃", badge:"🏃 Training Day",  title:"Training Fuel Day",                desc:"Your body needs sustained energy before practice and fast recovery after. Load up on complex carbs at lunch and your pre-training meal, then hit the protein + carb recovery window right after finishing." },
  strength:   { grad: ["#b45309","#f59e0b"], emoji:"🏋️", badge:"🏋️ Strength Day", title:"Training Fuel Day",                desc:"Your body needs sustained energy before practice and fast recovery after. Load up on complex carbs at lunch and your pre-training meal, then hit the protein + carb recovery window right after finishing." },
  game:       { grad: ["#9a1a1a","#e05a4a"], emoji:"⚽", badge:"⚽ Game Day",       title:"Game Day — Perform & Recover",     desc:"Today is all about peak performance and rapid recovery. Front-load carbs before kick-off, stay on top of hydration throughout, and hit your recovery window within 30 minutes of the final whistle." },
  tournament: { grad: ["#4a2a8a","#9a7ae8"], emoji:"🏆", badge:"🏆 Tournament",   title:"Tournament Day — Fuel to Compete", desc:"Multiple games means fuel management is critical. Prioritise carb availability all day, recover fast between games, and protect your muscles with quality protein at dinner." },
};

const TAG_COLORS = {
  "Complex Carbs":  { bg:"#fff8e7", color:"#b8720a", border:"#f4d3a0" },
  "Quick Carbs":    { bg:"#fff8e7", color:"#b8720a", border:"#f4d3a0" },
  "Fast Carbs":     { bg:"#fff8e7", color:"#b8720a", border:"#f4d3a0" },
  "Protein":        { bg:"#eff8ff", color:"#1a6ab8", border:"#b8d9f4" },
  "High Protein":   { bg:"#eff8ff", color:"#1a6ab8", border:"#b8d9f4" },
  "Light Protein":  { bg:"#eff8ff", color:"#1a6ab8", border:"#b8d9f4" },
  "Casein Protein": { bg:"#f5f0ff", color:"#5a3ab8", border:"#c8b0f4" },
  "Healthy Fats":   { bg:"#fdf5ff", color:"#7a3ab8", border:"#ddbef4" },
  "Light":          { bg:"#f4fdf7", color:"#2a7a4a", border:"#a8e4bc" },
  "Iron-Rich":      { bg:"#fff0f0", color:"#b83a3a", border:"#f4a8a8" },
  "Electrolytes":   { bg:"#e8f4ff", color:"#1a6aa8", border:"#a0cce8" },
  "Fluids":         { bg:"#e8f4ff", color:"#1a6aa8", border:"#a0cce8" },
};
```

- [ ] **Step 2: Update MealPlannerScreen state (remove generate/log, add selectedDate)**

Find the `export default function MealPlannerScreen` declaration (around line 226 after the edit above). Replace the entire state block and handler functions up to (but not including) the `return (`) with:

```jsx
export default function MealPlannerScreen({ athlete, onNavigate, freshImport = false, onFreshImportSeen }) {
  const todayISO = new Date().toISOString().split("T")[0];
  const [weekStart, setWeekStart]   = useState(getMondayOf(new Date()));
  const [selectedDate, setSelectedDate] = useState(todayISO);
  const [weekData, setWeekData]     = useState(null);
  const [allRecipes, setAllRecipes] = useState([]);
  const [activeSlot, setActiveSlot] = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState("");

  const athleteAllergens = (athlete.allergies || "").split(",").map(a => a.trim().toLowerCase()).filter(Boolean);

  useEffect(() => {
    fetch(`${API}/api/recipes/`)
      .then(r => r.json())
      .then(data => setAllRecipes(data.recipes || []))
      .catch(() => {});
  }, []);

  const loadWeek = useCallback(async () => {
    setLoading(true); setError("");
    const res = await fetch(`${API}/api/meal-plans/${athlete.id}?week_start=${toISO(weekStart)}`);
    if (res.ok) setWeekData(await res.json());
    else setError("Failed to load meal plan.");
    setLoading(false);
  }, [athlete.id, weekStart]);

  useEffect(() => { loadWeek(); }, [loadWeek]);

  function goToPrevDay() {
    const prev = addDays(new Date(selectedDate + "T12:00:00"), -1);
    const prevISO = toISO(prev);
    const monday = getMondayOf(prev);
    if (toISO(monday) !== toISO(weekStart)) setWeekStart(monday);
    setSelectedDate(prevISO);
    setActiveSlot(null);
  }

  function goToNextDay() {
    const next = addDays(new Date(selectedDate + "T12:00:00"), 1);
    const nextISO = toISO(next);
    const monday = getMondayOf(next);
    if (toISO(monday) !== toISO(weekStart)) setWeekStart(monday);
    setSelectedDate(nextISO);
    setActiveSlot(null);
  }

  async function handleAssign(date, slotName, recipe) {
    const res = await fetch(`${API}/api/meal-plans/${athlete.id}/slot`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_date: date, slot_name: slotName, recipe_id: recipe.id }),
    });
    if (res.ok) {
      const updated = await res.json();
      updateSlotInState(date, slotName, updated);
    }
  }

  function handleAutoSwap(date, slotName) {
    const day = weekData?.days.find(d => d.date === date);
    const slot = day?.slots.find(s => s.slot_name === slotName);
    if (!slot?.recipe_category) return;
    const safe = allRecipes.filter(r =>
      r.category === slot.recipe_category &&
      !athleteAllergens.some(a => r.allergens.map(x => x.toLowerCase()).includes(a))
    );
    const alts = safe.filter(r => r.id !== slot.recipe_id);
    if (!alts.length) return;
    handleAssign(date, slotName, alts[Math.floor(Math.random() * alts.length)]);
  }

  async function handleClear(date, slotName) {
    const res = await fetch(`${API}/api/meal-plans/${athlete.id}/slot?plan_date=${date}&slot_name=${slotName}`, { method: "DELETE" });
    if (res.ok) updateSlotInState(date, slotName, { recipe_id: null, recipe_name: null, calories: null, carbs_g: null, protein_g: null, fat_g: null, is_ai_generated: false, logged: false });
  }

  function updateSlotInState(date, slotName, patch) {
    setWeekData(prev => {
      if (!prev) return prev;
      const days = prev.days.map(day => {
        if (day.date !== date) return day;
        const slots = day.slots.map(s => s.slot_name === slotName ? { ...s, ...patch } : s);
        const planned = slots.reduce((sum, s) => sum + (s.calories || 0), 0);
        return { ...day, slots, planned_calories: Math.round(planned) };
      });
      return { ...prev, days };
    });
  }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/MealPlannerScreen.jsx
git commit -m "feat(meal-planner): add DAY_HERO constants, selectedDate state, day navigation"
```

---

### Task 4: Frontend — `WeekDots` component

**Files:**
- Modify: `frontend/src/MealPlannerScreen.jsx` — add `WeekDots` as a top-level component before `export default function MealPlannerScreen`

> **Note:** Place `WeekDots`, `DayHero`, and `TimelineSlot` (Tasks 4-6) as top-level functions **before** `export default function MealPlannerScreen`. The existing pattern (`RecipePicker` is top-level) must be followed — defining components inside a parent component causes React reconciliation issues.

- [ ] **Step 1: Add the `WeekDots` component**

Insert the following directly above `export default function MealPlannerScreen`:

```jsx
// ── WeekDots ────────────────────────────────────────────────────────────────
const EVENT_DOT_COLOR = { game:"#c04a3a", tournament:"#7e6ab5", practice:"#c8903a", training:"#c8903a", strength:"#4a8fc4", rest:"#8aa898" };

function WeekDots({ days, selectedDate, onSelect }) {
    return (
      <div style={wd.wrap}>
        {days.map(day => {
          const isActive  = day.date === selectedDate;
          const hasPlanned = day.slots.some(s => s.recipe_id);
          const evColor = EVENT_DOT_COLOR[day.event_type] || EVENT_DOT_COLOR.rest;
          const d = new Date(day.date + "T12:00:00").getDate();
          return (
            <div key={day.date} style={wd.col} onClick={() => onSelect(day.date)}>
              <div style={{ ...wd.dot, ...(isActive ? wd.dotActive : hasPlanned ? wd.dotPlanned : wd.dotEmpty) }}>
                {day.day_label[0]}
              </div>
              <div style={wd.dateNum}>{d}</div>
              <div style={{ ...wd.evDot, background: evColor }} />
            </div>
          );
        })}
      </div>
    );
  }
const wd = {
    wrap:       { display:"flex", justifyContent:"space-between", background:"#fff", padding:"10px 20px 12px", borderBottom:"1px solid #f0f4f1" },
    col:        { display:"flex", flexDirection:"column", alignItems:"center", gap:"3px", cursor:"pointer" },
    dot:        { width:"32px", height:"32px", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"12px", fontWeight:"800" },
    dotActive:  { background:"#2d6a4f", color:"#fff", boxShadow:"0 2px 8px rgba(45,106,79,0.30)" },
    dotPlanned: { background:"#d4ead8", color:"#2d6a4f" },
    dotEmpty:   { background:"#f0f4f1", color:"#8aa898" },
    dateNum:    { fontSize:"10px", color:"#8aa898", fontWeight:"700" },
    evDot:      { width:"5px", height:"5px", borderRadius:"50%" },
  };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/MealPlannerScreen.jsx
git commit -m "feat(meal-planner): add WeekDots component"
```

---

### Task 5: Frontend — `DayHero` component

**Files:**
- Modify: `frontend/src/MealPlannerScreen.jsx` — add `DayHero` as a top-level component after the `wd` styles object

- [ ] **Step 1: Add the `DayHero` component**

Insert directly after the `wd` styles object (still before `export default function MealPlannerScreen`):

```jsx
// ── DayHero ─────────────────────────────────────────────────────────────────
function DayHero({ day }) {
    const hero = DAY_HERO[day.event_type] || DAY_HERO.rest;
    const pct  = day.calorie_target ? Math.min(100, Math.round((day.planned_calories / day.calorie_target) * 100)) : 0;
    return (
      <div style={{ ...dh.card, background: `linear-gradient(135deg, ${hero.grad[0]}, ${hero.grad[1]})` }}>
        <div style={dh.bgEmoji}>{hero.emoji}</div>
        <div style={dh.badge}>{hero.badge}</div>
        <div style={dh.title}>{hero.title}</div>
        <div style={dh.desc}>{hero.desc}</div>
        {day.double_day && (
          <div style={dh.doubleDayAlert}>⚡ Double Event Day — +15% calorie target today</div>
        )}
        <div style={dh.calRow}>
          <div style={dh.calBarWrap}>
            <div style={dh.calTrack}>
              <div style={{ ...dh.calFill, width: `${pct}%` }} />
            </div>
          </div>
          <div style={dh.calLabel}>{day.planned_calories} / {day.calorie_target ?? "–"} kcal</div>
        </div>
      </div>
    );
  }
const dh = {
    card:        { margin:"14px 16px 0", borderRadius:"18px", padding:"18px 18px 16px", position:"relative", overflow:"hidden" },
    bgEmoji:     { position:"absolute", right:"-10px", top:"-10px", fontSize:"90px", opacity:"0.12", transform:"rotate(10deg)", userSelect:"none", lineHeight:1 },
    badge:       { display:"inline-flex", alignItems:"center", gap:"5px", background:"rgba(255,255,255,0.22)", border:"1px solid rgba(255,255,255,0.30)", padding:"3px 10px", borderRadius:"20px", fontSize:"12px", fontWeight:"700", color:"#fff", marginBottom:"8px" },
    title:       { fontSize:"18px", fontWeight:"900", color:"#fff", marginBottom:"6px", lineHeight:"1.2", fontFamily:"'Nunito', sans-serif" },
    desc:        { fontSize:"13px", color:"rgba(255,255,255,0.88)", lineHeight:"1.6" },
    doubleDayAlert: { marginTop:"8px", background:"rgba(255,255,255,0.20)", borderRadius:"8px", padding:"5px 10px", fontSize:"12px", fontWeight:"700", color:"#fff" },
    calRow:      { marginTop:"12px", background:"rgba(255,255,255,0.18)", borderRadius:"10px", padding:"8px 12px", display:"flex", alignItems:"center", gap:"10px" },
    calBarWrap:  { flex:1 },
    calTrack:    { height:"5px", background:"rgba(255,255,255,0.25)", borderRadius:"99px", overflow:"hidden" },
    calFill:     { height:"100%", background:"rgba(255,255,255,0.80)", borderRadius:"99px", transition:"width 0.4s ease" },
    calLabel:    { fontSize:"12px", color:"rgba(255,255,255,0.90)", fontWeight:"700", whiteSpace:"nowrap" },
  };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/MealPlannerScreen.jsx
git commit -m "feat(meal-planner): add DayHero component"
```

---

### Task 6: Frontend — `TimelineSlot` component (replaces `SlotCard` + `RecipePicker`)

**Files:**
- Modify: `frontend/src/MealPlannerScreen.jsx` — add `TimelineSlot` as a top-level component after the `dh` styles object

The existing `RecipePicker` component is kept unchanged — `TimelineSlot` embeds it the same way `SlotCard` did.

- [ ] **Step 1: Add `TimelineSlot` after the `dh` styles object**

Insert directly after `const dh = { … };` (still before `export default function MealPlannerScreen`):

```jsx
// ── TimelineSlot ──────────────────────────────────────────────────────────────
function TimelineSlot({ slot, date, allRecipes, athleteAllergens, isActive, isLast,
                          onOpenPicker, onClosePicker, onAssign, onAutoSwap, onClear }) {
    if (slot.double_day_alert) {
      return (
        <div style={ts.alertBanner}>
          <span style={ts.alertIcon}>⚡</span>
          <div>
            <div style={ts.alertTitle}>Double Event Day</div>
            <div style={ts.alertSub}>Two events today — calorie targets increased by 15%</div>
          </div>
        </div>
      );
    }

    const filled = !!slot.recipe_id;

    return (
      <div style={ts.wrap}>
        {/* Timeline line + dot */}
        <div style={ts.lineCol}>
          <div style={{ ...ts.dot, ...(slot.is_hydration ? ts.dotHydration : filled ? ts.dotFilled : ts.dotEmpty) }} />
          {!isLast && <div style={ts.line} />}
        </div>

        {/* Card */}
        <div style={ts.cardCol}>
          {/* Header: icon + name + time */}
          <div style={ts.cardHeader}>
            <div style={{ ...ts.iconWrap, ...(slot.is_hydration ? ts.iconWrapBlue : ts.iconWrapGreen) }}>
              {slot.icon}
            </div>
            <div style={ts.headerText}>
              <div style={ts.slotName}>{slot.display_label}</div>
              <div style={ts.eatBy}>
                {slot.is_hydration ? "💧" : "⏰"} {slot.eat_by_time}
                {slot.note ? <span style={ts.conflictNote}> · {slot.note}</span> : null}
              </div>
            </div>
          </div>

          {/* Nutrition tags */}
          {slot.tags.length > 0 && (
            <div style={ts.tags}>
              {slot.tags.map(tag => {
                const c = TAG_COLORS[tag] || { bg:"#f0f4f1", color:"#4a6358", border:"#dce8e0" };
                return <span key={tag} style={{ ...ts.tag, background:c.bg, color:c.color, borderColor:c.border }}>{tag}</span>;
              })}
            </div>
          )}

          {/* Hydration — informational only, no recipe */}
          {slot.is_hydration ? (
            <div style={ts.hydrationInfo}>
              Water target based on today's training load
            </div>
          ) : filled ? (
            /* Filled recipe card */
            <div style={{ ...ts.filledCard, ...(slot.is_merged ? ts.mergedCard : {}), ...(slot.is_ai_generated ? ts.aiCard : {}) }}>
              {slot.is_ai_generated && <div style={ts.aiBadge}>✨ AI</div>}
              <div style={ts.recipeName}>{slot.recipe_name}</div>
              <div style={ts.recipeCal}>{slot.calories} kcal</div>
              <div style={ts.actions}>
                <button style={ts.btnSwap} onClick={() => onAutoSwap(date, slot.slot_name)}>🔄 Swap</button>
                <button style={ts.btnClear} onClick={() => onClear(date, slot.slot_name)}>✕ Remove</button>
              </div>
            </div>
          ) : (
            /* Empty — Add button */
            <button style={ts.addBtn} onClick={() => onOpenPicker(date, slot.slot_name)}>
              ＋ {slot.is_merged ? "Add Recovery Dinner" : "Add Meal"}
            </button>
          )}

          {/* Recipe picker inline */}
          {isActive && (
            <RecipePicker
              slot={slot}
              allRecipes={allRecipes}
              athleteAllergens={athleteAllergens}
              onSelect={recipe => { onAssign(date, slot.slot_name, recipe); onClosePicker(); }}
              onClose={onClosePicker}
            />
          )}
        </div>
      </div>
    );
  }

const ts = {
    wrap:         { display:"flex", gap:"0", marginBottom:"0" },
    lineCol:      { display:"flex", flexDirection:"column", alignItems:"center", width:"24px", flexShrink:0, paddingTop:"8px" },
    dot:          { width:"12px", height:"12px", borderRadius:"50%", flexShrink:0, zIndex:1 },
    dotFilled:    { background:"#2d6a4f", border:"2px solid #2d6a4f" },
    dotEmpty:     { background:"#fff", border:"2px solid #2d6a4f" },
    dotHydration: { background:"#1a6ab8", border:"2px solid #1a6ab8" },
    line:         { width:"2px", flex:1, background:"linear-gradient(to bottom, #2d6a4f, #b0e8c8)", marginTop:"3px" },

    cardCol:      { flex:1, paddingBottom:"14px" },
    cardHeader:   { display:"flex", alignItems:"flex-start", gap:"10px", marginBottom:"8px" },
    iconWrap:     { width:"38px", height:"38px", borderRadius:"11px", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"19px", flexShrink:0 },
    iconWrapGreen:{ background:"#f0fdf4" },
    iconWrapBlue: { background:"#e8f4ff" },
    headerText:   { flex:1 },
    slotName:     { fontSize:"15px", fontWeight:"800", color:"#1b3a2a", lineHeight:"1.2", fontFamily:"'Nunito', sans-serif" },
    eatBy:        { fontSize:"12px", color:"#2d6a4f", fontWeight:"700", marginTop:"2px" },
    conflictNote: { color:"#b45309", fontWeight:"600" },

    tags:         { display:"flex", flexWrap:"wrap", gap:"5px", marginBottom:"10px" },
    tag:          { padding:"3px 9px", borderRadius:"20px", fontSize:"11px", fontWeight:"700", border:"1.5px solid" },

    hydrationInfo:{ fontSize:"12px", color:"#5a8ab8", fontStyle:"italic", padding:"6px 0" },

    filledCard:   { background:"#f4f8f5", border:"1.5px solid #e5e7eb", borderRadius:"10px", padding:"10px 12px" },
    mergedCard:   { background:"#f5f0ff", borderColor:"#dbbef4" },
    aiCard:       { background:"#f0fdf4", borderColor:"#b0e8c8" },
    aiBadge:      { fontSize:"10px", fontWeight:"800", color:"#2d6a4f", marginBottom:"2px" },
    recipeName:   { fontSize:"14px", fontWeight:"700", color:"#1b3a2a", marginBottom:"2px", lineHeight:"1.4" },
    recipeCal:    { fontSize:"13px", color:"#4a6358", marginBottom:"8px" },
    actions:      { display:"flex", gap:"6px" },
    btnSwap:      { background:"#f0f4f1", border:"none", borderRadius:"7px", padding:"6px 10px", fontSize:"13px", cursor:"pointer", color:"#4a6358", fontWeight:"600" },
    btnClear:     { background:"#fef2f2", border:"none", borderRadius:"7px", padding:"6px 10px", fontSize:"13px", cursor:"pointer", color:"#dc2626", fontWeight:"600" },

    addBtn:       { width:"100%", padding:"9px 12px", background:"#f0fdf4", border:"1.5px solid #2d6a4f", borderRadius:"9px", color:"#2d6a4f", fontSize:"14px", fontWeight:"700", cursor:"pointer" },

    alertBanner:  { display:"flex", alignItems:"center", gap:"10px", background:"#fffbeb", border:"1.5px solid #fde68a", borderRadius:"12px", padding:"10px 14px", marginBottom:"14px" },
    alertIcon:    { fontSize:"20px" },
    alertTitle:   { fontSize:"14px", fontWeight:"800", color:"#92400e" },
    alertSub:     { fontSize:"12px", color:"#b45309" },
  };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/MealPlannerScreen.jsx
git commit -m "feat(meal-planner): add TimelineSlot component"
```

---

### Task 7: Frontend — wire up the Day View layout

**Files:**
- Modify: `frontend/src/MealPlannerScreen.jsx` — replace the `return (` block of `MealPlannerScreen` and update the `s` styles object

- [ ] **Step 1: Replace the `return (` block of `MealPlannerScreen`**

Find the `return (` statement (starts with the import banner) and replace the entire return up to and including the closing `);` of the component with:

```jsx
  const selectedDay = weekData?.days.find(d => d.date === selectedDate) ?? null;
  const selectedDt  = new Date(selectedDate + "T12:00:00");

  return (
    <div>
      {freshImport && (
        <div style={s.importBanner}>
          <div style={s.importBannerInner}>
            <div style={s.importBannerText}>
              <div style={s.importBannerTitle}>🎉 Schedule loaded — meal slots are ready!</div>
              <div style={s.importBannerSub}>Tap each day to plan meals for that day.</div>
            </div>
            <button style={s.importBannerClose} onClick={onFreshImportSeen}>✕</button>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={s.headerRow}>
        <div>
          <h2 style={s.title}>🍳 Meal Planner</h2>
          <p style={s.subtitle}>{athlete.first_name}'s daily fueling plan</p>
        </div>
        {/* Day | Week toggle — Week greyed out */}
        <div style={s.toggleWrap}>
          <div style={s.toggleActive}>Day</div>
          <div style={s.toggleDisabled} title="Coming soon">Week</div>
        </div>
      </div>

      {error && <div style={s.errorBox}>{error}</div>}

      {loading ? (
        <div style={s.loadingMsg}>Loading plan…</div>
      ) : weekData ? (
        <>
          {/* Week dot strip */}
          <WeekDots
            days={weekData.days}
            selectedDate={selectedDate}
            onSelect={date => { setSelectedDate(date); setActiveSlot(null); }}
          />

          {/* Day navigator */}
          <div style={s.dayNav}>
            <button style={s.dayNavBtn} onClick={goToPrevDay}>‹</button>
            <div style={s.dayNavCenter}>
              <div style={s.dayNavDow}>
                {selectedDt.toLocaleDateString("en-US", { weekday:"long" }).toUpperCase()}
              </div>
              <div style={s.dayNavDate}>{selectedDt.getDate()}</div>
              <div style={s.dayNavMonth}>
                {selectedDt.toLocaleDateString("en-US", { month:"long", year:"numeric" })}
              </div>
            </div>
            <button style={s.dayNavBtn} onClick={goToNextDay}>›</button>
          </div>

          {selectedDay ? (
            <>
              {/* Hero card */}
              <DayHero day={selectedDay} />

              {/* Timeline */}
              <div style={s.timeline}>
                {selectedDay.slots.map((slot, idx) => (
                  <TimelineSlot
                    key={slot.slot_name}
                    slot={slot}
                    date={selectedDay.date}
                    allRecipes={allRecipes}
                    athleteAllergens={athleteAllergens}
                    isActive={activeSlot?.date === selectedDay.date && activeSlot?.slot === slot.slot_name}
                    isLast={idx === selectedDay.slots.length - 1}
                    onOpenPicker={(date, slotName) => setActiveSlot({ date, slot: slotName })}
                    onClosePicker={() => setActiveSlot(null)}
                    onAssign={handleAssign}
                    onAutoSwap={handleAutoSwap}
                    onClear={handleClear}
                  />
                ))}
              </div>
            </>
          ) : (
            <div style={s.loadingMsg}>Select a day above.</div>
          )}
        </>
      ) : null}

      <p style={s.disclaimer}>
        Meal plans are suggestions based on event type and nutrition targets.
        AthFuelPath provides educational food guidance — not medical nutrition therapy.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Replace the `s` styles object**

Remove the old `const s = { … }` block entirely and replace with:

```jsx
const s = {
  importBanner:      { margin:"0 0 16px", borderRadius:"14px", background:"linear-gradient(135deg, #0f4c35, #1a7a54)", padding:"1px" },
  importBannerInner: { display:"flex", alignItems:"center", justifyContent:"space-between", gap:"12px", background:"linear-gradient(135deg, #0f4c35, #1a7a54)", borderRadius:"13px", padding:"16px 18px" },
  importBannerText:  { flex:1 },
  importBannerTitle: { fontSize:"17px", fontWeight:"700", color:"#fff", marginBottom:"3px" },
  importBannerSub:   { fontSize:"15px", color:"#b7e4c7", lineHeight:"1.6" },
  importBannerClose: { background:"rgba(255,255,255,0.15)", border:"none", color:"#fff", borderRadius:"50%", width:"28px", height:"28px", cursor:"pointer", fontSize:"15px", flexShrink:0 },

  headerRow:    { display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:"0" },
  title:        { fontSize:"20px", fontWeight:"700", color:"#1b3a2a", margin:"0 0 2px" },
  subtitle:     { fontSize:"14px", color:"#4a6358", margin:"0 0 12px" },

  toggleWrap:    { display:"flex", background:"#f0f4f1", borderRadius:"10px", padding:"3px", gap:"2px", flexShrink:0 },
  toggleActive:  { padding:"5px 14px", borderRadius:"7px", background:"#2d6a4f", color:"#fff", fontSize:"13px", fontWeight:"700", boxShadow:"0 1px 4px rgba(45,106,79,0.25)" },
  toggleDisabled:{ padding:"5px 14px", borderRadius:"7px", color:"#c0c0c0", fontSize:"13px", fontWeight:"700", cursor:"not-allowed" },

  errorBox:     { background:"#fef2f2", border:"1.5px solid #fecaca", borderRadius:"8px", padding:"10px 14px", fontSize:"15px", color:"#dc2626", marginBottom:"12px" },
  loadingMsg:   { textAlign:"center", color:"#4a6358", padding:"40px 0", fontSize:"16px" },

  dayNav:       { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 20px 0" },
  dayNavBtn:    { width:"38px", height:"38px", background:"#fff", border:"1.5px solid #dce8e0", borderRadius:"10px", fontSize:"20px", fontWeight:"700", color:"#4a6358", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" },
  dayNavCenter: { textAlign:"center" },
  dayNavDow:    { fontSize:"12px", color:"#8aa898", fontWeight:"700", letterSpacing:"0.08em" },
  dayNavDate:   { fontSize:"28px", fontWeight:"900", color:"#1b3a2a", lineHeight:"1.1", fontFamily:"'Nunito', sans-serif" },
  dayNavMonth:  { fontSize:"13px", color:"#6b8f7e", marginTop:"1px" },

  timeline:     { padding:"16px 16px 8px", display:"flex", flexDirection:"column" },

  disclaimer:   { fontSize:"13px", color:"#8aa898", textAlign:"center", marginTop:"16px", lineHeight:"1.6", padding:"0 8px 16px" },
};
```

- [ ] **Step 3: Remove the old `CalorieSummaryBar`, `SlotCard`, `DayColumn` components and their styles**

Find and delete the following entire blocks from the file (they are now replaced by the new components):
- The `CalorieSummaryBar` function and `csb` styles object
- The `SlotCard` function and `sc` styles object
- The `DayColumn` function and `dc` styles object

- [ ] **Step 4: Commit**

```bash
git add frontend/src/MealPlannerScreen.jsx
git commit -m "feat(meal-planner): wire up Day View timeline layout with WeekDots, DayHero, TimelineSlot"
```

---

### Task 8: Manual verification

**Files:** None — read-only verification

- [ ] **Step 1: Start both servers**

Terminal 1:
```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && python db/setup.py && uvicorn api.main:app --reload --port 8000
```

Terminal 2:
```bash
cd /Users/mayurkhera/AthFuelPath/frontend && npm run dev
```

- [ ] **Step 2: Verify the API timing output**

```bash
curl -s "http://localhost:8000/api/meal-plans/1?week_start=2026-06-08" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for day in data['days']:
    print(f\"{day['day_label']} {day['date']} [{day['event_type']}]\")
    for s in day['slots']:
        print(f\"  {s['slot_name']:30} eat_by={s['eat_by_time']:12} hydration={s['is_hydration']}\")
"
```

Expected: each day shows different slot names and eat_by times based on its event type.

- [ ] **Step 3: Verify Day View in browser**

Open the app. Navigate to Meal Planner. Confirm:
- Day View is shown by default for today
- Hero card appears with correct colour and educational description
- 7-dot week strip is visible; active dot is today
- Slots appear as a vertical timeline with time labels
- ‹ › arrows move day by day; crossing week boundary reloads data
- "Week" toggle is greyed out and non-interactive
- No "Generate" button visible
- No "Mark as Eaten" button visible

- [ ] **Step 4: Verify Add flow**

Tap "＋ Add Meal" on any food slot. Confirm the recipe picker opens. Select a recipe. Confirm it appears in the slot with name + kcal. Confirm "🔄 Swap" and "✕ Remove" appear. Tap Remove. Confirm slot returns to empty state.

- [ ] **Step 5: Verify a training day**

Navigate to a day with a practice event. Confirm:
- Hero card is amber gradient with "Training Fuel Day" title
- Pre-Training Fuel slot shows "Eat by [event_start − 3h]" with the correct calculated time
- Power Snack shows "Eat by [event_start − 45min]"
- During Practice Hydration slot is blue/informational with no Add button

- [ ] **Step 6: Commit any fixes**

```bash
git add frontend/src/MealPlannerScreen.jsx api/services/meal_timing.py api/routes/meal_plans.py
git commit -m "fix(meal-planner): address issues found during manual verification"
```

Only run this step if fixes were needed in Steps 2–5.
