from datetime import date, timedelta
from api.services.today_service import compute_logged_totals, compute_traffic_light

NUTRIENT_LABELS: dict = {
    "iron_mg":    ("🩸", "Iron",          "mg"),
    "calcium_mg": ("🦴", "Calcium",       "mg"),
    "carbs_g":    ("⚡",  "Carbohydrates", "g"),
    "protein_g":  ("💪", "Protein",       "g"),
    "water_oz":   ("💧", "Hydration",     "oz"),
    "calories":   ("🔥", "Calories",      "kcal"),
}

FIX_FOODS: dict = {
    "iron_mg": [
        {"food": "🥩 Lean beef or ground turkey at lunch",                         "gain": "+3.5mg"},
        {"food": "🫘 Lentil soup or chickpeas",                                    "gain": "+4.2mg"},
        {"food": "🥬 Spinach + bell pepper (vitamin C doubles absorption)",         "gain": "+2.1mg"},
    ],
    "calcium_mg": [
        {"food": "🥛 2 glasses of milk daily",                                     "gain": "+600mg"},
        {"food": "🧀 Greek yogurt at breakfast",                                   "gain": "+250mg"},
        {"food": "🧀 Cheese + crackers as a snack",                                "gain": "+200mg"},
    ],
    "water_oz": [
        {"food": "💧 1 glass when waking up",                                      "gain": "+8oz"},
        {"food": "💧 Water bottle at every meal",                                  "gain": "+24oz"},
        {"food": "🍋 Sparkling water as afternoon snack",                          "gain": "+12oz"},
    ],
    "carbs_g": [
        {"food": "🍝 Pasta or rice at dinner",                                     "gain": "+80g"},
        {"food": "🍞 Toast + honey before practice",                               "gain": "+45g"},
        {"food": "🍌 Banana + peanut butter before training",                      "gain": "+30g"},
    ],
    "protein_g": [
        {"food": "🥚 2 eggs + Greek yogurt at breakfast",                          "gain": "+25g"},
        {"food": "🐟 Tuna or salmon at lunch",                                     "gain": "+22g"},
        {"food": "🍗 Chicken breast at dinner",                                    "gain": "+30g"},
    ],
    "calories": [
        {"food": "🥜 Peanut butter on toast (extra snack)",                        "gain": "+200kcal"},
        {"food": "🍌 Banana + granola bar",                                        "gain": "+150kcal"},
        {"food": "🥛 Whole milk + almonds",                                        "gain": "+180kcal"},
    ],
}


def score_to_grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 85: return "A−"
    if score >= 80: return "B+"
    if score >= 75: return "B"
    if score >= 70: return "B−"
    if score >= 65: return "C+"
    if score >= 60: return "C"
    if score >= 55: return "C−"
    if score >= 50: return "D+"
    return "D"


def _compute_streak(athlete_id: int, conn) -> int:
    today = date.today()
    streak = 0
    d = today
    for _ in range(365):
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM meal_logs WHERE athlete_id = %s AND logged_at::date = %s",
            (athlete_id, d.isoformat()),
        ).fetchone()
        if row and row["count"] > 0:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    return streak


def _rank_gaps(totals: dict, targets: dict, days: int, gender: str) -> list:
    if days == 0:
        return []
    gaps = []
    for nutrient, (emoji, label, unit) in NUTRIENT_LABELS.items():
        target_total = targets.get(nutrient, 0)
        if not target_total:
            continue
        logged_total = totals.get(nutrient, 0)
        avg_amount   = round(logged_total / days, 1)
        avg_target   = round(target_total  / days, 1)
        avg_pct      = round(min(100, (logged_total / target_total) * 100))
        gaps.append({
            "nutrient":   nutrient,
            "label":      label,
            "emoji":      emoji,
            "unit":       unit,
            "avg_amount": avg_amount,
            "target":     avg_target,
            "avg_pct":    avg_pct,
        })

    gaps.sort(key=lambda g: g["avg_pct"])

    if gender in ("girl", "female"):
        iron = next((g for g in gaps if g["nutrient"] == "iron_mg"), None)
        if iron and iron["avg_pct"] < 75:
            gaps.remove(iron)
            gaps.insert(0, iron)

    return gaps


def build_weekly_report(athlete_id: int, week_start: str, conn) -> dict:
    from api.services.claude_ai import prompt3_weekly_report_v2

    row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
    if not row:
        raise ValueError(f"Athlete {athlete_id} not found")
    athlete = dict(row)

    week_start_date = date.fromisoformat(week_start)
    week_end_date   = week_start_date + timedelta(days=6)
    today_str       = date.today().isoformat()

    # Per-day data
    raw_days: list         = []   # enriched per-day dicts used to build dots
    week_fuel_scores: list = []
    nutrient_totals: dict  = {}
    nutrient_targets: dict = {}
    days_with_data         = 0
    game_days              = 0

    for i in range(7):
        day_str  = (week_start_date + timedelta(days=i)).isoformat()
        day_date = date.fromisoformat(day_str)
        abbr     = day_date.strftime("%a")[:2]
        is_today  = day_str == today_str
        is_future = day_date > date.today()

        targets_row = conn.execute(
            "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
            (athlete_id, day_str),
        ).fetchone()

        event_row = conn.execute(
            "SELECT event_type, event_name FROM events WHERE athlete_id = %s AND event_date = %s",
            (athlete_id, day_str),
        ).fetchone()
        event_type = event_row["event_type"] if event_row else None

        if event_type in ("game", "tournament"):
            game_days += 1
            day_type = "game"
        elif event_type in ("practice", "training", "strength"):
            day_type = "practice"
        else:
            day_type = "rest"

        # Window logs count → confirmed_count for the dot
        wl_row = conn.execute(
            "SELECT COUNT(DISTINCT slot_name) AS count FROM window_logs WHERE athlete_id = %s AND logged_at::date = %s",
            (athlete_id, day_str),
        ).fetchone()
        confirmed_count = wl_row["count"] if wl_row else 0

        # Fall back to meal_logs if no window_logs
        if confirmed_count == 0:
            ml_row = conn.execute(
                "SELECT COUNT(*) AS count FROM meal_logs WHERE athlete_id = %s AND logged_at::date = %s",
                (athlete_id, day_str),
            ).fetchone()
            if ml_row and ml_row["count"] > 0:
                confirmed_count = 1

        # Past days always have at least one applicable window; future days have none
        applicable_count = 0 if is_future else 1

        meal_rows = conn.execute(
            "SELECT * FROM meal_logs WHERE athlete_id = %s AND logged_at::date = %s",
            (athlete_id, day_str),
        ).fetchall()

        fuel_score = None
        if targets_row and meal_rows:
            logged = compute_logged_totals([dict(m) for m in meal_rows])
            tl     = compute_traffic_light(dict(targets_row), logged)
            fuel_score = tl.get("daily_fuel_score")
            if fuel_score is not None:
                week_fuel_scores.append(fuel_score)
                days_with_data += 1

                for nutrient in NUTRIENT_LABELS:
                    nutrient_totals[nutrient] = (
                        nutrient_totals.get(nutrient, 0) + (logged.get(nutrient) or 0)
                    )

                t = dict(targets_row)
                target_map = {
                    "calories":   t.get("total_calories", 0),
                    "carbs_g":    t.get("carbs_g_max", 0),
                    "protein_g":  t.get("protein_g_max", 0),
                    "iron_mg":    t.get("iron_mg", 0),
                    "calcium_mg": t.get("calcium_mg", 0),
                    "water_oz":   t.get("hydration_oz_min", 0),
                }
                for nutrient, val in target_map.items():
                    nutrient_targets[nutrient] = (
                        nutrient_targets.get(nutrient, 0) + (val or 0)
                    )

        raw_days.append({
            "date":            day_str,
            "day_abbr":        abbr,
            "day_num":         day_date.day,
            "fuel_score":      fuel_score,
            "event_type":      event_type,
            "day_type":        day_type,
            "confirmed_count": confirmed_count,
            "applicable_count": applicable_count,
            "is_today":        is_today,
            "is_future":       is_future,
        })

    avg_score    = round(sum(week_fuel_scores) / len(week_fuel_scores)) if week_fuel_scores else 0
    letter_grade = score_to_grade(avg_score)
    streak       = _compute_streak(athlete_id, conn)

    ranked_gaps  = _rank_gaps(nutrient_totals, nutrient_targets, days_with_data, athlete["gender"])
    critical_gap = ranked_gaps[0] if ranked_gaps else None

    next_week_start = week_end_date + timedelta(days=1)
    next_week_end   = next_week_start + timedelta(days=6)
    next_events = [
        dict(r) for r in conn.execute(
            "SELECT event_type, event_name, event_date FROM events "
            "WHERE athlete_id = %s AND event_date BETWEEN %s AND %s ORDER BY event_date",
            (athlete_id, next_week_start.isoformat(), next_week_end.isoformat()),
        ).fetchall()
    ]

    narrative = prompt3_weekly_report_v2({
        "athlete":      athlete,
        "week_start":   week_start,
        "avg_score":    avg_score,
        "letter_grade": letter_grade,
        "days_logged":  days_with_data,
        "critical_gap": critical_gap,
        "next_events":  next_events,
        "streak":       streak,
    })

    # Safety flag: iron below 75% for female athletes
    safety_flag = None
    if athlete.get("gender") in ("girl", "female") and critical_gap and critical_gap["nutrient"] == "iron_mg":
        if critical_gap["avg_pct"] < 75:
            safety_flag = {"flag_key": "low_iron", "message": "Iron levels below target this week"}

    # Flatten what_went_well list → single string for narrative
    wwwell_items = narrative.get("what_went_well") or [
        {"text": f"Logged {days_with_data} days this week", "stat": f"{days_with_data}/7"},
    ]
    what_went_well_str = " · ".join(
        item["text"] if isinstance(item, dict) else str(item)
        for item in wwwell_items[:2]
    )

    summary_paragraphs = narrative.get("summary_paragraphs") or []
    next_action_text = summary_paragraphs[2] if len(summary_paragraphs) > 2 else (
        f"Focus on {critical_gap['label'].lower()} next week." if critical_gap else "Keep building your fueling routine."
    )

    # Build dots — the per-day week strip
    dots = [
        {
            "date":             d["date"],
            "day_abbr":         d["day_abbr"],
            "day_num":          d["day_num"],
            "applicable_count": d["applicable_count"],
            "confirmed_count":  d["confirmed_count"],
            "event_type":       d["event_type"],
            "day_type":         d["day_type"],
            "is_today":         d["is_today"],
            "is_future":        d["is_future"],
        }
        for d in raw_days
    ]

    return {
        "week_start": week_start,
        "week_end":   week_end_date.isoformat(),
        "athlete": {
            "id":         athlete["id"],
            "first_name": athlete["first_name"],
            "gender":     athlete["gender"],
        },
        "streak":     streak,
        "disclaimer": "Fueling2Win provides food education guidance — not medical nutrition therapy.",
        "load": {
            "game_days": game_days,
            "is_high":   game_days >= 2,
        },
        "rates": {
            "pre_fuel":  None,
            "recovery":  None,
            "hydration": None,
        },
        "dots": dots,
        "safety_flag": safety_flag,
        "narrative": {
            "what_went_well": what_went_well_str,
            "flag_narrative": narrative.get("critical_gap_why", ""),
            "encouragement":  narrative.get("grade_headline", f"Keep it up, {athlete['first_name']}!"),
        },
        "next_action": {
            "action": next_action_text,
            "reason": narrative.get("critical_gap_why", ""),
        },
    }
