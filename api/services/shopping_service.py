"""
Shopping / Fueling Essentials service.

Key invariant: schedule classification MUST use determine_day_type() from
window_templates — the single source of truth for event → day-type mapping.
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
    "other":         "Other",
}

CATEGORY_ORDER = ["breakfast", "pre_fuel", "recovery", "hydration", "dinner_staple", "other"]

_GAME_DAY_TYPES = frozenset({
    "morning_game", "afternoon_game", "evening_event", "early_game", "tournament"
})
_PRACTICE_DAY_TYPES = frozenset({
    "practice_morning", "practice_evening", "double_training"
})


# ── Week classification ───────────────────────────────────────────────────────

def classify_week(events_by_day: dict) -> dict:
    """
    events_by_day: {date_str: [event_dict, ...]} for each of the 7 days.
    Returns a classification dict with counts, flags, and header line.
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

def fetch_week_events(athlete_id: int, week_start: str, conn) -> dict:
    """Return {date_str: [event_dict, ...]} for the 7 days starting week_start.
    week_start is Sunday-anchored, matching api/utils/week.py's get_week_start()
    and the mobile client's own getWeekStart() (WEEK_STARTS_ON=0) — the only
    real caller of this shopping endpoint."""
    sunday = date.fromisoformat(week_start)
    result: dict = {}
    for i in range(7):
        day = (sunday + timedelta(days=i)).isoformat()
        rows = conn.execute(
            "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time",
            (athlete_id, day),
        ).fetchall()
        result[day] = [dict(r) for r in rows]
    return result


# ── Essentials generation ─────────────────────────────────────────────────────

# week_start is Sunday-anchored (see fetch_week_events) — day 0 is Sunday.
# This previously started "Mon", mislabeling every day in the strip by one.
_DAY_ABBRS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _week_tier(game_count: int, practice_count: int) -> tuple[str, str]:
    total = game_count + practice_count
    if game_count >= 2 or total >= 4:
        return "heavy", "Heavy week — stock up on pre-game and recovery fuel."
    if total >= 2:
        return "moderate", "Active week — keep pre-game snacks and recovery food handy."
    return "light", "Light week — focus on everyday fuel and good sleep."


def _focus(classification: dict) -> tuple[str | None, str | None]:
    if classification["has_game"]:
        return "pre_fuel", "Pre-game meals matter most this week."
    if classification["practice_count"] > 0:
        return "recovery", "Fast recovery fuel after every session."
    return None, None


def build_essentials(athlete_id: int, week_start: str, conn) -> dict:
    """
    Main entry point for GET /api/shopping/essentials.
    Returns header + grouped food suggestions, filtered by athlete prefs.
    """
    events_by_day = fetch_week_events(athlete_id, week_start, conn)
    classification = classify_week(events_by_day)
    active_cats = _active_categories(classification)

    # Athlete + parent names
    athlete_row = conn.execute(
        "SELECT first_name, parent_id FROM athletes WHERE id = ?", (athlete_id,)
    ).fetchone()
    athlete_name = dict(athlete_row)["first_name"] if athlete_row else "Athlete"
    parent_id    = dict(athlete_row)["parent_id"]   if athlete_row else None
    parent_row   = conn.execute(
        "SELECT full_name FROM parents WHERE id = ?", (parent_id,)
    ).fetchone() if parent_id else None
    parent_name  = dict(parent_row)["full_name"].split()[0] if parent_row else "Parent"

    # Week tier
    week_tier, tier_line = _week_tier(
        classification["game_count"], classification["practice_count"]
    )

    # Day strip (Sun–Sat with day type)
    sunday = date.fromisoformat(week_start)
    day_types = classification["day_types"]
    day_strip = [
        {
            "date":  (sunday + timedelta(days=i)).isoformat(),
            "label": _DAY_ABBRS[i],
            "type":  day_types[i] if i < len(day_types) else "rest",
        }
        for i in range(7)
    ]

    focus_category, focus_line = _focus(classification)

    # Load athlete preferences
    pref_rows = conn.execute(
        "SELECT food_name, preference, category FROM athlete_food_prefs WHERE athlete_id = ?",
        (athlete_id,),
    ).fetchall()
    excluded = {r["food_name"] for r in pref_rows if r["preference"] in ("disliked", "allergic")}
    liked = [
        {
            "name":          r["food_name"],
            "category":      r["category"],
            "soft_hint":     "",
            "allergen_tags": [],
            "source":        "personal",
        }
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
            "athlete_name":   athlete_name,
            "parent_name":    parent_name,
            "week_tier":      week_tier,
            "tier_line":      tier_line,
            "day_strip":      day_strip,
            "focus_category": focus_category,
            "focus_line":     focus_line,
        },
        "groups": groups,
    }


# ── Share text generation ─────────────────────────────────────────────────────

def build_share_text(week_start: str, items: list) -> str:
    """Produce plain-text Shopping List for clipboard / share sheet."""
    try:
        monday = date.fromisoformat(week_start)
        header_date = monday.strftime("%-d %b")
    except Exception:
        header_date = week_start

    lines = [f"Fueling2Win Shopping List — Week of {header_date}", ""]

    by_cat: dict = {c: [] for c in CATEGORY_ORDER}
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
