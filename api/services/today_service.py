import logging
from datetime import date, datetime, timedelta
from api.services.meal_timing import compute_meal_slots
from api.services.nutrition_calc import calc_daily_targets
from api.services.window_distribution import distribute_to_slots
from api.services.window_engine_v2 import event_relative_windows_enabled
from api.services.activity_type_resolver import resolve_activity_type
from api.utils.week import get_week_start

log = logging.getLogger(__name__)


def compute_logged_totals(meal_logs: list) -> dict:
    keys = ("calories", "carbs_g", "protein_g", "fat_g", "iron_mg", "calcium_mg", "water_oz")
    totals = {k: 0.0 for k in keys}
    for m in meal_logs:
        for k in keys:
            totals[k] += m.get(k) or 0.0
    return {k: round(v, 1) for k, v in totals.items()}


def compute_traffic_light(targets: dict, logged: dict) -> dict:
    mapping = [
        ("calories",   "total_calories",   0.30),
        ("carbs_g",    "carbs_g_max",      0.25),
        ("protein_g",  "protein_g_max",    0.20),
        ("water_oz",   "hydration_oz_min", 0.15),
        ("iron_mg",    "iron_mg",          0.05),
        ("calcium_mg", "calcium_mg",       0.05),
    ]
    tl = {}
    fuel_score = 0.0
    for logged_key, target_key, weight in mapping:
        logged_val = logged.get(logged_key) or 0.0
        target_val = targets.get(target_key) or 1.0
        pct = min(150, round(logged_val / target_val * 100))
        gap = round(max(0.0, target_val - logged_val), 1)
        status = "met" if pct >= 80 else "low" if pct >= 50 else "build"
        tl[logged_key] = {
            "logged": round(logged_val, 1),
            "target": round(target_val, 1),
            "pct_met": pct,
            "gap": gap,
            "status": status,
        }
        fuel_score += min(100, pct) * weight
    tl["daily_fuel_score"] = round(fuel_score)
    return tl


def calc_letter_grade(score: int) -> str:
    if score >= 90: return "Elite"
    if score >= 83: return "Pro Level"
    if score >= 75: return "Game Ready"
    if score >= 67: return "On Track"
    if score >= 57: return "Building"
    if score >= 47: return "Getting Started"
    if score >= 37: return "Early Days"
    return "Just Starting"


def get_positive_rows(tl: dict, event_type: str, gender: str) -> list:
    checks = [
        ("calories",   "🔥", lambda pct, et: f"{pct}% of daily calories met" if pct < 100 else "Calorie target met today"),
        ("carbs_g",    "⚡", lambda pct, et: f"Carbs on track for {et} day" if et in ("game", "tournament") else "Carbs building nicely"),
        ("protein_g",  "💪", lambda pct, et: "Protein target met" if pct >= 90 else f"Protein at {pct}% — strong"),
        ("calcium_mg", "🦴", lambda pct, et: "Calcium on track" if pct >= 90 else "Bone-building on track"),
        ("water_oz",   "💧", lambda pct, et: "Hydration goal met!" if pct >= 100 else f"Hydration at {pct}%"),
    ]
    if gender.lower() not in ("girl", "female") or tl.get("iron_mg", {}).get("pct_met", 0) >= 90:
        checks.append(("iron_mg", "🩸", lambda pct, et: "Iron target met — great!"))
    positives = []
    for key, icon, label_fn in checks:
        pct = tl.get(key, {}).get("pct_met", 0)
        if pct >= 80:
            positives.append({"icon": icon, "text": label_fn(pct, event_type), "pct": f"{pct}%"})
    return positives[:2]


def get_gap_rows(tl: dict, gender: str, event_type: str) -> list:
    gaps = []
    iron_pct = tl.get("iron_mg", {}).get("pct_met", 100)
    if iron_pct < 75 and gender.lower() in ("girl", "female"):
        gaps.append({
            "key": "iron_mg", "icon": "🩸",
            "name": "Iron — boost opportunity" if iron_pct < 40 else "Iron — let's build this up",
            "detail": "Add lean beef or lentils to your next meal and pair with vitamin C — your body will thank you on the field. — Everett MD 2025",
            "pct": iron_pct, "target": f"of {round(tl['iron_mg']['target'])}mg",
        })
    calcium_pct = tl.get("calcium_mg", {}).get("pct_met", 100)
    if calcium_pct < 75:
        gaps.append({
            "key": "calcium_mg", "icon": "🦴",
            "name": "Calcium — below target",
            "detail": "Add 2 glasses of milk today. Peak bone mass window — ages 9–17 only. — AAP",
            "pct": calcium_pct, "target": f"of {round(tl['calcium_mg']['target'])}mg",
        })
    cal_pct = tl.get("calories", {}).get("pct_met", 100)
    if cal_pct < 60:
        gaps.append({
            "key": "calories", "icon": "🔥",
            "name": "Calories below target",
            "detail": f"{round(tl['calories']['gap'])} kcal remaining · Recovery lunch + bedtime snack will close this gap",
            "pct": cal_pct, "target": f"of {round(tl['calories']['target'])} kcal",
        })
    carbs_pct = tl.get("carbs_g", {}).get("pct_met", 100)
    if carbs_pct < 60 and event_type in ("game", "practice", "tournament", "training"):
        gaps.append({
            "key": "carbs_g", "icon": "⚡",
            "name": f"Carbs low for {event_type} day",
            "detail": f"Need {round(tl['carbs_g']['gap'])}g more · Add rice, pasta, or fruit to next meal",
            "pct": carbs_pct, "target": f"of {round(tl['carbs_g']['target'])}g",
        })
    water_pct = tl.get("water_oz", {}).get("pct_met", 100)
    if water_pct < 50:
        oz_gap = round(tl["water_oz"]["gap"])
        gaps.append({
            "key": "water_oz", "icon": "💧",
            "name": "Hydration below target",
            "detail": f"{oz_gap}oz remaining · {max(1, round(oz_gap / 8))} more cups needed",
            "pct": water_pct, "target": f"of {round(tl['water_oz']['target'])}oz",
        })
    return gaps[:3]


def get_athlete_streak(athlete_id: int, conn) -> dict:
    today = date.today()
    streak = 0
    check_date = today
    while streak <= 365:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at) = %s",
            (athlete_id, check_date.isoformat()),
        ).fetchone()["cnt"]
        if cnt > 0:
            streak += 1
            check_date -= timedelta(days=1)
        elif check_date == today:
            check_date -= timedelta(days=1)
            continue
        else:
            break

    rows = conn.execute(
        "SELECT DISTINCT DATE(logged_at) as d FROM meal_logs WHERE athlete_id = %s ORDER BY d ASC",
        (athlete_id,),
    ).fetchall()
    dates = [r["d"] for r in rows]
    best, best_end, cur = 0, None, 0
    for i, d in enumerate(dates):
        if i == 0:
            cur = 1
        else:
            prev_dt = datetime.strptime(dates[i - 1], "%Y-%m-%d").date()
            curr_dt = datetime.strptime(d, "%Y-%m-%d").date()
            cur = cur + 1 if (curr_dt - prev_dt).days == 1 else 1
        if cur > best:
            best = cur
            best_end = d

    week_start = get_week_start(today)
    week_logged = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at) = %s",
            (athlete_id, d.isoformat()),
        ).fetchone()["cnt"]
        week_logged.append(cnt > 0)

    return {
        "current_streak": streak,
        "best_streak": best,
        "best_streak_date": best_end,
        "week_logged": week_logged,
    }


def get_urgent_action(events: list, tl: dict, meal_logs: list) -> dict:
    now = datetime.now()

    def mins_until(time_str):
        try:
            h, m = map(int, time_str.split(":"))
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
            return round((t - now).total_seconds() / 60)
        except Exception:
            return None

    def has_log_type(keywords):
        for m in meal_logs:
            desc = (m.get("description") or "").lower()
            if any(kw.lower() in desc for kw in keywords):
                return True
        return False

    for ev in events:
        start = ev.get("start_time")
        dur = ev.get("duration_hours") or 1.5
        if not start:
            continue
        mins_to = mins_until(start)
        if mins_to is None:
            continue

        if 10 <= mins_to <= 90 and not has_log_type(["snack", "banana", "pre-game snack", "top-up"]):
            return {
                "icon": "🍌", "title": "Eat your pre-game snack now",
                "sub": "Banana + PB or toast + honey · fast carbs",
                "window": f"Window closes in {max(1, mins_to - 10)} min",
                "window_duration_secs": max(1, mins_to - 10) * 60,
                "action": "log_meal", "meal_type": "snack",
            }

        mins_since_end = -(mins_to + round(dur * 60))
        if 0 <= mins_since_end <= 30 and not has_log_type(["recovery", "chocolate milk", "post-game"]):
            remaining = 30 - mins_since_end
            return {
                "icon": "🏆", "title": "Recovery window open — act now",
                "sub": "Chocolate milk + banana · 3:1 carb:protein",
                "window": f"{remaining} min remaining",
                "window_duration_secs": remaining * 60,
                "action": "log_meal", "meal_type": "recovery",
            }

        if 150 <= mins_to <= 240 and not has_log_type(["breakfast", "oatmeal", "eggs", "pre-game meal"]):
            return {
                "icon": "🍳", "title": "Pre-game breakfast window is open",
                "sub": f"Eat now · {mins_to // 60}hr {mins_to % 60}min to kickoff",
                "window": "Optimal window: 2.5–4hrs before event",
                "window_duration_secs": (mins_to - 150) * 60,
                "action": "log_meal", "meal_type": "breakfast",
            }

    iron_pct = tl.get("iron_mg", {}).get("pct_met", 100)
    if iron_pct < 35:
        return {
            "icon": "🩸", "title": "Iron boost needed today",
            "sub": f"{round(tl['iron_mg']['gap'])}mg to go · Lentils or beef at lunch will get you there",
            "window": "Iron carries oxygen to your muscles — strong levels mean strong legs all game",
            "window_duration_secs": None, "action": "log_meal", "meal_type": "lunch",
        }

    water_pct = tl.get("water_oz", {}).get("pct_met", 100)
    if water_pct < 40:
        cups = max(1, round(tl["water_oz"]["gap"] / 8))
        return {
            "icon": "💧", "title": f"Drink {cups} more cups today",
            "sub": "Tap your hydration tracker below as you drink",
            "window": "Dehydration by 2% measurably slows reaction time",
            "window_duration_secs": None, "action": "scroll_to_hydration",
        }

    score = tl.get("daily_fuel_score", 0)
    if score >= 80:
        return {
            "icon": "🏆", "title": "You're fueling like a pro today",
            "sub": f"Fuel score {score}/100 · Keep it going",
            "window": "Check your meal plan for tonight's recovery snack",
            "window_duration_secs": None, "action": "view_plan",
        }
    return {
        "icon": "📋", "title": "Check today's meal plan",
        "sub": f"Fuel score {score}/100 · Log your next meal",
        "window": "Every logged meal improves your fuel score",
        "window_duration_secs": None, "action": "view_plan",
    }


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
    state: "done" | "urgent" | "build" | "pending"
    tag:   "DONE" | "NOW" | "BOOST" | "UPCOMING"
    """
    now = datetime.now()
    is_female = gender.lower() in ("girl", "female")
    iron_pct = traffic_light.get("iron_mg", {}).get("pct_met") or 0
    iron_gap = round(traffic_light.get("iron_mg", {}).get("gap", 0), 1)
    water_pct = traffic_light.get("water_oz", {}).get("pct_met") or 0
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
        tag = {"done": "DONE", "urgent": "NOW", "build": "BOOST", "pending": "UPCOMING"}[state]
        return {"label": label, "sub": sub, "time": time, "state": state, "tag": tag, "item_type": item_type}

    def iron_item():
        if is_female and iron_pct < 50:
            return _item("iron_lunch", "Boost your iron at lunch",
                         f"Lean beef or lentils + vitamin C · <em>{iron_gap}mg to go</em>",
                         "1:00 PM", "urgent")
        return _item("iron_lunch", "Iron-rich lunch today",
                     "Lentils, lean beef, or fortified cereal", "1:00 PM", "pending")

    def hydration_item():
        cups_done = water_cups or 0
        state = "urgent" if water_pct < 40 else "pending"
        return _item("hydration",
                     f"Drink {cups_remaining} more cup{'s' if cups_remaining != 1 else ''} of water",
                     f"<em>{cups_done}</em> of {target_cups} cups done · {cups_done * 8}oz logged",
                     "All day", state)

    norm = (event_type or "rest").lower()

    # ── GAME DAY ──────────────────────────────────────────────────────────────
    if norm in ("game", "tournament"):
        mins = mins_to_start()
        breakfast_done = _has_log_type(meal_logs, ["breakfast", "oatmeal", "eggs", "pancake", "toast"])
        snack_done = _has_log_type(meal_logs, ["snack", "banana", "pre-game snack"])

        window_passed = mins is not None and mins < 150
        if breakfast_done:
            item1_state = "done"
            item1_label = "Pre-game breakfast logged"
        elif window_passed:
            item1_state = "pending"
            item1_label = "Pre-game breakfast window closed"
        else:
            item1_state = "pending"
            item1_label = "Pre-game breakfast — eat now"

        item2_state = "done" if snack_done else ("urgent" if mins is not None and 10 <= mins <= 90 else "pending")
        recovery_time = _fmt_time(start, dur + 0.5) if start else "After game"
        snack_time = _fmt_time(start, -0.75) if start else "45 min before"

        return [
            _item("pregame_breakfast", item1_label,
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
                _item("protein_recovery", "Protein recovery — 30-min window open",
                      "Chocolate milk or Greek yogurt + banana · <em>30-min window</em>",
                      recovery_time, "urgent"),
                _item("casein_snack", "Bedtime casein snack tonight",
                      "Cottage cheese or Greek yogurt · <em>overnight muscle repair</em>",
                      "9:30 PM", "pending"),
                hydration_item(),
            ]

        return [
            _item("pre_practice_lunch", "Eat your pre-practice lunch by noon",
                  "High-carb lunch · rice, pasta, or sweet potato",
                  "12:00 PM", "pending"),
            _item("pre_practice_snack",
                  f"Pre-practice snack {round((mins or 45))} min before training" if mins and mins > 0 else "Pre-practice snack",
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
            _item("pregame_dinner", "Tonight's pre-game dinner — biggest carb meal of the week",
                  "Pasta + lean protein · <em>this meal fills tomorrow's tank</em>",
                  "6:30 PM", "urgent"),
            _item("low_fiber", "Limit fiber and fat today",
                  "Easy digestion for tomorrow · no salads or heavy sauces",
                  "All day", "pending"),
        ]

    # ── REST / RECOVERY DAY (default) ─────────────────────────────────────────
    return [
        _item("active_recovery", "Rest day fueling — keep your energy up",
              "Your muscles are rebuilding today — 80%+ of normal calories keeps recovery on track",
              "All day", "pending"),
        iron_item(),
        _item("calcium", "2 glasses of milk for calcium restoration",
              "Ages 9–17 is the bone-building window · <em>+600mg calcium</em>",
              "With meals",
              "urgent" if (traffic_light.get("calcium_mg", {}).get("pct_met") or 0) < 50 else "pending"),
        _item("anti_inflammatory", "Anti-inflammatory dinner tonight",
              "Salmon, leafy greens, or olive oil · reduces muscle soreness",
              "7:00 PM", "pending"),
        hydration_item(),
    ]


# ── MACRO FOCUS MAPPING ───────────────────────────────────────────────────────
# Maps slot_name from compute_meal_slots to a display label shown in Today's Mission.
# slot_names use hyphens (from meal_timing.py); underscore variants are also included
# for any callers using underscore-style keys.

MACRO_FOCUS_MAP = {
    # ── New engine keys (window_templates.py) ─────────────────────────────────
    "everyday_breakfast":     "Balanced Fuel",
    "everyday_lunch":         "High Carbs",
    "everyday_snack":         "Quick Fuel",
    "everyday_dinner":        "High Protein + Carbs",
    "pre_event_meal":         "High Carbs",
    "fuel_after_primary":     "Recovery Focus",
    "fuel_after_second":      "High Protein + Carbs",
    "quick_morning_snack":    "Fast Carbs",
    "proper_breakfast_after": "Balanced Fuel",
    # Tournament / double-session keyed variants handled by prefix matching below
    # ── Legacy compute_meal_slots keys (hyphen-separated) ─────────────────────
    "breakfast":                    "Balanced Fuel",
    "mid-morning-snack":            "Quick Fuel",
    "lunch":                        "High Carbs",
    "afternoon-snack":              "Quick Fuel",
    "dinner":                       "High Protein + Carbs",
    "evening-recovery":             "Protein Focus",
    "night-fuel":                   "Protein Focus",
    "pre-game-fuel":                "High Carbs",
    "pre-training":                 "High Carbs + Protein",
    "power-snack":                  "Fast Carbs",
    "halftime-fueling":             "Fast Carbs",
    "recovery-fuel":                "Recovery Focus",
    "recovery-dinner":              "Recovery Fuel",
    "between-games":                "Electrolytes + Carbs",
    # Underscore variants
    "pre_game_breakfast":           "High Carbs",
    "pre_game_snack":               "High Carbs",
    "halftime":                     "Fast Carbs",
    "recovery_snack":               "Recovery Focus",
    "recovery_lunch":               "High Protein + Carbs",
    "pre_practice_lunch":           "High Carbs + Protein",
    "pre_practice_snack":           "High Carbs",
    "post_practice_dinner":         "Recovery Focus",
    "pre_strength_lunch":           "High Protein + Carbs",
    "post_strength_snack":          "High Protein",
    "bedtime_casein":               "Protein Focus",
    "pregame_breakfast":            "High Carbs",
    "pregame_lunch":                "High Carbs",
    "pregame_snack":                "High Carbs",
    "pregame_dinner":               "Max Carb Load",
    "tournament_breakfast":         "High Carbs",
    "between_games":                "Electrolytes + Carbs",
    "tournament_recovery":          "Recovery Focus",
    "recovery_breakfast":           "Light Fuel",
    "recovery_dinner":              "Anti-Inflammatory",
    "snack":                        "Quick Fuel",
    "bedtime_snack":                "Protein Focus",
}


# carb_pct and protein_pct of daily targets allocated to each macro_focus label
_FOCUS_MACRO_PCT = {
    "Balanced Fuel":        {"carbs_pct": 0.22, "protein_pct": 0.20},
    "High Carbs":           {"carbs_pct": 0.35, "protein_pct": 0.15},
    "High Carbs + Protein": {"carbs_pct": 0.30, "protein_pct": 0.25},
    "High Protein + Carbs": {"carbs_pct": 0.20, "protein_pct": 0.30},
    "High Protein":         {"carbs_pct": 0.10, "protein_pct": 0.30},
    "Recovery Focus":       {"carbs_pct": 0.15, "protein_pct": 0.25},
    "Recovery Fuel":        {"carbs_pct": 0.18, "protein_pct": 0.22},
    "Protein Focus":        {"carbs_pct": 0.08, "protein_pct": 0.25},
    "Fast Carbs":           {"carbs_pct": 0.12, "protein_pct": 0.05},
    "Quick Fuel":           {"carbs_pct": 0.10, "protein_pct": 0.08},
    "Max Carb Load":        {"carbs_pct": 0.40, "protein_pct": 0.18},
    "Electrolytes + Carbs": {"carbs_pct": 0.18, "protein_pct": 0.10},
    "Light Fuel":           {"carbs_pct": 0.12, "protein_pct": 0.12},
    "Anti-Inflammatory":    {"carbs_pct": 0.18, "protein_pct": 0.22},
    "Fuel Window":          {"carbs_pct": 0.15, "protein_pct": 0.15},
}


def get_macro_focus(meal_type: str) -> str:
    """Returns the macro focus label for a given slot/meal_type. Never returns None."""
    if not meal_type:
        return "Fuel Window"
    if meal_type in MACRO_FOCUS_MAP:
        return MACRO_FOCUS_MAP[meal_type]
    # Handle tournament/double-session keyed variants: "fuel_after_primary_1", "between_games_1_2", etc.
    _PREFIX_MAP = {
        "fuel_after_primary":     "Recovery Focus",
        "fuel_after_second":      "High Protein + Carbs",
        "pre_event_meal":         "High Carbs",
        "between_games":          "Electrolytes + Carbs",
        "between_sessions":       "Electrolytes + Carbs",
        "proper_breakfast_after": "Balanced Fuel",
    }
    for prefix, focus in _PREFIX_MAP.items():
        if meal_type.startswith(prefix):
            return focus
    key = meal_type.lower().replace(" ", "_").replace("-", "_")
    return MACRO_FOCUS_MAP.get(key, "Fuel Window")


def build_mission_items_from_slots(slot_defs: list, logged_slots: dict, targets: dict = None,
                                   wt_kg: float = None, is_sc_day: bool = False,
                                   duration_min: float = 0) -> list:  # duration_min reserved for keep_going_window() in WD-4
    """
    Converts compute_meal_slots output into Today's Mission items.
    Skips hydration-only slots and double-day alert banners.
    logged_slots: {slot_name: bool} from the meal_plans table.
    targets: daily nutrition targets dict; when provided, adds per-slot carbs_g/protein_g.

    Macro allocation:
      - When EVENT_RELATIVE_WINDOWS is set AND wt_kg is provided, per-slot grams
        come from window_distribution.distribute_to_slots() (Purvi's SPLITS).
      - Otherwise falls back to the legacy _FOCUS_MACRO_PCT table.
    """
    daily_carbs   = (targets or {}).get("carbs_g")   or (targets or {}).get("carbs_g_max")
    daily_protein = (targets or {}).get("protein_g") or (targets or {}).get("protein_g_max")

    # Try the distribution path; fall back to legacy on any precondition miss.
    distributed = None
    if (event_relative_windows_enabled() and wt_kg and daily_carbs and daily_protein):
        distributed = distribute_to_slots(
            slot_defs, round(daily_carbs), round(daily_protein), wt_kg, is_sc_day,
        )

    missions = []
    i = 0
    for slot in slot_defs:
        if slot.get("is_hydration") or slot.get("double_day_alert"):
            continue
        slot_name  = slot["slot_name"]
        focus      = get_macro_focus(slot_name)
        item = {
            "id":          f"mission_{i}",
            "time":        slot.get("eat_by_time", ""),
            "label":       slot.get("display_label", slot_name),
            "macro_focus": focus,
            "logged":      logged_slots.get(slot_name, False),
            "meal_type":   slot_name,
        }
        if distributed is not None and slot_name in distributed:
            d = distributed[slot_name]
            item["carbs_g"]   = d["cho_g"]
            item["protein_g"] = d["prot_g"]
            item["ratio_flag"] = d["flag"]   # parent-only: exposed via response.window_ratio_flags; athlete MissionItem type ignores this field
        elif daily_carbs and daily_protein:
            pcts = _FOCUS_MACRO_PCT.get(focus, {"carbs_pct": 0.15, "protein_pct": 0.15})
            item["carbs_g"]   = round(daily_carbs   * pcts["carbs_pct"])
            item["protein_g"] = round(daily_protein * pcts["protein_pct"])
        missions.append(item)
        i += 1
    return missions


def calculate_performance_forecast(traffic_light: dict) -> dict:
    """Derives 4 performance metrics from nutrition traffic light. Pure math."""
    def pct(key): return min(traffic_light.get(key, {}).get("pct_met") or 0, 100)

    # calcium excluded — no direct acute per-match performance effect
    return {
        "sprint_capacity":   round(pct("carbs_g")   * 0.40 + pct("iron_mg")   * 0.35 + pct("protein_g") * 0.25),
        "energy_reserves":   round(pct("calories")  * 0.60 + pct("carbs_g")   * 0.40),
        "second_half_power": round(pct("iron_mg")   * 0.50 + pct("carbs_g")   * 0.30 + pct("water_oz")  * 0.20),
        "mental_focus":      round(pct("calories")  * 0.40 + pct("water_oz")  * 0.35 + pct("protein_g") * 0.25),
    }


# ── TODAY VIEW ──────────────────────────────────────────────────────────────

_READINESS_LABELS = {
    "elite": "Elite",
    "pro":   "Pro Level",
    "game":  "Game Ready",
    "track": "On Track",
    "build": "Building",
    "start": "Getting Started",
}

_READINESS_LINES: dict = {
    "elite": {
        "game":     ["Your fueling is dialed in — you're ready to compete.", "Stay sharp and hydrated heading into kickoff."],
        "practice": ["Elite fuel score — bring that energy to training.", "Your consistency is building real match fitness."],
        "rest":     ["Your recovery fueling is elite — the gains are locking in now.", "This is how your body builds the next level."],
        "any":      ["Your fueling is dialed in today.", "Keep this rhythm through the week."],
    },
    "pro": {
        "game":     ["Strong fuel score — your tank is loaded for today.", "One more window to hit Elite status."],
        "rest":     ["Strong recovery score — your body is getting exactly what it needs.", "One more window to lock in elite recovery."],
        "any":      ["Strong fuel score today — the plan is working.", "One more window to hit Elite status."],
    },
    "game": {
        "game":     ["Your tank is loaded for today's competition.", "Stay hydrated heading into kickoff."],
        "practice": ["Game-ready fuel score — great prep for training.", "Hit your next window to keep the momentum."],
        "rest":     ["Solid rest-day fueling — you're building tomorrow's energy.", "Complete your next window to keep the recovery going."],
        "any":      ["Solid fueling today — you're on the right track.", "Complete your next window to push your score higher."],
    },
    "track": {
        "game":     ["Good start — complete your next window before the game.", "Every logged window adds to your energy reserves."],
        "rest":     ["Good start on your recovery day — keep the fuel windows coming.", "Rest days that are fueled well lead to stronger training this week."],
        "any":      ["Good start — hit your next window to keep momentum.", "Consistent fueling is how you build match fitness."],
    },
    "build": {
        "game":     ["Game day is here — let's get your fuel windows in.", "Even one more completed window makes a difference."],
        "rest":     ["Rest days are when your body actually gets stronger from the week.", "Keep fueling and you come back faster."],
        "any":      ["Every completed window improves your score.", "Focus on your next fuel window to get back on track."],
    },
    "start": {
        "rest":     ["Rest days need fuel too — let's hit the next window together.", "Your body rebuilds between sessions. Give it what it needs."],
        "any":      ["Let's get your fuel windows going.", "Complete the next window to start building momentum."],
    },
}


def _score_band(score: int) -> str:
    if score >= 90: return "elite"
    if score >= 80: return "pro"
    if score >= 70: return "game"
    if score >= 60: return "track"
    if score >= 50: return "build"
    return "start"


def _readiness_lines(score: int, event_type: str) -> list:
    band = _score_band(score)
    et = (event_type or "rest").lower()
    if et in ("tournament",): et = "game"
    if et in ("training", "strength"): et = "practice"
    # "rest" is kept as its own key — recovery tone, not generic
    lines_map = _READINESS_LINES.get(band, {})
    return lines_map.get(et) or lines_map.get("any") or ["Your fueling is on track.", "Keep going."]


def compute_readiness(logged_count: int, total_count: int, event_type: str) -> dict:
    bonus = round(35 * (logged_count / total_count)) if total_count > 0 else 0
    score = max(40, min(100, 55 + bonus))
    band  = _score_band(score)
    return {
        "score": score,
        "word":  _READINESS_LABELS[band],
        "lines": _readiness_lines(score, event_type),
    }


def assign_window_status(windows: list) -> list:
    next_assigned = False
    result = []
    for w in windows:
        if w.get("logged"):
            result.append({**w, "status": "done"})
        elif not next_assigned:
            result.append({**w, "status": "next"})
            next_assigned = True
        else:
            result.append({**w, "status": "upcoming"})
    return result


def _ensure_window_logs_table(conn) -> None:
    # window_logs (with logged_by/audio_url) is already created by
    # db/postgres/001_baseline.sql — this stays a harmless idempotent no-op
    # there. Kept (rather than deleted) to match existing behavior for any
    # DB that hasn't been migrated yet. Postgres's ADD COLUMN IF NOT EXISTS
    # replaces SQLite's PRAGMA-based column-existence check + ALTER dance.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS window_logs (
            id              INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            athlete_id      INTEGER NOT NULL,
            window_id       TEXT NOT NULL,
            log_date        TEXT NOT NULL,
            method          TEXT NOT NULL DEFAULT 'photo',
            text            TEXT,
            photo_url       TEXT,
            thumb_url       TEXT,
            audio_url       TEXT,
            nutrient_status TEXT NOT NULL DEFAULT 'none',
            logged_by       TEXT,
            created_at      TEXT DEFAULT sqlite_now(),
            UNIQUE(athlete_id, window_id, log_date)
        )
    """)
    conn.execute("ALTER TABLE window_logs ADD COLUMN IF NOT EXISTS logged_by TEXT")
    conn.execute("ALTER TABLE window_logs ADD COLUMN IF NOT EXISTS audio_url TEXT")
    conn.commit()


def record_window_capture(
    athlete_id: int,
    window_id: str,
    method: str,
    text: str | None,
    photo_url: str | None,
    thumb_url: str | None,
    conn,
    audio_url: str | None = None,
    log_date: str | None = None,
) -> int:
    """Insert (or replace) a window_logs row and mark meal_plans.logged for backward compat."""
    _ensure_window_logs_table(conn)
    # INVARIANT: use the client's local date, not the server's UTC date.
    # Without this, athletes in timezones behind UTC will have evening logs
    # assigned to the *next* day (server UTC) and appear pre-done the next morning.
    today = log_date or date.today().isoformat()
    cur = conn.execute(
        """INSERT INTO window_logs
               (athlete_id, window_id, log_date, method, text, photo_url, thumb_url,
                audio_url, nutrient_status, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'none', %s)
           ON CONFLICT(athlete_id, window_id, log_date) DO UPDATE SET
               method=excluded.method, text=excluded.text,
               photo_url=excluded.photo_url, thumb_url=excluded.thumb_url,
               audio_url=excluded.audio_url,
               nutrient_status='none'
           RETURNING id""",
        (athlete_id, window_id, today, method, text, photo_url, thumb_url,
         audio_url, datetime.now().isoformat()),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    # Keep meal_plans.logged in sync for the Meal Plan tab
    conn.execute(
        "UPDATE meal_plans SET logged = 1 WHERE athlete_id = %s AND plan_date = %s AND slot_name = %s",
        (athlete_id, today, window_id),
    )
    conn.commit()
    return new_id


def remove_window_capture(
    athlete_id: int,
    window_id: str,
    conn,
    log_date: str | None = None,
) -> bool:
    """Reverse a window confirmation (un-confirm). Athletes mis-tap; don't trap them.

    Capture writes BOTH window_logs and meal_plans.logged (see record_window_capture),
    and build_today_view derives `logged` from either source — so a full reversal must
    clear both, else the window stays 'done'. Idempotent: returns True if a confirmation
    existed and was removed, False if there was nothing to undo. Uses the client's local
    log_date (same timezone invariant as capture)."""
    _ensure_window_logs_table(conn)
    today = log_date or date.today().isoformat()
    cur = conn.execute(
        "DELETE FROM window_logs WHERE athlete_id = %s AND window_id = %s AND log_date = %s",
        (athlete_id, window_id, today),
    )
    removed = cur.rowcount > 0
    conn.execute(
        "UPDATE meal_plans SET logged = 0 WHERE athlete_id = %s AND plan_date = %s AND slot_name = %s",
        (athlete_id, today, window_id),
    )
    conn.commit()
    return removed


def _build_fuel_targets_block(athlete: dict, events: list, windows: list,
                              tappable: list, template_windows: list,
                              confirmed_keys: set) -> dict:
    """Assemble the additive, flag-gated `fuel_targets` block (Fuel Gauge).

    Targets are derived LIVE, never stored (no stale-target risk). Path is chosen
    by today's event count:
      • no events today → rest-day path, delegates to Blueprint   → target_source "blueprint"
      • >=1 event       → event-day engine (macros + weather/season) → "event_day"

    A window counts as confirmed if its slot_name is in `confirmed_keys` (the
    Today-screen confirm tap → confirmations table) OR it is logged via
    window_logs/meal_plans (CaptureSheet). This UNION matches streak_service's
    "fueled" semantic and ensures the live confirm button drives the gauge.
    confirmed_totals and daily_met are PURE derivations from that combined set —
    no new persistence.
    """
    from api.services import fuel_gauge, fueling_targets as ft

    season_phase = athlete.get("season_phase")
    if events:
        daily = fuel_gauge.compute_event_day_targets(athlete, events, season_phase, None)
        target_source = "event_day"
    else:
        daily = fuel_gauge.compute_rest_day_targets(athlete, season_phase)
        target_source = "blueprint"

    catkey_by_slot = {tw["key"]: tw.get("category_key") for tw in template_windows}

    # category_key added back to windows[] additively. Only reached when the flag
    # is ON, so the flag-OFF payload stays byte-identical to production.
    for w in windows:
        ck = catkey_by_slot.get(w.get("slot_name"))
        if ck is not None:
            w["category_key"] = ck

    # Split across CONFIRMABLE (tappable) windows only. Nudge windows
    # (hydrate/fuel_during, short between_games) are excluded by construction (D6).
    #
    # Phase 5: everyday windows now SHARE the daily target on event days too (paired
    # with un-hiding them on Today, index.tsx). They join the split whenever the engine
    # emits them — the engine-level _everyday_windows suppression still gates which
    # everyday windows actually appear on an event day. Per-slot Purvi ratios live in
    # split_targets_across_windows; the everyday TOTAL (7% CHO / 10% protein) is split
    # across the everyday windows present.
    split_source = tappable
    split_input = [
        {"slot_name": w["slot_name"], "category_key": catkey_by_slot.get(w["slot_name"])}
        for w in split_source
    ]
    split = fuel_gauge.split_targets_across_windows(daily, split_input)
    logged_by_slot = {w["slot_name"]: bool(w.get("logged")) for w in tappable}

    def _is_confirmed(slot: str) -> bool:
        # Union (matches streak_service): confirm tap → confirmations; capture → window_logs.
        return slot in confirmed_keys or logged_by_slot.get(slot, False)

    fuel_windows = [
        {
            "slot_name":    s["slot_name"],
            "category_key": s["category_key"],
            "contribution": s["contribution"],
            "confirmed":    _is_confirmed(s["slot_name"]),
        }
        for s in split
    ]

    # confirmed_totals = sum of CONFIRMED windows' contributions (derived, not stored).
    confirmed_totals = {}
    for n in ft.NUTRIENT_KEYS:
        if daily.get(n) is None:
            confirmed_totals[n] = None
            continue
        total = sum(
            fw["contribution"][n] for fw in fuel_windows
            if fw["confirmed"] and fw["contribution"].get(n) is not None
        )
        confirmed_totals[n] = round(total, 1) if n == "protein_g" else int(round(total))

    # Phase-2 streak seam: expose the signal now, build no consumer.
    daily_met = bool(fuel_windows) and all(fw["confirmed"] for fw in fuel_windows)

    # Day-level child-safe electrolyte DECISION (boolean only). Pop the engine flag off
    # `daily` so the FuelMetrics daily object stays the 5 canonical keys. Rest days never
    # set it → defaults False → no chip. NO mg / reason / number is emitted to mobile here;
    # the chip's text is a mobile placeholder pending RDN copy.
    electrolyte_needed = bool(daily.pop("electrolytes_needed", False))

    return {
        "target_source":    target_source,
        "daily":            daily,
        "confirmed_totals": confirmed_totals,
        "windows":          fuel_windows,
        "daily_met":        daily_met,
        "electrolyte":      {"needed": electrolyte_needed},
    }


def build_today_view(athlete_id: int, conn, today: str | None = None, force_v2: bool = False, now=None) -> dict | None:
    from api.services.nutrition_analysis import get_week_start, get_week_dates
    from api.services.window_templates import generate_windows_for_day

    # INVARIANT: use the client's local date so timezone-shifted athletes
    # see the correct day's windows. Falls back to server UTC if not provided.
    today_str = today or date.today().isoformat()
    _ensure_window_logs_table(conn)

    ath = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
    if not ath:
        return None
    athlete = dict(ath)

    events = [dict(r) for r in conn.execute(
        "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time",
        (athlete_id, today_str),
    ).fetchall()]
    def _fmt_12h(t: str | None) -> str | None:
        if not t:
            return None
        from datetime import datetime as _dt
        return _dt.strptime(t, "%H:%M").strftime("%-I:%M %p")

    def _build_today_event_info(ev: dict) -> dict:
        from datetime import datetime as _dt, timedelta as _td
        st  = ev.get("start_time")
        dur = ev.get("duration_hours") or 1.5
        end_str = None
        if st:
            end_dt  = _dt.strptime(st, "%H:%M") + _td(hours=dur)
            end_str = end_dt.strftime("%H:%M")
        return {
            "event_type":     ev["event_type"],
            "event_name":     ev.get("event_name"),
            "start_time":     st,
            "duration_hours": ev.get("duration_hours"),
            "start_display":  _fmt_12h(st),
            "end_display":    _fmt_12h(end_str),
        }

    today_events = [_build_today_event_info(ev) for ev in events]
    today_event  = events[0] if events else None  # backward compat

    # Window engine — day_layout (DAY_LAYOUT_V2) replaces window_engine_v2 for Today
    # when enabled; legacy generate_windows_for_day otherwise.
    from api.services.day_layout import (
        build_day_layout, cards_to_template_windows, day_layout_v2_enabled,
    )
    if day_layout_v2_enabled():
        from datetime import datetime as _dt
        effective_now = now if now is not None else _dt.now()
        _layout = build_day_layout(events, athlete, now=effective_now)
        event_type       = _layout["day_type"]
        template_windows = cards_to_template_windows(_layout["cards"], today_str)
        # Flag-ON targets: real event_type + resolved activity_type so event days get
        # event-level macros and per-type modifiers apply (Plan D). Legacy unchanged.
        _primary = events[0] if events else {}
        event_type_for_targets    = _primary.get("event_type", "rest")
        activity_type_for_targets = resolve_activity_type(_primary, effective_now) if _primary else None
    else:
        engine_result    = generate_windows_for_day(athlete_id, today_str, events, force_v2=force_v2)
        event_type       = engine_result["day_type"]
        template_windows = engine_result["windows"]
        event_type_for_targets    = event_type   # legacy: day_type label, unchanged
        activity_type_for_targets = None

    plan_rows = conn.execute(
        "SELECT id, slot_name, logged FROM meal_plans WHERE athlete_id = %s AND plan_date = %s",
        (athlete_id, today_str),
    ).fetchall()
    logged_map = {r["slot_name"]: {"id": r["id"], "logged": bool(r["logged"])} for r in plan_rows}

    # window_logs: photo/text/voice capture records for today
    wl_rows = conn.execute(
        "SELECT * FROM window_logs WHERE athlete_id = %s AND log_date = %s",
        (athlete_id, today_str),
    ).fetchall()
    wl_map = {r["window_id"]: dict(r) for r in wl_rows}

    # Confirmation taps ("I Ate This") — queried once here so both the window
    # status builder and the fuel gauge block can use the same set.
    confirmed_keys = {
        r["window_key"] for r in conn.execute(
            "SELECT window_key FROM confirmations WHERE athlete_id = %s AND log_date = %s",
            (athlete_id, today_str),
        ).fetchall()
    }

    # Compute daily macro targets once for per-window breakdown
    _ev0 = events[0] if events else {}
    _dur_min = (_ev0.get("duration_hours") or 0) * 60
    _intensity = _ev0.get("intensity")
    _daily_targets = calc_daily_targets(athlete, event_type_for_targets, _intensity, _dur_min,
                                        activity_type=activity_type_for_targets)
    _daily_carbs   = _daily_targets.get("carbs_g") or _daily_targets.get("carbs_g_max")
    _daily_protein = _daily_targets.get("protein_g") or _daily_targets.get("protein_g_max")

    tappable: list[dict] = []
    nudges:   list[dict] = []
    for tw in template_windows:
        sn     = tw["key"]
        sort_t = tw.get("sort_time", "")
        if tw.get("is_nudge_only"):
            # Short between_games windows (< 25-min gap, demoted to non-tappable by
            # guardrail 2) surface as informational nudges so the athlete sees a
            # "grab something quick" signal between back-to-back games. All other
            # nudge categories (fuel_during) remain invisible on Today.
            if tw.get("category") == "between_games":
                od = tw.get("open_dt")
                cd = tw.get("close_dt")
                nudges.append({
                    "id":            None,
                    "slot_name":     sn,
                    "display_label": tw["label"],
                    "eat_by_time":   tw.get("time_display", ""),
                    "open_time":     od.strftime("%H:%M") if od else "",
                    "close_time":    cd.strftime("%H:%M") if cd else "",
                    "macro_focus":   tw.get("macro_focus", "Fast Carbs + Fluid"),
                    "logged":        False,
                    "window_type":   "nudge",
                    "sort_time":     sort_t,
                    "status":        "nudge",
                    "log":           {"logged": False, "method": None,
                                      "photo_thumb_url": None, "nutrient_status": "none"},
                })
            elif tw.get("category") == "event":
                nudges.append({
                    "id":            None,
                    "slot_name":     sn,
                    "display_label": tw["label"],
                    "eat_by_time":   tw.get("time_display", ""),
                    "open_time":     "",
                    "close_time":    "",
                    "macro_focus":   "",
                    "logged":        False,
                    "window_type":   "event",
                    "sort_time":     sort_t,
                    "status":        "event",
                    "log":           {"logged": False, "method": None,
                                      "photo_thumb_url": None, "nutrient_status": "none"},
                })
            elif tw.get("category") == "keep_going":
                nudges.append({
                    "id":            None,
                    "slot_name":     sn,
                    "display_label": tw["label"],
                    "eat_by_time":   tw.get("time_display", ""),
                    "open_time":     "",
                    "close_time":    "",
                    "macro_focus":   tw.get("macro_focus", ""),
                    "logged":        False,
                    "window_type":   "keep_going",
                    "sort_time":     sort_t,
                    "status":        "nudge",
                    "log":           {"logged": False, "method": None,
                                      "photo_thumb_url": None, "nutrient_status": "none"},
                })
            continue
        plan_info = logged_map.get(sn, {})
        wl        = wl_map.get(sn)
        # logged = True if "I Ate This" tapped, captured via window_logs, or Meal Plan marked done
        logged    = (sn in confirmed_keys) or bool(wl is not None) or bool(plan_info.get("logged", False))
        od = tw.get("open_dt")
        cd = tw.get("close_dt")
        # Prefer the window's own macro_focus when it's a recognized split key
        # (day_layout path); otherwise derive from the slot key (legacy path).
        _tw_focus = tw.get("macro_focus")
        focus = _tw_focus if _tw_focus in _FOCUS_MACRO_PCT else get_macro_focus(sn)
        tappable.append({
            "id":            plan_info.get("id"),
            "slot_name":     sn,
            "display_label": tw["label"],
            "eat_by_time":   tw["time_display"],
            # Additive 24h timing fields (eat_by_time display string is unchanged).
            # Lets the client gate per-window confirm by now vs open/close.
            "open_time":     od.strftime("%H:%M") if od else "",
            "close_time":    cd.strftime("%H:%M") if cd else "",
            "macro_focus":   focus,
            "carbs_g":       round(_daily_carbs   * _FOCUS_MACRO_PCT.get(focus, {"carbs_pct": 0.15})["carbs_pct"])   if _daily_carbs   else None,
            "protein_g":     round(_daily_protein * _FOCUS_MACRO_PCT.get(focus, {"protein_pct": 0.15})["protein_pct"]) if _daily_protein else None,
            "logged":        logged,
            "sort_time":     sort_t,
            "log": {
                "logged":          logged,
                "method":          wl["method"] if wl else None,
                "photo_thumb_url": wl["thumb_url"] if wl else None,
                "nutrient_status": wl["nutrient_status"] if wl else "none",
            },
        })

    tappable = assign_window_status(tappable)

    # Readiness is scored only on confirmable (tappable) windows — nudges don't count.
    logged_count = sum(1 for w in tappable if w.get("logged"))
    readiness = compute_readiness(logged_count, len(tappable), event_type)

    # Merge and sort chronologically; nudge windows bypass status assignment.
    windows = sorted(tappable + nudges, key=lambda w: w.get("sort_time", ""))

    next_game_row = conn.execute(
        "SELECT * FROM events WHERE athlete_id = %s AND event_date > %s "
        "AND event_type IN ('game', 'tournament') ORDER BY event_date LIMIT 1",
        (athlete_id, today_str),
    ).fetchone()
    next_game = None
    if next_game_row:
        ng = dict(next_game_row)
        days_away = (date.fromisoformat(ng["event_date"]) - date.today()).days
        next_game = {
            "event_date": ng["event_date"],
            "event_type": ng["event_type"],
            "event_name": ng.get("event_name"),
            "start_time": ng.get("start_time"),
            "days_away":  days_away,
        }

    # Does this athlete have ANY events ever? Distinguishes a genuine rest day
    # from a never-set-up schedule (both otherwise look identical on Today).
    has_schedule = conn.execute(
        "SELECT COUNT(*) AS count FROM events WHERE athlete_id = %s", (athlete_id,)
    ).fetchone()["count"] > 0

    week_start_str = get_week_start()
    week_dates     = get_week_dates(week_start_str)
    DAY_ABBR       = ["M", "T", "W", "T", "F", "S", "S"]
    readiness_grid = []
    for i, d in enumerate(week_dates):
        d_ev = conn.execute(
            "SELECT event_type, start_time, duration_hours FROM events WHERE athlete_id = %s AND event_date = %s LIMIT 1",
            (athlete_id, d),
        ).fetchone()
        d_et  = d_ev["event_type"] if d_ev else "rest"
        d_st  = d_ev["start_time"] if d_ev else None
        d_dur = d_ev["duration_hours"] if d_ev else None
        d_slots = [s for s in compute_meal_slots(d_et, d_st, d_dur)
                   if not s.get("is_hydration") and not s.get("double_day_alert")]
        d_total = len(d_slots)
        d_logged = conn.execute(
            "SELECT COUNT(*) as cnt FROM meal_plans WHERE athlete_id = %s AND plan_date = %s AND logged = 1",
            (athlete_id, d),
        ).fetchone()["cnt"]

        score = None
        if d <= today_str and d_total > 0:
            bonus = round(35 * (d_logged / d_total))
            score = max(40, min(100, 55 + bonus))

        readiness_grid.append({"date": d, "day": DAY_ABBR[i], "score": score, "is_today": d == today_str})

    from api.services.streak_service import get_streak

    result = {
        "athlete":        {"first_name": athlete["first_name"], "sport": athlete.get("sport", "soccer")},
        "today_event":    today_event,
        "today_events":   today_events,
        "day_type":       event_type,
        "readiness":      readiness,
        "windows":        windows,
        "next_game":      next_game,
        "has_schedule":   has_schedule,
        "readiness_grid": readiness_grid,
        "streak":         get_streak(athlete_id, conn, today_str),
    }

    # Performance Plate — flag gate. ADDITIVE like the gauge: the field is added
    # ONLY when the flag is on, so a flag-off payload stays byte-identical to
    # production. The client reads absent/false as "off" (no plate expander, no
    # per-window fetch).
    try:
        from api.services.plate_config import performance_plate_enabled
        if performance_plate_enabled():
            result["performance_plate_enabled"] = True
    except Exception:
        pass

    # Fuel Gauge — ADDITIVE and flag-gated. When FUEL_GAUGE_ENABLED is off, the
    # block is never added, so the payload is byte-identical to production. No
    # gauges without a schedule (T4). Wrapped so a gauge fault can never break the
    # LIVE Today payload — on any error we omit the block and serve Today as-is.
    try:
        from api.services import fueling_targets as _ft
        if _ft.fuel_gauge_enabled() and has_schedule:
            # A window is confirmed via the Today confirm tap (confirmations table)
            # OR a CaptureSheet log (window_logs, carried on each window's `logged`).
            # confirmed_keys already computed above (shared with window status builder).
            result["fuel_targets"] = _build_fuel_targets_block(
                athlete, events, windows, tappable, template_windows, confirmed_keys
            )
    except Exception:
        log.exception("fuel_targets assembly failed — serving Today without it")

    return result
