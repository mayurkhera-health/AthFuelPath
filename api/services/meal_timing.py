import re
import copy
from datetime import datetime, timedelta

# ── Day Timeline format (Meal Plan tab) ───────────────────────────────────────

_CATEGORY_BY_SLOT: dict[str, str] = {
    "breakfast":                  "balanced",
    "mid-morning-snack":          "carb",
    "lunch":                      "balanced",
    "afternoon-snack":            "recovery",
    "pre-game-fuel":              "carb",
    "pre-training":               "carb",
    "power-snack":                "carb",
    "halftime-fueling":           "carb",
    "recovery-fuel":              "recovery",
    "recovery-dinner":            "recovery",
    "dinner":                     "balanced",
    "night-fuel":                 "recovery",
    "evening-recovery":           "recovery",
    "between-games":              "recovery",
    "during-game-hydration":      "hydrate",
    "during-practice-hydration":  "hydrate",
    "daily-hydration":            "hydrate",
}

_CATEGORY_LABELS: dict[str, str] = {
    "carb":     "Build on carbs",
    "balanced": "Fuel + rebuild",
    "recovery": "Recovery fuel",
    "hydrate":  "Stay hydrated",
}

_WHY_LINES: dict[str, str] = {
    "carb":     "Carbs before your session keep your legs fresh and your focus sharp.",
    "balanced": "A balanced mix of carbs, protein, and healthy fats sets a solid base.",
    "recovery": "Within 30 min of finishing, protein + carbs kick-start muscle repair.",
    "hydrate":  "Staying ahead of thirst helps maintain output and reduces cramping.",
}


def _display_time_to_sort(eat_by_time: str) -> str:
    """Convert '5:30 PM' or '5:30 PM – 6:00 PM' to 24h 'HH:MM' sort key."""
    if not eat_by_time or eat_by_time == "All day":
        return "99:00"
    match = re.search(r"(\d+):(\d+)\s*(AM|PM)", eat_by_time)
    if not match:
        return "99:00"
    h, m, period = int(match.group(1)), int(match.group(2)), match.group(3)
    h24 = h % 12 + (12 if period == "PM" else 0)
    return f"{h24:02d}:{m:02d}"

from api.services.nutrient_timing_rules import (
    WINDOWS, HYDRATION, CARB_FUELING_THRESHOLD_MINUTES,
)


def _offset(event_date: str, start_time: str, hours: float) -> str:
    if not start_time:
        return event_date
    try:
        dt = datetime.strptime(f"{event_date} {start_time}", "%Y-%m-%d %H:%M")
        return (dt + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return event_date


def get_meal_timing_protocol(event_type: str, event_date: str, start_time: str = None) -> dict:
    norm = event_type.lower()
    if "tournament" in norm:
        steps = _tournament(event_date, start_time)
    elif "game" in norm:
        steps = _game_day(event_date, start_time)
    elif "strength" in norm or "conditioning" in norm:
        steps = _strength(event_date, start_time)
    elif "practice" in norm or "training" in norm or "agility" in norm:
        steps = _practice(event_date, start_time)
    elif "pre-game" in norm:
        steps = _pre_game_day(event_date)
    elif "recovery" in norm or "yoga" in norm:
        steps = _recovery(event_date)
    else:
        steps = _rest_day(event_date)

    return {"event_type": event_type, "event_date": event_date, "protocol": steps}


def _game_day(event_date: str, start_time: str) -> list:
    _rec = WINDOWS["recovery"]
    _cas = WINDOWS["bedtime_casein"]
    _gas = WINDOWS["gas_tank"]
    _top = WINDOWS["top_off"]
    return [
        {"timing": "Night before (7pm)", "when": f"{event_date} (night before 19:00)", "what": "High carb dinner — pasta/rice + protein + milk", "why": "Glycogen loading takes 24–48 hrs — tonight's dinner determines tomorrow's performance (IOC/ACSM).", "recipe": "Power Pasta Bowl (R001)", "recipient": "parent", "critical": True},
        {"timing": "3 hrs before kickoff", "when": _offset(event_date, start_time, _gas["offset_hours"]), "what": "Gas Tank Meal — carbs + protein + OJ", "why": _gas["why"], "recipe": "Tournament Morning Plate (R023)", "recipient": "both"},
        {"timing": "45 min before kickoff", "when": _offset(event_date, start_time, _top["offset_hours"]), "what": "Top-Off Snack — banana or toast + honey", "why": _top["why"], "recipe": "Banana + PB (R006) or Toast + Honey (R007)", "recipient": "teen"},
        {"timing": "Halftime", "when": _offset(event_date, start_time, 0.75), "what": "Orange slices + 16 oz water OR banana + natural sports drink", "why": WINDOWS["during_long"]["why"], "recipe": "Orange Slices (R010) or Banana + Sports Drink (R011)", "recipient": "teen"},
        {"timing": "Within 30 min after final whistle", "when": _offset(event_date, start_time, 2.0), "what": f"Recovery Window — {_rec['gold_standard']}", "why": _rec["why"], "recipe": "Choc Milk Recovery (R013)", "recipient": "both", "critical": True},
        {"timing": "1–2 hrs after game", "when": _offset(event_date, start_time, 3.0), "what": "Recovery meal — protein + carbs + veg + milk", "why": "Continue glycogen restoration; muscle protein synthesis remains elevated for 4–6 hrs post-exercise.", "recipe": "Post-Practice Rebuild Plate (R019)", "recipient": "both"},
        {"timing": "Bedtime", "when": f"{event_date} 21:00", "what": f"Bedtime Casein — {_cas['examples'][0]} or {_cas['examples'][1]}", "why": _cas["why"], "recipe": "Cottage Cheese + Pineapple (R017)", "recipient": "teen"},
    ]


def _strength(event_date: str, start_time: str) -> list:
    _gas = WINDOWS["gas_tank"]
    _top = WINDOWS["top_off"]
    _rec = WINDOWS["recovery"]
    _cas = WINDOWS["bedtime_casein"]
    return [
        {"timing": "2 hrs before", "when": _offset(event_date, start_time, -2), "what": "Gas Tank Meal — rice/pasta + chicken", "why": _gas["why"], "recipe": "Strength Day Protein Plate (R022)", "recipient": "both"},
        {"timing": "30 min before", "when": _offset(event_date, start_time, _top["offset_hours"]), "what": "Top-Off Snack — banana or rice cakes", "why": _top["why"], "recipe": "Rice Cakes + Almond Butter (R009)", "recipient": "teen"},
        {"timing": "During session", "when": "During session", "what": f"Water throughout — {HYDRATION['during']['target_oz_per_15min'][0]}–{HYDRATION['during']['target_oz_per_15min'][1]} oz every 15 min", "why": WINDOWS["during_short"]["why"], "recipe": None, "recipient": "teen"},
        {"timing": "Within 30 min after", "when": _offset(event_date, start_time, 1.5), "what": f"Recovery Window — {_rec['gold_standard']}", "why": _rec["why"], "recipe": "Post-Practice Rebuild Plate (R019)", "recipient": "both", "critical": True},
        {"timing": "Bedtime — MANDATORY", "when": f"{event_date} 21:00", "what": f"Bedtime Casein — {_cas['protein_target_g'][0]}–{_cas['protein_target_g'][1]} g casein", "why": _cas["why"], "recipe": "Cottage Cheese + Pineapple (R017)", "recipient": "teen", "critical": True},
    ]


def _practice(event_date: str, start_time: str) -> list:
    _gas = WINDOWS["gas_tank"]
    _top = WINDOWS["top_off"]
    _rec = WINDOWS["recovery"]
    return [
        {"timing": "3–4 hrs before practice", "when": _offset(event_date, start_time, _gas["offset_hours"]), "what": "Gas Tank Meal — carbs + protein", "why": _gas["why"], "recipe": "Pre-Practice Oatmeal Bowl (R018)", "recipient": "both"},
        {"timing": "30–60 min before practice", "when": _offset(event_date, start_time, _top["offset_hours"]), "what": "Top-Off Snack — banana or toast", "why": _top["why"], "recipe": "Banana + PB (R006)", "recipient": "teen"},
        {"timing": "Within 30 min after practice", "when": _offset(event_date, start_time, 2.0), "what": f"Recovery Window — {_rec['gold_standard']}", "why": _rec["why"], "recipe": "Post-Practice Rebuild Plate (R019)", "recipient": "both", "critical": True},
    ]


def _pre_game_day(event_date: str) -> list:
    return [
        {"timing": "Breakfast", "when": f"{event_date} 08:00", "what": "Carb-rich breakfast", "why": "Pre-game day carb loading begins at breakfast", "recipe": "Pre-Practice Oatmeal Bowl (R018)", "recipient": "both"},
        {"timing": "Lunch", "when": f"{event_date} 12:00", "what": "Large carb + protein meal", "why": "Filling muscle glycogen — takes 24-48hrs to replenish (Everett 2025)", "recipe": "Brown Rice Salmon Bowl (R002)", "recipient": "both"},
        {"timing": "Dinner — MOST IMPORTANT MEAL OF THE WEEK", "when": f"{event_date} 19:00", "what": "HIGH CARB dinner — pasta/rice + lean protein + milk", "why": "This dinner = tomorrow's game performance. Cannot be skipped.", "recipe": "Power Pasta Bowl (R001)", "recipient": "both", "critical": True},
        {"timing": "Bedtime snack", "when": f"{event_date} 21:00", "what": "Greek yogurt or cottage cheese", "why": "Overnight casein + keeps glycogen topped", "recipe": "Cottage Cheese + Pineapple (R017)", "recipient": "teen"},
    ]


def _tournament(event_date: str, start_time: str) -> list:
    return [
        {"timing": "2-3hrs before first game", "when": _offset(event_date, start_time, -2.5), "what": "High carb breakfast — oatmeal/pancakes + protein + OJ", "why": "Multi-game day requires maximum glycogen stores", "recipe": "Tournament Morning Plate (R023)", "recipient": "both"},
        {"timing": "Between games — MANDATORY", "when": "Between each game", "what": "Banana + natural sports drink + whole grain crackers", "why": "Glycogen partially depleted after each game — must refuel immediately", "recipe": "Between-Games Refuel (R024)", "recipient": "both", "critical": True},
        {"timing": "Every 20min during each game", "when": "Throughout tournament", "what": "6-8oz natural sports drink", "why": "Electrolytes MANDATORY on tournament day — sodium critical", "recipe": None, "recipient": "teen", "critical": True},
        {"timing": "Tournament recovery dinner", "when": f"{event_date} 19:00", "what": "High protein + carb dinner + extra hydration", "why": "Multi-game glycogen depletion requires aggressive recovery", "recipe": "Tournament Recovery Dinner (R025)", "recipient": "both"},
        {"timing": "Bedtime — MANDATORY", "when": f"{event_date} 21:00", "what": "Casein protein + carbs", "why": "Multiple games = maximum muscle damage — overnight repair critical", "recipe": "Bedtime Casein Snack (R026)", "recipient": "teen", "critical": True},
    ]


def _recovery(event_date: str) -> list:
    return [
        {"timing": "All day", "when": event_date, "what": "Light carb + anti-inflammatory foods — berries, salmon, turmeric, leafy greens", "why": "Continued glycogen restoration + reduce inflammation from training load", "recipe": "Iron-Boost Hummus Plate (R020)", "recipient": "both"},
        {"timing": "Hydration focus", "when": event_date, "what": "64-72oz water — add electrolytes if previous day was a game", "why": "Rehydration continues 24-48hrs after heavy exercise", "recipe": None, "recipient": "both"},
    ]


def _rest_day(event_date: str) -> list:
    return [
        {"timing": "All meals", "when": event_date, "what": "Slightly lower carbs, maintain protein and micronutrients", "why": "Lower energy expenditure — maintain muscle protein synthesis without surplus", "recipe": None, "recipient": "both"},
        {"timing": "Iron focus (girls)", "when": event_date, "what": "Iron-rich foods — lean red meat, spinach, lentils, fortified cereal", "why": "52% of female adolescent athletes are iron deficient. Daily target: 15mg (Everett 2025)", "recipe": "Iron-Boost Hummus Plate (R020)", "recipient": "both"},
        {"timing": "Calcium — every day", "when": event_date, "what": "3 servings dairy or fortified alternatives", "why": "1,300mg/day during peak bone mass window — cannot recover later (AAP)", "recipe": None, "recipient": "both"},
    ]


# ── compute_meal_slots ─────────────────────────────────────────────────────────

def _time_from_str(t: str) -> datetime:
    return datetime.strptime(t, "%H:%M")


def _add(t: str, hours: float) -> str:
    """Return HH:MM 24h string offset by hours from t."""
    dt = _time_from_str(t) + timedelta(hours=hours)
    return dt.strftime("%H:%M")


def _fmt(t: str) -> str:
    """Format HH:MM 24h string as '4:30 PM' or '1:00 PM'."""
    dt = _time_from_str(t)
    h = dt.hour % 12 or 12
    period = "AM" if dt.hour < 12 else "PM"
    return f"{h}:{dt.minute:02d} {period}"


def _hour(t: str) -> float:
    """Return hour as float (e.g. '19:30' -> 19.5)."""
    dt = _time_from_str(t)
    return dt.hour + dt.minute / 60


def _slot_sort_key(slot):
    """Sort key for chronological ordering of meal slots.

    double_day_alert slots sort first (0).
    Real meal times sort by their parsed time (1, h24, m).
    is_hydration=True, empty eat_by_time, or 'All day' sort last (99, 0).
    """
    if slot.get("double_day_alert"):
        return (0, 0, 0)
    t = slot.get("eat_by_time", "")
    if not t or t == "All day":
        return (99, 0, 0)
    match = re.search(r'(\d+):(\d+)\s*(AM|PM)', t)
    if not match:
        return (50, 0, 0)
    h = int(match.group(1))
    m = int(match.group(2))
    period = match.group(3)
    h24 = h % 12 + (12 if period == "PM" else 0)
    return (1, h24, m)


_REST_SLOTS = [
    {"slot_name": "breakfast",         "display_label": "Breakfast",                          "eat_by_time": "8:30 AM",  "time_note": "Morning meal",             "tags": ["Complex Carbs", "Protein", "Healthy Fats"],     "icon": "🍳", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "practice",          "double_day_alert": False},
    {"slot_name": "mid-morning-snack", "display_label": "Mid-Morning Snack",                  "eat_by_time": "11:00 AM", "time_note": "~10-11 AM",                "tags": ["Quick Carbs", "Light"],                         "icon": "🍎", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "pre-game-snack",    "double_day_alert": False},
    {"slot_name": "lunch",             "display_label": "Lunch",                              "eat_by_time": "1:30 PM",  "time_note": "Midday meal",              "tags": ["High Protein", "Complex Carbs", "Iron-Rich"],   "icon": "🥗", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "meal-prep",          "double_day_alert": False},
    {"slot_name": "afternoon-snack",   "display_label": "Afternoon Snack",                    "eat_by_time": "4:00 PM",  "time_note": "~2-4 PM",                  "tags": ["Protein", "Healthy Fats"],                      "icon": "🥜", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "pre-game-snack",    "double_day_alert": False},
    {"slot_name": "dinner",            "display_label": "Dinner",                             "eat_by_time": "7:00 PM",  "time_note": "Evening meal",             "tags": ["High Protein", "Complex Carbs", "Healthy Fats"], "icon": "🍽️", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "practice",          "double_day_alert": False},
    {"slot_name": "evening-recovery",  "display_label": "Evening Recovery / Pre-Bed Fueling", "eat_by_time": "9:30 PM",  "time_note": "Before bed",               "tags": ["Casein Protein", "Light"],                      "icon": "🌙", "is_hydration": False, "is_merged": False, "note": "", "recipe_category": "post-game-recovery", "double_day_alert": False},
    {"slot_name": "daily-hydration",   "display_label": "Daily Hydration",                    "eat_by_time": "All day",  "time_note": "Water target for the day", "tags": [],                                               "icon": "💧", "is_hydration": True,  "is_merged": False, "note": "", "recipe_category": None,               "double_day_alert": False},
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
    event_type,
    start_time,
    duration_hours,
    double_day=False,
    second_start_time=None,
):
    """
    Return ordered list of meal slot dicts for a given day.
    All slot dicts have keys: slot_name, display_label, eat_by_time, time_note,
    tags, icon, is_hydration, is_merged, note, recipe_category, double_day_alert.
    """
    if not event_type or event_type.lower() == "rest":
        return [copy.deepcopy(s) for s in _REST_SLOTS]

    norm = event_type.lower()
    is_game = "game" in norm or "tournament" in norm

    if not start_time:
        return [copy.deepcopy(s) for s in _REST_SLOTS]

    dur = duration_hours or 1.5
    event_end = _add(start_time, dur)

    # Timing anchors derived from nutrient_timing_rules WINDOWS
    pre_event_time   = _add(start_time, WINDOWS["gas_tank"]["offset_hours"])
    power_snack_time = _add(start_time, WINDOWS["top_off"]["offset_hours"])
    halftime_time    = _add(start_time, 0.75)
    recovery_time    = _add(event_end,  WINDOWS["recovery"]["offset_hours"])

    # Does this session require carb + electrolyte fueling during (>= 75 min)?
    needs_carb_fueling = (dur * 60) >= CARB_FUELING_THRESHOLD_MINUTES or is_game

    is_early_event = _hour(pre_event_time) < 6.0
    is_late_event  = _hour(event_end) >= 19.0

    slots = []

    if double_day:
        slots.append(_make_slot(
            "double-day-alert", "⚡ Double Event Day",
            "", "Two events today — +15% calories",
            [], "⚡", double_day_alert=True,
        ))

    slots.append(_make_slot("breakfast", "Breakfast", "8:30 AM", "Morning meal",
        ["Complex Carbs", "Protein", "Healthy Fats"], "🍳", recipe_category="practice"))
    slots.append(_make_slot("mid-morning-snack", "Mid-Morning Snack", "11:00 AM", "~10-11 AM",
        ["Quick Carbs", "Light"], "🍎", recipe_category="pre-game-snack"))
    slots.append(_make_slot("lunch", "Lunch", "1:30 PM", "Midday meal",
        ["High Protein", "Complex Carbs", "Iron-Rich"], "🥗", recipe_category="meal-prep"))

    if is_early_event:
        # Only emit power snack if it's not before 06:00
        if _hour(power_snack_time) >= 6.0:
            slots.append(_make_slot(
                "power-snack", "Power Snack",
                _fmt(power_snack_time),
                f"45 min before {'kick-off' if is_game else 'training'}",
                ["Quick Carbs"], "🍌",
                note="Early event — light snack only before kick-off",
                recipe_category="pre-game-snack",
            ))
        # else: both pre-event fuel and power snack are before 06:00 — no pre-event fueling
    else:
        label    = "Pre-Game Fuel" if is_game else "Pre-Training Fuel"
        note_str = "3 hrs before kick-off" if is_game else "3 hrs before training"
        slots.append(_make_slot(
            "pre-game-fuel" if is_game else "pre-training",
            label, _fmt(pre_event_time), note_str,
            ["Complex Carbs", "Light Protein"], "⚡",
            recipe_category="pre-game",
        ))
        slots.append(_make_slot(
            "power-snack", "Power Snack",
            _fmt(power_snack_time),
            f"45 min before {'kick-off' if is_game else 'training'}",
            ["Quick Carbs"], "🍌",
            recipe_category="pre-game-snack",
        ))

    if needs_carb_fueling:
        during_tags  = WINDOWS["during_long"]["tags"]
        during_note  = f"30–60 g simple carbs/hr + electrolytes — {WINDOWS['during_long']['why']}"
    else:
        during_tags  = WINDOWS["during_short"]["tags"]
        during_note  = WINDOWS["during_short"]["why"]

    hydration_label = "During Game Hydration" if is_game else "During Practice Hydration"
    slots.append(_make_slot(
        "during-game-hydration" if is_game else "during-practice-hydration",
        hydration_label,
        f"{_fmt(start_time)} – {_fmt(event_end)}",
        "Electrolytes + fluids" if needs_carb_fueling else "Water only",
        during_tags, "💦",
        is_hydration=True,
        note=during_note,
    ))

    if is_game and "tournament" not in norm:
        slots.append(_make_slot(
            "halftime-fueling", "Halftime Fueling",
            _fmt(halftime_time), "At halftime",
            ["Quick Carbs", "Light"], "🍊",
            recipe_category="halftime",
        ))

    if is_late_event:
        slots.append(_make_slot(
            "recovery-dinner", "After Training Recovery Fuel",
            f"After {_fmt(event_end)}",
            "Recovery window — prioritize fuel over a full dinner",
            ["High Protein", "Fast Carbs", "Fluids"], "🔋",
            is_merged=True,
            note="Practice ends at dinner time — recovery nutrition takes priority over a sit-down meal",
            recipe_category="post-game-recovery",
        ))
    else:
        slots.append(_make_slot(
            "recovery-fuel", "Recovery Fuel",
            _fmt(recovery_time), "Within 30 min after event",
            ["Protein", "Fast Carbs"], "🔋",
            recipe_category="post-game-recovery",
        ))
        slots.append(_make_slot(
            "dinner", "Dinner", "7:00 PM", "Evening meal",
            ["High Protein", "Complex Carbs", "Healthy Fats"], "🍽️",
            recipe_category="practice",
        ))
        slots.append(_make_slot(
            "night-fuel", "Night Fuel", "9:00 PM", "Before bed",
            ["Casein Protein", "Light"], "🌙",
            recipe_category="post-game-recovery",
        ))

    if double_day and second_start_time:
        between_time = f"After {_fmt(event_end)} – Before {_fmt(second_start_time)}"
        slots.append(_make_slot(
            "between-games", "Between Games Recovery + Refuel",
            between_time, "Recovery window between games",
            ["Protein", "Fast Carbs", "Electrolytes"], "🔄",
            is_merged=True,
            recipe_category="post-game-recovery",
        ))

    slots.append(_make_slot(
        "daily-hydration", "Daily Hydration", "All day",
        "Water target for the day", [], "💧",
        is_hydration=True,
    ))

    # Sort slots chronologically:
    # - double_day_alert first
    # - real meal times in chronological order
    # - is_hydration / "All day" / empty eat_by_time last
    slots.sort(key=_slot_sort_key)

    return slots


def generate_day_windows(athlete_id: int, plan_date: str, conn, force_v2: bool = False) -> dict:
    """
    Single window engine for the Day Timeline (Meal Plan tab).
    Delegates to window_templates.generate_windows_for_day() — single source of truth.

    Returns skeleton dict: { date, day_type, event, windows[] }
    Callers attach items[] and ideas[] before returning to client.
    """
    from api.services.window_templates import generate_windows_for_day

    event_rows = conn.execute(
        "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time",
        (athlete_id, plan_date),
    ).fetchall()
    events = [dict(r) for r in event_rows]
    first_event = events[0] if events else None

    result              = generate_windows_for_day(athlete_id, plan_date, events, force_v2=force_v2)
    day_type            = result["day_type"]
    tw_list             = result["windows"]
    early_morning_msg   = result.get("early_morning_message")

    def _build_event_info(ev: dict) -> dict | None:
        st = ev.get("start_time")
        if not st:
            return None
        dur = ev.get("duration_hours") or 1.5
        return {
            "label":         ev.get("event_name") or ev["event_type"].capitalize(),
            "start_display": _fmt(st),
            "end_display":   _fmt(_add(st, dur)),
            "sort_time":     st,
        }

    events_info = [info for ev in events if (info := _build_event_info(ev))]
    event_info  = events_info[0] if events_info else None

    windows = []
    for tw in tw_list:
        if tw.get("is_nudge_only"):
            continue
        windows.append({
            "window_id":      f"w_{tw['key']}",
            "window_key":     tw["key"],
            "label":          tw["label"],
            "category":       tw["category"],
            "category_key":   tw["category_key"],
            "category_label": tw["category_label"],
            "time_display":   tw["time_display"],
            "sort_time":      tw["sort_time"],
            "why":            tw["why"],
        })

    return {
        "date":                  plan_date,
        "day_type":              day_type,
        "early_morning_message": early_morning_msg,
        "event":                 event_info,
        "events":                events_info,
        "windows":               windows,
    }
