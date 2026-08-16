# Today Screen v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Today screen as a sports-broadcast briefing with a Broadcast Card (Zone A), Daily Mission checklist (Zone B), Science Edge rotating cards (Zone C), and Quick Row — replacing all current Today components.

**Architecture:** Python adds `calculate_performance_forecast()` and `get_mission_items()` to `today_service.py`, both exposed through the existing `/api/athletes/{id}/daily-summary` endpoint. React replaces 9 old components with 6 new focused components wired into a rewritten `Today.jsx` page shell. All numbers are calculated by Python — never on the client.

**Tech Stack:** Python 3.12, FastAPI, pytest, React 18 (hooks, inline styles), Nunito + DM Sans fonts, existing AthFuelPath green palette (#2d6a4f, #1b3a2a, #52b788).

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `api/services/today_service.py` | Add `calculate_performance_forecast()` and `get_mission_items()` |
| Modify | `api/routes/today.py` | Add `performance_forecast` and `mission_items` to `/daily-summary` response; expose full athlete fields |
| Create | `tests/test_today_service.py` | Unit tests for both new service functions |
| Create | `frontend/src/components/today/BroadcastCard.jsx` | Zone A: LiveTicker + AthleteIdentity + PerformanceTagline + StatsRow |
| Create | `frontend/src/components/today/PerformanceForecast.jsx` | 4 animated metric bars |
| Create | `frontend/src/components/today/DailyMission.jsx` | Zone B: mission header + 5 MissionItem rows |
| Create | `frontend/src/components/today/MissionItem.jsx` | Single checklist row with state-coded checkbox |
| Create | `frontend/src/components/today/ScienceEdge.jsx` | Zone C: rotating 3-card science panel |
| Create | `frontend/src/components/today/QuickRow.jsx` | HydrationMini + CaloriesQuick side by side |
| Create | `frontend/src/components/today/Toast.jsx` | Fixed toast notification (shared within Today) |
| Modify | `frontend/src/pages/Today.jsx` | Rewire to new component tree |
| Delete | `frontend/src/components/today/Greeting.jsx` | Replaced by BroadcastCard |
| Delete | `frontend/src/components/today/CountdownHero.jsx` | Replaced by BroadcastCard |
| Delete | `frontend/src/components/today/FuelScoreCard.jsx` | Replaced by BroadcastCard StatsRow |
| Delete | `frontend/src/components/today/StreakCard.jsx` | Removed from v3 |
| Delete | `frontend/src/components/today/WeekBarChart.jsx` | Removed from v3 |
| Delete | `frontend/src/components/today/NutrientsReportCard.jsx` | Replaced by DailyMission + ScienceEdge |
| Delete | `frontend/src/components/today/TomorrowAlert.jsx` | Absorbed into DailyMission |
| Delete | `frontend/src/components/today/NextMealsStrip.jsx` | Replaced by DailyMission |
| Delete | `frontend/src/components/today/HydrationTracker.jsx` | Replaced by QuickRow HydrationMini |

---

## Task 1: `calculate_performance_forecast()` in today_service.py

**Files:**
- Modify: `api/services/today_service.py`
- Create: `tests/test_today_service.py`

- [ ] **Step 1: Create test file**

```bash
touch tests/test_today_service.py
```

- [ ] **Step 2: Write failing tests**

Write `tests/test_today_service.py`:

```python
import pytest
from api.services.today_service import calculate_performance_forecast, get_mission_items


def make_tl(calories=80, carbs=80, protein=80, iron=80, calcium=80, water=80):
    """Build a minimal traffic_light dict for testing."""
    def cell(pct):
        return {"pct_met": pct, "logged": 0, "target": 100, "gap": max(0, 100 - pct), "status": "met" if pct >= 80 else "low" if pct >= 50 else "critical"}
    return {
        "calories":   cell(calories),
        "carbs_g":    cell(carbs),
        "protein_g":  cell(protein),
        "iron_mg":    cell(iron),
        "calcium_mg": cell(calcium),
        "water_oz":   cell(water),
        "daily_fuel_score": 75,
    }


# ── calculate_performance_forecast ───────────────────────────────────────────

def test_forecast_returns_four_keys():
    result = calculate_performance_forecast(make_tl())
    assert set(result.keys()) == {"sprint_capacity", "energy_reserves", "second_half_power", "mental_focus"}


def test_forecast_all_100_gives_100():
    result = calculate_performance_forecast(make_tl(100, 100, 100, 100, 100, 100))
    assert result["sprint_capacity"] == 100
    assert result["energy_reserves"] == 100
    assert result["second_half_power"] == 100
    assert result["mental_focus"] == 100


def test_forecast_all_zero_gives_zero():
    result = calculate_performance_forecast(make_tl(0, 0, 0, 0, 0, 0))
    assert result["sprint_capacity"] == 0
    assert result["energy_reserves"] == 0
    assert result["second_half_power"] == 0
    assert result["mental_focus"] == 0


def test_forecast_sprint_capacity_formula():
    # carbs=100, iron=0, protein=0 → 100*0.40 + 0*0.35 + 0*0.25 = 40
    result = calculate_performance_forecast(make_tl(calories=0, carbs=100, protein=0, iron=0, water=0))
    assert result["sprint_capacity"] == 40


def test_forecast_energy_reserves_formula():
    # calories=100, carbs=0 → 100*0.60 + 0*0.40 = 60
    result = calculate_performance_forecast(make_tl(calories=100, carbs=0, protein=0, iron=0, water=0))
    assert result["energy_reserves"] == 60


def test_forecast_second_half_power_formula():
    # iron=100, carbs=0, water=0 → 100*0.50 = 50
    result = calculate_performance_forecast(make_tl(calories=0, carbs=0, protein=0, iron=100, water=0))
    assert result["second_half_power"] == 50


def test_forecast_mental_focus_formula():
    # calories=0, water=100, protein=0 → 100*0.35 = 35
    result = calculate_performance_forecast(make_tl(calories=0, carbs=0, protein=0, iron=0, water=100))
    assert result["mental_focus"] == 35


def test_forecast_caps_at_100():
    # Each pct_met is capped at 100 before weighting
    tl = make_tl(100, 100, 100, 100, 100, 100)
    for k in tl:
        if isinstance(tl[k], dict):
            tl[k]["pct_met"] = 150  # simulate over-logging
    result = calculate_performance_forecast(tl)
    assert result["sprint_capacity"] == 100
    assert result["energy_reserves"] == 100
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && pytest tests/test_today_service.py::test_forecast_returns_four_keys -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'calculate_performance_forecast'`

- [ ] **Step 4: Implement `calculate_performance_forecast()` in today_service.py**

Add at the end of `api/services/today_service.py`:

```python


def calculate_performance_forecast(traffic_light: dict) -> dict:
    """Derives 4 performance metrics from nutrition traffic light. Pure math."""
    def pct(key): return min(traffic_light.get(key, {}).get("pct_met", 0), 100)

    return {
        "sprint_capacity":   round(pct("carbs_g")   * 0.40 + pct("iron_mg")   * 0.35 + pct("protein_g") * 0.25),
        "energy_reserves":   round(pct("calories")  * 0.60 + pct("carbs_g")   * 0.40),
        "second_half_power": round(pct("iron_mg")   * 0.50 + pct("carbs_g")   * 0.30 + pct("water_oz")  * 0.20),
        "mental_focus":      round(pct("calories")  * 0.40 + pct("water_oz")  * 0.35 + pct("protein_g") * 0.25),
    }
```

- [ ] **Step 5: Run tests**

```bash
source venv/bin/activate && pytest tests/test_today_service.py -k "forecast" -v 2>&1 | tail -15
```

Expected: all 8 forecast tests PASS.

- [ ] **Step 6: Commit**

```bash
git add api/services/today_service.py tests/test_today_service.py
git commit -m "feat(today): add calculate_performance_forecast() with tests"
```

---

## Task 2: `get_mission_items()` in today_service.py

**Files:**
- Modify: `api/services/today_service.py`
- Modify: `tests/test_today_service.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_today_service.py`:

```python
# ── get_mission_items ─────────────────────────────────────────────────────────

def test_mission_items_always_returns_5():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    assert len(items) == 5


def test_mission_items_all_have_required_keys():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    for item in items:
        assert "label" in item
        assert "sub" in item
        assert "time" in item
        assert "state" in item
        assert "tag" in item
        assert "item_type" in item


def test_mission_items_state_values_are_valid():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    valid_states = {"done", "urgent", "critical", "pending"}
    for item in items:
        assert item["state"] in valid_states, f"Invalid state: {item['state']}"


def test_mission_items_tag_values_are_valid():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    valid_tags = {"DONE", "NOW", "FIX THIS", "UPCOMING"}
    for item in items:
        assert item["tag"] in valid_tags, f"Invalid tag: {item['tag']}"


def test_mission_items_rest_day():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "iron_lunch" in types
    assert "calcium" in types
    assert "hydration" in types


def test_mission_items_game_day_has_pregame_snack():
    events = [{"start_time": "14:00", "duration_hours": 1.5, "event_type": "game"}]
    items = get_mission_items("game", events, make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "pregame_snack" in types


def test_mission_items_game_day_has_recovery():
    events = [{"start_time": "14:00", "duration_hours": 1.5, "event_type": "game"}]
    items = get_mission_items("game", events, make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "recovery" in types


def test_mission_items_iron_critical_for_girls():
    tl = make_tl(iron=30)
    items = get_mission_items("rest", [], tl, [], {}, 0, "girl")
    iron_items = [i for i in items if i["item_type"] == "iron_lunch"]
    assert len(iron_items) >= 1
    assert iron_items[0]["state"] == "critical"


def test_mission_items_iron_not_flagged_for_boys():
    tl = make_tl(iron=30)
    items = get_mission_items("rest", [], tl, [], {}, 0, "boy")
    iron_items = [i for i in items if i.get("state") == "critical"]
    # boys don't get critical iron state
    assert all(i["item_type"] != "iron_lunch" for i in iron_items)


def test_mission_items_hydration_urgent_when_low():
    tl = make_tl(water=30)
    items = get_mission_items("rest", [], tl, [], {"hydration_oz_min": 80}, 1, "girl")
    hydration = next(i for i in items if i["item_type"] == "hydration")
    assert hydration["state"] in ("urgent", "critical")


def test_mission_items_practice_day():
    events = [{"start_time": "16:00", "duration_hours": 1.5, "event_type": "practice"}]
    items = get_mission_items("practice", events, make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "pre_practice_snack" in types
    assert "protein_recovery" in types
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_today_service.py -k "mission" -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'get_mission_items'`

- [ ] **Step 3: Implement `get_mission_items()` in today_service.py**

Add after `calculate_performance_forecast()` in `api/services/today_service.py`:

```python


def _fmt_time(time_str: str, offset_hours: float = 0) -> str:
    """'14:30' + 0.5 → '3:00 PM'"""
    if not time_str:
        return ""
    try:
        h, m = map(int, time_str.split(":"))
        base = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
        dt = base + timedelta(hours=offset_hours)
        hour = dt.hour % 12 or 12
        period = "AM" if dt.hour < 12 else "PM"
        minute_str = f":{dt.minute:02d}" if dt.minute else ""
        return f"{hour}{minute_str} {period}"
    except Exception:
        return ""


def _has_log_type(meal_logs: list, keywords: list) -> bool:
    for m in meal_logs:
        desc = (m.get("description") or "").lower()
        if any(kw.lower() in desc for kw in keywords):
            return True
    return False


def get_mission_items(
    event_type: str,
    events: list,
    traffic_light: dict,
    meal_logs: list,
    targets: dict,
    water_cups: int,
    gender: str,
) -> list:
    """
    Returns exactly 5 mission items for today.
    Each item: {label, sub, time, state, tag, item_type}
    state: "done" | "urgent" | "critical" | "pending"
    tag:   "DONE" | "NOW" | "FIX THIS" | "UPCOMING"
    """
    now = datetime.now()
    is_female = gender.lower() in ("girl", "female")
    iron_pct = traffic_light.get("iron_mg", {}).get("pct_met", 100)
    iron_gap = round(traffic_light.get("iron_mg", {}).get("gap", 0), 1)
    water_pct = traffic_light.get("water_oz", {}).get("pct_met", 100)
    target_cups = max(1, round((targets.get("hydration_oz_min") or 64) / 8))
    cups_remaining = max(0, target_cups - (water_cups or 0))

    event = events[0] if events else None
    start = event.get("start_time") if event else None
    dur = (event.get("duration_hours") or 1.5) if event else 1.5

    def mins_to_start():
        if not start:
            return None
        try:
            h, m = map(int, start.split(":"))
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
            return round((t - now).total_seconds() / 60)
        except Exception:
            return None

    def _item(item_type, label, sub, time, state):
        tag = {"done": "DONE", "urgent": "NOW", "critical": "FIX THIS", "pending": "UPCOMING"}[state]
        return {"label": label, "sub": sub, "time": time, "state": state, "tag": tag, "item_type": item_type}

    # ── Iron item (shared across event types for girls) ───────────────────────
    def iron_item():
        if is_female and iron_pct < 50:
            return _item("iron_lunch", "Close the iron gap at lunch",
                         f"Add lean beef or lentils · <em>{iron_gap}mg needed</em>",
                         "1:00 PM", "critical")
        return _item("iron_lunch", "Iron-rich lunch today",
                     "Lentils, lean beef, or fortified cereal", "1:00 PM", "pending")

    # ── Hydration item (shared) ───────────────────────────────────────────────
    def hydration_item():
        cups_done = water_cups or 0
        state = "urgent" if water_pct < 40 else "pending"
        return _item("hydration",
                     f"Drink {cups_remaining} more cup{'s' if cups_remaining != 1 else ''} of water",
                     f"<em>{cups_done}</em> of {target_cups} cups done · {cups_done * 8}oz logged",
                     "All day", state)

    norm = (event_type or "rest").lower()

    # ── GAME DAY ─────────────────────────────────────────────────────────────
    if norm in ("game", "tournament"):
        mins = mins_to_start()
        breakfast_done = _has_log_type(meal_logs, ["breakfast", "oatmeal", "eggs", "pancake", "toast"])
        snack_done = _has_log_type(meal_logs, ["snack", "banana", "pre-game snack"])

        item1_state = "done" if breakfast_done or (mins is not None and mins < 150) else "pending"
        item2_state = "done" if snack_done else ("urgent" if mins is not None and 10 <= mins <= 90 else "pending")
        recovery_time = _fmt_time(start, dur + 0.5) if start else "After game"
        snack_time = _fmt_time(start, -0.75) if start else "45 min before"

        return [
            _item("pregame_breakfast", "Pre-game breakfast logged",
                  "High-carb meal 2.5–4 hrs before kickoff",
                  _fmt_time(start, -3) if start else "Morning", item1_state),
            _item("pregame_snack", "Eat your pre-game snack NOW" if item2_state == "urgent" else "Pre-game snack",
                  f"Banana + PB · Window closes in <em>{max(1, (mins or 45) - 10)} min</em>" if item2_state == "urgent" else "Banana + PB or rice cakes",
                  snack_time, item2_state),
            iron_item(),
            _item("recovery", "Hit recovery window after the game",
                  "Chocolate milk + banana · <em>30-min window</em>",
                  recovery_time, "pending"),
            hydration_item(),
        ]

    # ── PRACTICE / TRAINING / STRENGTH DAY ───────────────────────────────────
    if norm in ("practice", "training", "strength"):
        mins = mins_to_start()
        recovery_time = _fmt_time(start, dur + 0.5) if start else "After training"
        snack_time = _fmt_time(start, -0.75) if start else "45 min before"
        pre_time = _fmt_time(start, -2.0) if start else "2 hrs before"

        if norm == "strength":
            return [
                _item("pre_strength_meal", "Pre-strength meal 2hrs before training",
                      "Rice + chicken or oatmeal + eggs · complex carbs + protein",
                      pre_time, "pending"),
                _item("pre_practice_snack", "Fast carb snack 30 min before",
                      "Banana or rice cakes · <em>fast glucose</em>",
                      _fmt_time(start, -0.5) if start else "30 min before", "pending"),
                _item("protein_recovery", "CRITICAL: Protein recovery within 30 min",
                      "Chocolate milk or Greek yogurt + banana · <em>30-min window</em>",
                      recovery_time, "critical"),
                _item("casein_snack", "Bedtime casein snack tonight",
                      "Cottage cheese or Greek yogurt · <em>overnight muscle repair</em>",
                      "9:30 PM", "pending"),
                hydration_item(),
            ]

        return [
            _item("pre_practice_lunch", "Eat your pre-practice lunch by noon",
                  "High-carb lunch · rice, pasta, or sweet potato",
                  "12:00 PM", "pending"),
            _item("pre_practice_snack", f"Pre-practice snack {round((mins or 45))} min before training" if mins and mins > 0 else "Pre-practice snack",
                  "Banana + PB or toast + honey · <em>fast carbs</em>",
                  snack_time, "pending"),
            _item("protein_recovery", "Protein recovery within 30 min of whistle",
                  "Chocolate milk + banana · <em>30-min window</em>",
                  recovery_time, "pending"),
            iron_item(),
            hydration_item(),
        ]

    # ── PRE-GAME DAY ──────────────────────────────────────────────────────────
    if norm == "pregame_day":
        return [
            _item("hc_breakfast", "High-carb breakfast this morning",
                  "Oatmeal + banana + OJ · carb loading starts now",
                  "8:00 AM", "pending"),
            _item("pasta_lunch", "Big pasta or rice lunch — carb load begins",
                  "Pasta + tomato sauce + chicken · <em>high carbs, low fat</em>",
                  "12:00 PM", "pending"),
            _item("afternoon_snack", "Afternoon snack — keep carbs high all day",
                  "Toast + honey or rice cakes · no heavy protein",
                  "3:00 PM", "pending"),
            _item("pregame_dinner", "MOST IMPORTANT: Pre-game dinner tonight",
                  "Pasta + lean protein · <em>biggest carb meal of the week</em>",
                  "6:30 PM", "critical"),
            _item("low_fiber", "Limit fiber and fat today",
                  "Easy digestion for tomorrow · no salads or heavy sauces",
                  "All day", "pending"),
        ]

    # ── REST / RECOVERY DAY (default) ─────────────────────────────────────────
    return [
        _item("active_recovery", "Active recovery nutrition — don't undereat",
              "Rest days need 80%+ of normal calories to repair muscle",
              "All day", "pending"),
        iron_item(),
        _item("calcium", "2 glasses of milk for calcium restoration",
              "Ages 9–17 is the bone-building window · <em>+600mg calcium</em>",
              "With meals", "critical" if traffic_light.get("calcium_mg", {}).get("pct_met", 100) < 50 else "pending"),
        _item("anti_inflammatory", "Anti-inflammatory dinner tonight",
              "Salmon, leafy greens, or olive oil · reduces muscle soreness",
              "7:00 PM", "pending"),
        hydration_item(),
    ]
```

- [ ] **Step 4: Run tests**

```bash
source venv/bin/activate && pytest tests/test_today_service.py -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/today_service.py tests/test_today_service.py
git commit -m "feat(today): add get_mission_items() with tests"
```

---

## Task 3: Update `/api/athletes/{id}/daily-summary` route

**Files:**
- Modify: `api/routes/today.py`

- [ ] **Step 1: Update imports and response**

Open `api/routes/today.py`. Replace the import line:

```python
from api.services.today_service import (
    compute_logged_totals,
    compute_traffic_light,
    calc_letter_grade,
    get_positive_rows,
    get_gap_rows,
    get_athlete_streak,
    get_urgent_action,
)
```

with:

```python
from api.services.today_service import (
    compute_logged_totals,
    compute_traffic_light,
    calc_letter_grade,
    get_positive_rows,
    get_gap_rows,
    get_athlete_streak,
    get_urgent_action,
    calculate_performance_forecast,
    get_mission_items,
)
```

- [ ] **Step 2: Expand the athlete object and add new fields to response**

In `get_daily_summary()`, find the `return {` block. Replace the `"athlete"` key and add the two new keys:

```python
        return {
            "athlete": {
                "first_name":        athlete["first_name"],
                "last_name":         athlete.get("last_name"),
                "gender":            gender,
                "position":          athlete.get("position"),
                "competition_level": athlete.get("competition_level"),
                "jersey_number":     athlete.get("jersey_number"),
                "team_name":         athlete.get("team_name"),
                "dietary_restrictions": athlete.get("dietary_restrictions"),
                "allergies":         athlete.get("allergies"),
            },
            "date": target_date,
            "event_type": event_type,
            "events": events,
            "targets": targets,
            "logged": logged,
            "traffic_light": tl,
            "meal_logs": meal_logs,
            "letter_grade": calc_letter_grade(score),
            "positive_rows": get_positive_rows(tl, event_type, gender),
            "gap_rows": get_gap_rows(tl, gender, event_type),
            "urgent_action": get_urgent_action(events, tl, meal_logs),
            "streak": get_athlete_streak(athlete_id, conn),
            "tomorrow_event": dict(tomorrow_row) if tomorrow_row else None,
            "water_cups": water_cups,
            "lea_alert": targets.get("lea_alert", False),
            "performance_forecast": calculate_performance_forecast(tl),
            "mission_items": get_mission_items(event_type, events, tl, meal_logs, targets, water_cups, gender),
        }
```

- [ ] **Step 3: Verify the API starts and returns new fields**

```bash
source venv/bin/activate && python -c "from api.routes.today import router; print('OK')"
```

Expected: `OK`

```bash
curl -s "http://localhost:8000/api/athletes/9/daily-summary" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('performance_forecast:', d.get('performance_forecast'))
print('mission_items count:', len(d.get('mission_items', [])))
print('mission_items[0]:', d.get('mission_items', [{}])[0])
"
```

Expected: `performance_forecast` has 4 keys, `mission_items` has 5 items.

- [ ] **Step 4: Commit**

```bash
git add api/routes/today.py
git commit -m "feat(today): expose performance_forecast and mission_items in daily-summary"
```

---

## Task 4: BroadcastCard.jsx

**Files:**
- Create: `frontend/src/components/today/BroadcastCard.jsx`

- [ ] **Step 1: Create BroadcastCard.jsx**

Create `frontend/src/components/today/BroadcastCard.jsx`:

```jsx
import { useState, useEffect } from "react";

// ── Countdown helpers ──────────────────────────────────────────────────────
function computeCountdown(events) {
  const now = new Date();
  const upcoming = events
    .map(e => {
      if (!e.start_time) return null;
      const [h, m] = e.start_time.split(":").map(Number);
      const t = new Date(now);
      t.setHours(h, m, 0, 0);
      return { ...e, eventTime: t, diff: t - now };
    })
    .filter(e => e && e.diff > 0)
    .sort((a, b) => a.diff - b.diff);

  if (!upcoming.length) return { text: "IN PROGRESS", mins: 0, isLive: true };
  const mins = Math.floor(upcoming[0].diff / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return { text: `${h}:${String(m).padStart(2, "0")}`, mins, isLive: false };
}

// ── Score helpers ──────────────────────────────────────────────────────────
function scoreColor(score) {
  if (score >= 75) return "#2d6a4f";
  if (score >= 50) return "#b45309";
  return "#b83a3a";
}

function taglineContent(score) {
  if (score >= 85) return { emoji: "🏆", text: "Fueled for a career-best performance today." };
  if (score >= 70) return { emoji: "⚡", text: "One snack away from game-ready — eat now" };
  if (score >= 50) return { emoji: "📈", text: "Building toward peak — close the iron gap now." };
  return { emoji: "🔴", text: "Your body is running on empty. Fix this now." };
}

// ── ReadinessDial ─────────────────────────────────────────────────────────
function ReadinessDial({ score }) {
  const [displayed, setDisplayed] = useState(0);
  const circumference = 182; // 2π × 29

  useEffect(() => {
    const timer = setTimeout(() => {
      let val = 0;
      const interval = setInterval(() => {
        val = Math.min(val + 2, score);
        setDisplayed(val);
        if (val >= score) clearInterval(interval);
      }, 14);
      return () => clearInterval(interval);
    }, 200);
    return () => clearTimeout(timer);
  }, [score]);

  const offset = circumference - (circumference * displayed) / 100;
  const color = scoreColor(score);
  const statusLabel = score >= 75 ? "READY" : score >= 50 ? "BUILDING" : "LOW";

  return (
    <div style={rd.wrap}>
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="29" fill="none" stroke="#dce8e0" strokeWidth="5" />
        <circle
          cx="36" cy="36" r="29" fill="none"
          stroke={color} strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 36 36)"
          style={{ transition: "stroke-dashoffset 0.9s cubic-bezier(.4,0,.2,1)" }}
        />
        <text x="36" y="33" textAnchor="middle" fill={color} fontSize="16" fontWeight="800" fontFamily="Nunito,sans-serif">{displayed}</text>
        <text x="36" y="43" textAnchor="middle" fill="#8aa898" fontSize="7" fontFamily="DM Sans,sans-serif" letterSpacing="1">READY</text>
      </svg>
      <div style={rd.status}>{statusLabel}</div>
    </div>
  );
}
const rd = {
  wrap:   { display: "flex", flexDirection: "column", alignItems: "center", gap: "2px", flexShrink: 0 },
  status: { fontSize: "9px", textTransform: "uppercase", letterSpacing: ".05em", color: "#8aa898" },
};

// ── BroadcastCard ─────────────────────────────────────────────────────────
export default function BroadcastCard({ athlete, events, trafficLight, fuelScore, onNavigateMealPlan }) {
  const [countdown, setCountdown] = useState(() => computeCountdown(events));

  useEffect(() => {
    const interval = setInterval(() => setCountdown(computeCountdown(events)), 30000);
    return () => clearInterval(interval);
  }, [events]);

  const score = fuelScore ?? 0;
  const tl = trafficLight ?? {};
  const isUrgent = !countdown.isLive && countdown.mins < 30;
  const tagline = taglineContent(score);

  const hasEvent = events.length > 0;
  const eventStr = hasEvent
    ? `${events[0].event_type?.replace(/_/g, " ")} · ${events[0].event_name || "Training"}`
    : "Rest Day";

  const carbsPct  = tl.carbs_g?.pct_met  ?? 0;
  const ironPct   = tl.iron_mg?.pct_met  ?? 0;
  const ironSub   = ironPct < 50 ? "critical" : ironPct < 80 ? "low" : "on track";

  return (
    <div style={bc.card}>
      {/* Ticker */}
      <div style={bc.ticker}>
        <div style={bc.liveDot} />
        <span style={bc.liveLabel}>LIVE</span>
        <div style={bc.tickerSep} />
        <span style={bc.tickerEvent}>{eventStr.toUpperCase()}</span>
        <span style={{ ...bc.tickerCountdown, color: isUrgent ? "#b83a3a" : "#b45309" }}>
          {hasEvent ? (countdown.isLive ? "IN PROGRESS" : `${countdown.text} TO KICKOFF`) : "NO EVENT"}
        </span>
      </div>

      {/* Identity */}
      <div style={bc.identityRow}>
        <div>
          {(athlete.position || athlete.competition_level) && (
            <div style={bc.positionLine}>
              {[athlete.position, athlete.competition_level].filter(Boolean).join(" · ")}
            </div>
          )}
          <div style={bc.nameBlock}>
            <div style={bc.firstName}>{athlete.first_name}</div>
            {athlete.last_name && <div style={bc.lastName}>{athlete.last_name}</div>}
          </div>
          {athlete.team_name && (
            <div style={bc.teamLine}>{athlete.team_name}</div>
          )}
        </div>
        <ReadinessDial score={score} />
      </div>

      {/* Tagline bar */}
      <div style={bc.taglineBar} onClick={onNavigateMealPlan} role="button">
        <span style={bc.taglineEmoji}>{tagline.emoji}</span>
        <span style={bc.taglineText}>{tagline.text}</span>
        <span style={bc.taglineArrow}>→</span>
      </div>

      {/* Stats row */}
      <div style={bc.statsRow}>
        <div style={bc.statCell}>
          <div style={bc.statLabel}>Fuel score</div>
          <div style={{ ...bc.statValue, color: scoreColor(score) }}>{score}</div>
          <div style={bc.statSub}>/ 100</div>
        </div>
        <div style={bc.statCell}>
          <div style={bc.statLabel}>Carbs</div>
          <div style={{ ...bc.statValue, color: carbsPct >= 80 ? "#2d6a4f" : carbsPct >= 50 ? "#b45309" : "#b83a3a" }}>
            {carbsPct}%
          </div>
          <div style={bc.statSub}>of target</div>
        </div>
        <div style={{ ...bc.statCell }}>
          <div style={bc.statLabel}>Iron</div>
          <div style={{ ...bc.statValue, color: ironPct >= 80 ? "#2d6a4f" : ironPct >= 50 ? "#b45309" : "#b83a3a" }}>
            {ironPct}%
          </div>
          <div style={bc.statSub}>{ironSub}</div>
        </div>
        <div style={{ ...bc.statCell, borderRight: "none" }}>
          <div style={bc.statLabel}>Kickoff</div>
          <div style={{ ...bc.statValue, color: isUrgent ? "#b83a3a" : "#b45309" }}>
            {hasEvent ? (countdown.isLive ? "—" : countdown.text) : "—"}
          </div>
          <div style={bc.statSub}>{countdown.isLive ? "LIVE" : "hrs·min"}</div>
        </div>
      </div>
    </div>
  );
}

const bc = {
  card:          { background: "#fff", borderBottom: "1px solid #dce8e0" },
  ticker:        { background: "#f4f8f5", borderBottom: "1px solid #dce8e0", height: "34px", padding: "0 14px", display: "flex", alignItems: "center", gap: "8px" },
  liveDot:       { width: "6px", height: "6px", borderRadius: "50%", background: "#e05a4a", animation: "athfuelpath-pulse 1.4s infinite", flexShrink: 0 },
  liveLabel:     { fontSize: "9px", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: "700", color: "#e05a4a" },
  tickerSep:     { width: "1px", height: "12px", background: "#dce8e0" },
  tickerEvent:   { fontSize: "10px", textTransform: "uppercase", letterSpacing: ".04em", color: "#8aa898", fontWeight: "300", flex: 1, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" },
  tickerCountdown: { fontSize: "10px", fontWeight: "700", textTransform: "uppercase", flexShrink: 0 },
  identityRow:   { padding: "16px 14px 12px", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" },
  positionLine:  { fontSize: "11px", textTransform: "uppercase", letterSpacing: ".08em", color: "#8aa898", fontWeight: "500", marginBottom: "4px" },
  nameBlock:     { lineHeight: "1.0" },
  firstName:     { fontFamily: "'Nunito', sans-serif", fontSize: "28px", fontWeight: "800", letterSpacing: "-.04em", color: "#1b3a2a" },
  lastName:      { fontFamily: "'Nunito', sans-serif", fontSize: "28px", fontWeight: "800", letterSpacing: "-.04em", color: "#1b3a2a" },
  teamLine:      { fontSize: "11px", color: "#8aa898", fontWeight: "300", marginTop: "4px" },
  taglineBar:    { margin: "0 14px 14px", borderRadius: "9px", padding: "11px 13px", background: "#2d6a4f", display: "flex", alignItems: "center", gap: "10px", cursor: "pointer" },
  taglineEmoji:  { fontSize: "18px" },
  taglineText:   { fontFamily: "'Nunito', sans-serif", fontSize: "13px", fontWeight: "800", color: "#d4ead8", letterSpacing: "-.01em", lineHeight: "1.3", flex: 1 },
  taglineArrow:  { fontSize: "16px", color: "#b7e4c7", opacity: ".5" },
  statsRow:      { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", borderTop: "1px solid #dce8e0" },
  statCell:      { padding: "11px 10px", borderRight: "1px solid #dce8e0" },
  statLabel:     { fontSize: "8px", textTransform: "uppercase", letterSpacing: ".07em", color: "#8aa898", marginBottom: "3px" },
  statValue:     { fontFamily: "'Nunito', sans-serif", fontSize: "14px", fontWeight: "800", letterSpacing: "-.02em", lineHeight: "1", marginBottom: "2px" },
  statSub:       { fontSize: "9px", color: "#8aa898", fontWeight: "300" },
};
```

- [ ] **Step 2: Add the CSS animation keyframe to index.html or global CSS**

Open `frontend/index.html`. Add inside `<head>`:

```html
<style>
  @keyframes athfuelpath-pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/today/BroadcastCard.jsx frontend/index.html
git commit -m "feat(today): add BroadcastCard with LiveTicker, ReadinessDial, StatsRow"
```

---

## Task 5: PerformanceForecast.jsx

**Files:**
- Create: `frontend/src/components/today/PerformanceForecast.jsx`

- [ ] **Step 1: Create PerformanceForecast.jsx**

Create `frontend/src/components/today/PerformanceForecast.jsx`:

```jsx
import { useState, useEffect } from "react";

function metricColor(pct) {
  if (pct >= 75) return "#2d6a4f";
  if (pct >= 50) return "#b45309";
  return "#b83a3a";
}

export default function PerformanceForecast({ forecast }) {
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 50);
    return () => clearTimeout(t);
  }, []);

  if (!forecast) return null;

  const metrics = [
    { key: "sprint_capacity",   label: "Sprint Capacity" },
    { key: "energy_reserves",   label: "Energy Reserves" },
    { key: "second_half_power", label: "Second-Half Power" },
    { key: "mental_focus",      label: "Mental Focus" },
  ];

  return (
    <div style={s.card}>
      <div style={s.headerRow}>
        <span style={s.eyebrow}>Performance forecast · Based on current fueling</span>
        <span style={s.right}>vs your baseline</span>
      </div>
      <div style={s.grid}>
        {metrics.map(({ key, label }) => {
          const pct = forecast[key] ?? 0;
          const color = metricColor(pct);
          return (
            <div key={key}>
              <div style={s.itemHeader}>
                <span style={s.name}>{label}</span>
                <span style={{ ...s.pct, color }}>{pct}%</span>
              </div>
              <div style={s.track}>
                <div style={{
                  ...s.fill,
                  width: animated ? `${pct}%` : "0%",
                  background: color,
                }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const s = {
  card:       { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", padding: "13px 14px", marginTop: "10px" },
  headerRow:  { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" },
  eyebrow:    { fontSize: "9px", textTransform: "uppercase", letterSpacing: ".1em", color: "#8aa898" },
  right:      { fontSize: "9px", color: "#c0c0c0", fontWeight: "300" },
  grid:       { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" },
  itemHeader: { display: "flex", justifyContent: "space-between", marginBottom: "4px" },
  name:       { fontSize: "11px", color: "#1b3a2a" },
  pct:        { fontSize: "11px", fontWeight: "700" },
  track:      { height: "2px", background: "#f4f8f5", borderRadius: "2px", overflow: "hidden" },
  fill:       { height: "100%", borderRadius: "2px", transition: "width 0.7s ease" },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/today/PerformanceForecast.jsx
git commit -m "feat(today): add PerformanceForecast component"
```

---

## Task 6: MissionItem.jsx + DailyMission.jsx

**Files:**
- Create: `frontend/src/components/today/MissionItem.jsx`
- Create: `frontend/src/components/today/DailyMission.jsx`

- [ ] **Step 1: Create MissionItem.jsx**

Create `frontend/src/components/today/MissionItem.jsx`:

```jsx
export default function MissionItem({ item, isDone, onToggle }) {
  const state = isDone ? "done" : item.state;
  const tag   = isDone ? "DONE" : item.tag;

  const boxStyle = {
    done:     { border: "1px solid rgba(45,106,79,.3)", background: "rgba(45,106,79,.12)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "11px", color: "#2d6a4f" },
    urgent:   { border: "1.5px solid rgba(180,83,9,.5)", background: "rgba(180,83,9,.08)" },
    critical: { border: "1.5px solid rgba(184,58,58,.4)", background: "rgba(184,58,58,.08)" },
    pending:  { border: "1.5px solid #dce8e0", background: "transparent" },
  };

  const tagStyle = {
    DONE:     { background: "rgba(45,106,79,.10)",  color: "#2d6a4f" },
    NOW:      { background: "rgba(180,83,9,.12)",   color: "#b45309", animation: "athfuelpath-pulse 1.4s infinite" },
    "FIX THIS": { background: "rgba(184,58,58,.10)", color: "#b83a3a" },
    UPCOMING: { background: "#f4f8f5",               color: "#8aa898" },
  };

  return (
    <div style={{ ...s.row, opacity: isDone ? 0.55 : 1 }} onClick={onToggle}>
      <div style={{ ...s.checkBox, ...(boxStyle[state] || boxStyle.pending) }}>
        {state === "done" ? "✓" : null}
      </div>
      <div style={s.body}>
        <div style={{ ...s.label, ...(isDone ? s.labelDone : {}) }}>{item.label}</div>
        {item.sub && (
          <div
            style={s.sub}
            dangerouslySetInnerHTML={{ __html: item.sub }}
          />
        )}
      </div>
      <div style={s.right}>
        <span style={s.time}>{item.time}</span>
        <span style={{ ...s.tag, ...(tagStyle[tag] || tagStyle.UPCOMING) }}>{tag}</span>
      </div>
    </div>
  );
}

const s = {
  row:       { display: "flex", alignItems: "flex-start", gap: "10px", padding: "11px 14px", borderBottom: "1px solid #dce8e0", cursor: "pointer" },
  checkBox:  { width: "20px", height: "20px", borderRadius: "5px", flexShrink: 0, marginTop: "1px" },
  body:      { flex: 1 },
  label:     { fontSize: "13px", fontWeight: "500", color: "#1b3a2a", lineHeight: "1.3", marginBottom: "2px" },
  labelDone: { textDecoration: "line-through", color: "#8aa898" },
  sub:       { fontSize: "10px", color: "#8aa898", fontWeight: "300", lineHeight: "1.4" },
  right:     { display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "3px", flexShrink: 0 },
  time:      { fontSize: "10px", color: "#8aa898", fontWeight: "300" },
  tag:       { fontSize: "9px", fontWeight: "600", letterSpacing: ".04em", padding: "2px 7px", borderRadius: "3px" },
};
```

- [ ] **Step 2: Create DailyMission.jsx**

Create `frontend/src/components/today/DailyMission.jsx`:

```jsx
import { useState } from "react";
import MissionItem from "./MissionItem";

const API = import.meta.env.VITE_API_URL ?? "";

export default function DailyMission({ missionItems, eventType, date, athleteId, onToast }) {
  const [doneSet, setDoneSet] = useState(
    () => new Set(missionItems.filter(i => i.state === "done").map(i => i.item_type))
  );

  const items = missionItems ?? [];
  const doneCount = items.filter(i => doneSet.has(i.item_type)).length;
  const pct = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 0;

  async function handleToggle(item) {
    const wasDone = doneSet.has(item.item_type);
    setDoneSet(prev => {
      const next = new Set(prev);
      wasDone ? next.delete(item.item_type) : next.add(item.item_type);
      return next;
    });
    if (!wasDone) {
      onToast?.("✓ Logged — fuel score updating");
      try {
        await fetch(`${API}/api/meal-logs/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            athlete_id: athleteId,
            meal_type: item.item_type,
            description: item.label,
            logged_at: new Date().toISOString(),
          }),
        });
      } catch (_) {}
    }
  }

  const dayLabel = eventType
    ? eventType.charAt(0).toUpperCase() + eventType.slice(1) + " Day"
    : "Today";
  const dateStr = date
    ? new Date(date + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : "";

  return (
    <div style={s.card}>
      <div style={s.header}>
        <div>
          <div style={s.eyebrow}>{dayLabel} · {dateStr}</div>
          <div style={s.title}>Today's Mission</div>
        </div>
        <div style={s.progress}>
          <div style={s.count}>
            {doneCount}<span style={s.denom}>/{items.length}</span>
          </div>
          <span style={s.completeLabel}>complete</span>
          <div style={s.bar}><div style={{ ...s.barFill, width: `${pct}%` }} /></div>
        </div>
      </div>
      {items.map((item, idx) => (
        <div key={item.item_type} style={idx === items.length - 1 ? { borderBottom: "none" } : {}}>
          <MissionItem
            item={item}
            isDone={doneSet.has(item.item_type)}
            onToggle={() => handleToggle(item)}
          />
        </div>
      ))}
    </div>
  );
}

const s = {
  card:          { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", overflow: "hidden", marginTop: "10px" },
  header:        { padding: "13px 14px 11px", borderBottom: "1px solid #dce8e0", display: "flex", alignItems: "flex-start", justifyContent: "space-between" },
  eyebrow:       { fontSize: "9px", textTransform: "uppercase", letterSpacing: ".1em", color: "#8aa898", marginBottom: "2px" },
  title:         { fontFamily: "'Nunito', sans-serif", fontSize: "16px", fontWeight: "800", letterSpacing: "-.02em", color: "#1b3a2a" },
  progress:      { textAlign: "right" },
  count:         { fontFamily: "'Nunito', sans-serif", fontSize: "20px", fontWeight: "800", letterSpacing: "-.04em", color: "#2d6a4f", lineHeight: "1" },
  denom:         { fontSize: "12px", color: "#8aa898", fontWeight: "400" },
  completeLabel: { fontSize: "9px", color: "#8aa898", fontWeight: "300", display: "block", marginBottom: "4px" },
  bar:           { width: "64px", height: "2px", background: "#f4f8f5", borderRadius: "2px", overflow: "hidden", marginLeft: "auto" },
  barFill:       { height: "100%", background: "#2d6a4f", borderRadius: "2px", transition: "width 0.4s ease" },
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/today/MissionItem.jsx frontend/src/components/today/DailyMission.jsx
git commit -m "feat(today): add DailyMission and MissionItem components"
```

---

## Task 7: ScienceEdge.jsx

**Files:**
- Create: `frontend/src/components/today/ScienceEdge.jsx`

- [ ] **Step 1: Create ScienceEdge.jsx**

Create `frontend/src/components/today/ScienceEdge.jsx`:

```jsx
import { useState, useEffect } from "react";

const CARDS = [
  {
    id: "iron",
    quote: (ironPct) => `<em>Iron</em> carries oxygen to your muscles. At ${ironPct}%, your legs will feel heavy in minute 70.`,
    detail: "Iron enables red blood cells to deliver oxygen during sustained running. When iron is low, your sprint recovery slows — you feel it as heavy legs in the second half, not the first.",
    fixes: [
      { food: "Lentil soup at lunch",           gain: "+4.2mg iron" },
      { food: "Lean beef at dinner",             gain: "+3.5mg iron" },
      { food: "Spinach + OJ (vitamin C helps)",  gain: "+2.1mg iron" },
    ],
    source: "Everett MD 2025 · Stony Brook University",
  },
  {
    id: "carbs",
    quote: () => `<em>Carb loading</em> starts 24 hours before kickoff — not the morning of the game.`,
    detail: "Muscle glycogen — your sprint fuel — takes 24 to 48 hours to fully replenish. Friday dinner fills Saturday's tank. Saturday breakfast just tops it off. Most athletes don't know this.",
    fixes: [
      { food: "Tonight: Power Pasta Bowl",   gain: "High carb load" },
      { food: "Tomorrow: OJ + toast at 7am", gain: "Top-off fuel" },
      { food: "9:15am snack: Banana + PB",   gain: "Fast glucose" },
    ],
    source: "Everett MD 2025 · Stony Brook University",
  },
  {
    id: "calcium",
    quote: () => `Ages 9–17 is the <em>only window</em> to build peak bone mass. After this, the opportunity closes.`,
    detail: "Peak bone mineral density is established almost entirely during adolescence. Every day of adequate calcium at 13–17 is a deposit into a bone bank that cannot be reopened after age 25.",
    fixes: [
      { food: "2 glasses of milk today",       gain: "+600mg calcium" },
      { food: "Greek yogurt bedtime snack",     gain: "+280mg calcium" },
      { food: "Fortified OJ with breakfast",    gain: "+350mg calcium" },
    ],
    source: "American Academy of Pediatrics (AAP)",
  },
];

export default function ScienceEdge({ trafficLight, onToast }) {
  const ironPct = trafficLight?.iron_mg?.pct_met ?? 100;

  // Iron < 50 → always show card 0 first
  const startIdx = ironPct < 50 ? 0 : new Date().getDay() % 3;
  const [active, setActive] = useState(startIdx);

  useEffect(() => {
    const interval = setInterval(() => setActive(i => (i + 1) % 3), 8000);
    return () => clearInterval(interval);
  }, []);

  const card = CARDS[active];
  const quoteHtml = card.quote(ironPct);

  function handleFixTap(food) {
    onToast?.(`${food} added to meal plan →`);
  }

  return (
    <div style={s.card}>
      <div style={s.header}>
        <div style={s.iconBox}>🔬</div>
        <span style={s.eyebrow}>Today's Performance Edge</span>
        <div style={s.dots}>
          {CARDS.map((_, i) => (
            <div
              key={i}
              onClick={() => setActive(i)}
              style={{ ...s.dot, ...(i === active ? s.dotActive : s.dotInactive) }}
            />
          ))}
        </div>
      </div>
      <div style={s.body}>
        <div
          style={s.quote}
          dangerouslySetInnerHTML={{ __html: quoteHtml }}
        />
        <div style={s.detail}>{card.detail}</div>
        {card.fixes.map(fix => (
          <div key={fix.food} style={s.fix} onClick={() => handleFixTap(fix.food)}>
            <span style={s.fixName}>{fix.food}</span>
            <span style={s.fixGain}>{fix.gain}</span>
          </div>
        ))}
        <div style={s.source}>📖 {card.source}</div>
      </div>
    </div>
  );
}

const s = {
  card:       { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", overflow: "hidden", marginTop: "10px" },
  header:     { padding: "10px 14px 8px", borderBottom: "1px solid #dce8e0", display: "flex", alignItems: "center", gap: "8px" },
  iconBox:    { width: "26px", height: "26px", borderRadius: "6px", background: "rgba(45,106,79,.10)", border: "1px solid rgba(45,106,79,.20)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px" },
  eyebrow:    { fontSize: "9px", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".1em", color: "#2d6a4f", flex: 1 },
  dots:       { display: "flex", gap: "4px", alignItems: "center" },
  dot:        { width: "5px", height: "5px", borderRadius: "50%", cursor: "pointer" },
  dotActive:  { background: "#2d6a4f" },
  dotInactive:{ background: "#f4f8f5", border: "1px solid #dce8e0" },
  body:       { padding: "14px" },
  quote:      { fontFamily: "'Nunito', sans-serif", fontSize: "15px", fontWeight: "700", letterSpacing: "-.01em", color: "#1b3a2a", lineHeight: "1.4", marginBottom: "8px" },
  detail:     { fontSize: "12px", color: "#8aa898", fontWeight: "300", lineHeight: "1.6", marginBottom: "10px" },
  fix:        { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", background: "#f4f8f5", border: "1px solid #dce8e0", borderRadius: "7px", marginBottom: "6px", cursor: "pointer" },
  fixName:    { fontSize: "12px", color: "#1b3a2a" },
  fixGain:    { fontSize: "11px", fontWeight: "700", color: "#2d6a4f" },
  source:     { marginTop: "10px", paddingTop: "10px", borderTop: "1px solid #dce8e0", fontSize: "10px", color: "#8aa898", fontWeight: "300" },
};
```

Note: add `em { font-style: normal; color: #2d6a4f; font-weight: 700; }` to the global style tag in `index.html` so `<em>` in dangerouslySetInnerHTML renders correctly.

- [ ] **Step 2: Add em style to index.html**

Open `frontend/index.html`. Inside the existing `<style>` block add:

```css
em { font-style: normal; color: #2d6a4f; font-weight: 700; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/today/ScienceEdge.jsx frontend/index.html
git commit -m "feat(today): add ScienceEdge rotating cards component"
```

---

## Task 8: QuickRow.jsx

**Files:**
- Create: `frontend/src/components/today/QuickRow.jsx`

- [ ] **Step 1: Create QuickRow.jsx**

Create `frontend/src/components/today/QuickRow.jsx`:

```jsx
const API = import.meta.env.VITE_API_URL ?? "";

export default function QuickRow({ waterCups, targetCups, caloriesLogged, caloriesTarget, athleteId, onWaterUpdate }) {
  const pctWater = targetCups > 0 ? Math.round((waterCups / targetCups) * 100) : 0;
  const ozLogged = (waterCups ?? 0) * 8;
  const ozTarget = (targetCups ?? 10) * 8;

  const calPct   = caloriesTarget > 0 ? Math.round((caloriesLogged / caloriesTarget) * 100) : 0;
  const calRemain = Math.max(0, Math.round((caloriesTarget ?? 0) - (caloriesLogged ?? 0)));
  const calColor  = calPct >= 80 ? "#2d6a4f" : calPct >= 60 ? "#b45309" : "#b83a3a";

  async function handleCupTap(i) {
    const newCups = i < waterCups ? i : i + 1;
    onWaterUpdate(newCups);
    try {
      await fetch(`${API}/api/water-log/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ athlete_id: athleteId, cups: newCups }),
      });
    } catch (_) {}
  }

  return (
    <div style={s.row}>
      {/* Hydration */}
      <div style={s.card}>
        <div style={s.label}>💧 Hydration</div>
        <div style={{ ...s.value, color: "#1a6ab8" }}>{ozLogged}oz</div>
        <div style={s.sub}>of {ozTarget}oz · {pctWater}%</div>
        <div style={s.cups}>
          {Array.from({ length: targetCups || 10 }, (_, i) => (
            <button
              key={i}
              style={{ ...s.cup, ...(i < waterCups ? s.cupFilled : s.cupEmpty) }}
              onClick={() => handleCupTap(i)}
            >
              {i < waterCups ? "💧" : "○"}
            </button>
          ))}
        </div>
      </div>

      {/* Calories */}
      <div style={s.card}>
        <div style={s.label}>🔥 Calories</div>
        <div style={{ ...s.value, color: calColor }}>{Math.round(caloriesLogged ?? 0)}</div>
        <div style={s.sub}>of {Math.round(caloriesTarget ?? 0)} · {calPct}%</div>
        <div style={s.track}><div style={{ ...s.fill, width: `${Math.min(calPct, 100)}%`, background: calColor }} /></div>
        <div style={s.note}>{calRemain} kcal remaining</div>
      </div>
    </div>
  );
}

const s = {
  row:       { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "10px" },
  card:      { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", padding: "13px" },
  label:     { fontSize: "9px", textTransform: "uppercase", letterSpacing: ".07em", color: "#8aa898", marginBottom: "4px" },
  value:     { fontFamily: "'Nunito', sans-serif", fontSize: "22px", fontWeight: "800", letterSpacing: "-.03em", lineHeight: "1", marginBottom: "2px" },
  sub:       { fontSize: "10px", color: "#8aa898", fontWeight: "300", marginBottom: "6px" },
  cups:      { display: "flex", flexWrap: "wrap", gap: "3px", marginTop: "4px" },
  cup:       { width: "18px", height: "18px", borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "9px", cursor: "pointer", border: "none", padding: 0 },
  cupFilled: { background: "rgba(26,106,184,.10)", border: "1px solid rgba(26,106,184,.40)" },
  cupEmpty:  { background: "transparent", border: "1px solid #dce8e0", color: "#8aa898" },
  track:     { height: "2px", background: "#f4f8f5", borderRadius: "2px", overflow: "hidden", marginTop: "2px" },
  fill:      { height: "100%", borderRadius: "2px", transition: "width 0.7s ease" },
  note:      { fontSize: "10px", color: "#8aa898", fontWeight: "300", marginTop: "6px" },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/today/QuickRow.jsx
git commit -m "feat(today): add QuickRow with HydrationMini and CaloriesQuick"
```

---

## Task 9: Toast.jsx

**Files:**
- Create: `frontend/src/components/today/Toast.jsx`

- [ ] **Step 1: Create Toast.jsx**

Create `frontend/src/components/today/Toast.jsx`:

```jsx
import { useState, useEffect, useCallback } from "react";

export function useToast() {
  const [message, setMessage] = useState(null);

  const showToast = useCallback((msg) => {
    setMessage(msg);
    setTimeout(() => setMessage(null), 2200);
  }, []);

  return { message, showToast };
}

export default function Toast({ message }) {
  const visible = !!message;
  return (
    <div style={{
      ...s.toast,
      opacity: visible ? 1 : 0,
      transform: visible ? "translateX(-50%) translateY(0)" : "translateX(-50%) translateY(6px)",
      pointerEvents: visible ? "auto" : "none",
    }}>
      {message}
    </div>
  );
}

const s = {
  toast: {
    position: "fixed",
    bottom: "80px",
    left: "50%",
    transform: "translateX(-50%)",
    background: "#2d6a4f",
    color: "#d4ead8",
    fontFamily: "'Nunito', sans-serif",
    fontSize: "13px",
    fontWeight: "700",
    padding: "10px 20px",
    borderRadius: "8px",
    whiteSpace: "nowrap",
    zIndex: 50,
    transition: "opacity 0.22s, transform 0.22s",
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/today/Toast.jsx
git commit -m "feat(today): add Toast component and useToast hook"
```

---

## Task 10: Rewire Today.jsx + delete old components

**Files:**
- Modify: `frontend/src/pages/Today.jsx`
- Delete: 9 old component files

- [ ] **Step 1: Rewrite Today.jsx**

Replace the entire contents of `frontend/src/pages/Today.jsx` with:

```jsx
import { useState, useEffect, useCallback } from "react";
import BroadcastCard       from "../components/today/BroadcastCard";
import PerformanceForecast from "../components/today/PerformanceForecast";
import DailyMission        from "../components/today/DailyMission";
import ScienceEdge         from "../components/today/ScienceEdge";
import QuickRow            from "../components/today/QuickRow";
import Toast, { useToast } from "../components/today/Toast";

const API = import.meta.env.VITE_API_URL ?? "";

export default function Today({ athlete, onNavigate }) {
  const [summary, setSummary]     = useState(null);
  const [loading, setLoading]     = useState(true);
  const [waterCups, setWaterCups] = useState(0);
  const { message: toastMsg, showToast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/athletes/${athlete.id}/daily-summary`);
      if (res.ok) {
        const d = await res.json();
        setSummary(d);
        setWaterCups(d.water_cups ?? 0);
      }
    } catch (_) {}
    finally { setLoading(false); }
  }, [athlete.id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onVisible = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load]);

  async function handleWaterUpdate(cups) {
    setWaterCups(cups);
    try {
      await fetch(`${API}/api/water-log/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ athlete_id: athlete.id, cups }),
      });
    } catch (_) {}
  }

  if (loading) return (
    <div style={s.loadWrap}>
      <div style={s.spinner} />
      <div style={s.loadText}>Loading today's briefing…</div>
    </div>
  );

  const events      = summary?.events ?? [];
  const eventType   = summary?.event_type ?? "rest";
  const tl          = summary?.traffic_light ?? {};
  const fuelScore   = tl.daily_fuel_score ?? 0;
  const targets     = summary?.targets ?? {};
  const targetCups  = Math.round((targets.hydration_oz_min ?? 64) / 8);
  const missionItems = summary?.mission_items ?? [];
  const forecast    = summary?.performance_forecast ?? null;

  return (
    <div style={s.page}>
      <BroadcastCard
        athlete={summary?.athlete ?? { first_name: athlete.first_name }}
        events={events}
        trafficLight={tl}
        fuelScore={fuelScore}
        onNavigateMealPlan={() => onNavigate("meal-plan")}
      />

      <div style={s.body}>
        <PerformanceForecast forecast={forecast} />

        <DailyMission
          missionItems={missionItems}
          eventType={eventType}
          date={summary?.date}
          athleteId={athlete.id}
          onToast={showToast}
        />

        <ScienceEdge
          trafficLight={tl}
          onToast={showToast}
        />

        <QuickRow
          waterCups={waterCups}
          targetCups={targetCups}
          caloriesLogged={tl.calories?.logged ?? 0}
          caloriesTarget={tl.calories?.target ?? 0}
          athleteId={athlete.id}
          onWaterUpdate={handleWaterUpdate}
        />

        <div style={s.logWrap}>
          <button style={s.logBtn} onClick={() => { showToast("Opening meal logger →"); onNavigate("nutrition"); }}>
            📸 Log a meal — 2 seconds
          </button>
        </div>

        <p style={s.disclaimer}>
          AthFuelPath provides food education guidance — not medical nutrition therapy.
          Consult your physician or a licensed RDN for medical nutrition concerns.
        </p>
      </div>

      <Toast message={toastMsg} />
    </div>
  );
}

const s = {
  page:       { fontFamily: "'Nunito', 'DM Sans', sans-serif", paddingBottom: "8px", background: "#f8faf9", minHeight: "100vh" },
  body:       { padding: "0 12px" },
  loadWrap:   { display: "flex", flexDirection: "column", alignItems: "center", gap: "14px", padding: "60px 0" },
  spinner:    { width: "30px", height: "30px", border: "3px solid #dce8e0", borderTopColor: "#2d6a4f", borderRadius: "50%", animation: "spin 0.7s linear infinite" },
  loadText:   { fontSize: "16px", color: "#4a6358", fontFamily: "'DM Sans', sans-serif" },
  logWrap:    { paddingTop: "10px" },
  logBtn:     { width: "100%", padding: "13px", background: "rgba(45,106,79,.07)", border: "1px dashed rgba(45,106,79,.25)", borderRadius: "14px", color: "#2d6a4f", fontFamily: "'Nunito', sans-serif", fontSize: "13px", fontWeight: "700", letterSpacing: "-.01em", cursor: "pointer", textAlign: "center" },
  disclaimer: { textAlign: "center", fontSize: "10px", color: "#8aa898", lineHeight: "1.5", fontWeight: "300", padding: "10px 0 0" },
};
```

- [ ] **Step 2: Delete old components**

```bash
rm frontend/src/components/today/Greeting.jsx
rm frontend/src/components/today/CountdownHero.jsx
rm frontend/src/components/today/FuelScoreCard.jsx
rm frontend/src/components/today/StreakCard.jsx
rm frontend/src/components/today/WeekBarChart.jsx
rm frontend/src/components/today/NutrientsReportCard.jsx
rm frontend/src/components/today/TomorrowAlert.jsx
rm frontend/src/components/today/NextMealsStrip.jsx
rm frontend/src/components/today/HydrationTracker.jsx
```

- [ ] **Step 3: Verify no broken imports remain**

```bash
grep -r "Greeting\|CountdownHero\|FuelScoreCard\|StreakCard\|WeekBarChart\|NutrientsReportCard\|TomorrowAlert\|NextMealsStrip\|HydrationTracker" frontend/src/ 2>/dev/null
```

Expected: no output.

- [ ] **Step 4: Run lint**

```bash
cd frontend && npm run lint 2>&1 | tail -20
```

Expected: no errors related to new Today components.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Today.jsx
git add frontend/src/components/today/
git commit -m "feat(today): wire up Today v3 — BroadcastCard, Mission, ScienceEdge, QuickRow"
```

---

## Task 11: Manual verification

**Files:** None — read-only verification

- [ ] **Step 1: Restart API server (picks up new service code)**

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null; sleep 1
source venv/bin/activate && uvicorn api.main:app --port 8000 > /tmp/athfuelpath-api.log 2>&1 &
sleep 2 && curl -s http://localhost:8000/api/info | python3 -c "import json,sys; print('API up:', json.load(sys.stdin)['app'])"
```

- [ ] **Step 2: Verify daily-summary returns new fields**

```bash
curl -s "http://localhost:8000/api/athletes/9/daily-summary" | python3 -c "
import json, sys
d = json.load(sys.stdin)
pf = d.get('performance_forecast', {})
mi = d.get('mission_items', [])
print('performance_forecast:', pf)
print('mission_items count:', len(mi))
print('mission_item[0]:', mi[0] if mi else None)
"
```

Expected: 4 forecast keys present, 5 mission items.

- [ ] **Step 3: Check frontend compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: build succeeds with no errors.

- [ ] **Step 4: Open in browser and verify Zone A**

Open http://localhost:5174 (or 5173). Log in. Navigate to Today.

Confirm:
- Live ticker strip visible with pulsing dot
- Athlete first name displayed in large font
- Readiness dial animates from 0 → score on load
- Score number counts up
- Green tagline bar below identity row
- 4-cell stats row at bottom of card

- [ ] **Step 5: Verify Performance Forecast bars animate**

Scroll to Performance Forecast section. Confirm 4 bars animate from 0 to their values on load.

- [ ] **Step 6: Verify Daily Mission**

Confirm 5 mission items visible. Tap one → check box fills green ✓, label gets strikethrough, toast appears. Tap again → reverts.

- [ ] **Step 7: Verify Science Edge rotation**

Confirm science card visible. Wait 8 seconds → card advances to card 2. Click a dot → jumps to that card. Tap a food fix → toast fires.

- [ ] **Step 8: Verify Quick Row**

Confirm hydration cups and calorie bar visible side by side. Tap a cup → fills optimistically. Tap filled cup → unfills.

- [ ] **Step 9: Commit any fixes found**

```bash
git add -p
git commit -m "fix(today): address issues found during manual verification"
```

Only run if fixes were needed in steps 4–8.
