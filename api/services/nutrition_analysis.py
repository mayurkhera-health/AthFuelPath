from datetime import date as dt_date, timedelta
from api.services.today_service import compute_traffic_light, compute_logged_totals, get_athlete_streak
from api.utils.week import get_week_start as _get_week_start_sunday

NUTRIENT_LABELS = {
    "calories":   ("🔥", "Calories"),
    "carbs_g":    ("⚡", "Carbs"),
    "protein_g":  ("💪", "Protein"),
    "iron_mg":    ("🩸", "Iron"),
    "calcium_mg": ("🦴", "Calcium"),
    "water_oz":   ("💧", "Hydration"),
}

WIN_COLORS = {
    "calories": "gold", "carbs_g": "green", "protein_g": "gold",
    "iron_mg": "red", "calcium_mg": "blue", "water_oz": "blue",
}


def get_week_start(reference_date: str = None) -> str:
    d = dt_date.fromisoformat(reference_date) if reference_date else dt_date.today()
    return _get_week_start_sunday(d).isoformat()


def get_week_dates(week_start: str) -> list:
    start = dt_date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def compute_trend(pcts: list) -> str:
    if len(pcts) < 4:
        return "stable"
    mid = len(pcts) // 2
    first = sum(pcts[:mid]) / mid
    second = sum(pcts[mid:]) / (len(pcts) - mid)
    diff = second - first
    if diff > 8:
        return "improving"
    if diff < -8:
        return "declining"
    return "stable"


def _get_day_logged(athlete_id: int, date_str: str, conn):
    """Returns (targets_dict, logged_dict) or (None, None) if no data."""
    targets_row = conn.execute(
        "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
        (athlete_id, date_str),
    ).fetchone()
    meal_rows = conn.execute(
        "SELECT * FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at::timestamp) = %s",
        (athlete_id, date_str),
    ).fetchall()
    if not targets_row or not meal_rows:
        return None, None
    logged = compute_logged_totals([dict(m) for m in meal_rows])
    water_row = conn.execute(
        "SELECT cups FROM water_logs WHERE athlete_id = %s AND log_date = %s",
        (athlete_id, date_str),
    ).fetchone()
    if water_row:
        logged["water_oz"] = round((logged.get("water_oz") or 0) + water_row["cups"] * 8, 1)
    return dict(targets_row), logged


def build_heatmap(athlete_id: int, week_dates: list, conn) -> dict:
    """Returns {nutrient: [pct_or_null, ...]} for 7 days. null = not logged."""
    nutrients = ["iron_mg", "calcium_mg", "carbs_g", "protein_g", "calories", "water_oz"]
    heatmap = {n: [] for n in nutrients}
    for date_str in week_dates:
        targets, logged = _get_day_logged(athlete_id, date_str, conn)
        if targets is None:
            for n in nutrients:
                heatmap[n].append(None)
            continue
        tl = compute_traffic_light(targets, logged)
        for n in nutrients:
            heatmap[n].append(tl[n]["pct_met"] if n in tl else None)
    return heatmap


def calculate_weekly_traffic_light(athlete_id: int, week_dates: list, conn) -> dict:
    """Aggregates per-day traffic light into weekly averages. Only includes logged days."""
    nutrients = ["iron_mg", "calcium_mg", "carbs_g", "protein_g", "calories", "water_oz"]
    accum = {n: {"pcts": [], "amounts": [], "target": 0} for n in nutrients}
    for date_str in week_dates:
        targets, logged = _get_day_logged(athlete_id, date_str, conn)
        if targets is None:
            continue
        tl = compute_traffic_light(targets, logged)
        for n in nutrients:
            if n in tl:
                accum[n]["pcts"].append(tl[n]["pct_met"])
                accum[n]["amounts"].append(tl[n]["logged"])
                accum[n]["target"] = tl[n]["target"]
    result = {}
    for n in nutrients:
        pcts = accum[n]["pcts"]
        amounts = accum[n]["amounts"]
        if pcts:
            result[n] = {
                "weekly_avg_pct": round(sum(pcts) / len(pcts)),
                "weekly_avg_amount": round(sum(amounts) / len(amounts), 1),
                "target": accum[n]["target"],
                "days_below_target": sum(1 for p in pcts if p < 80),
                "days_logged": len(pcts),
                "trend": compute_trend(pcts),
            }
        else:
            result[n] = {
                "weekly_avg_pct": 0, "weekly_avg_amount": 0,
                "target": accum[n]["target"],
                "days_below_target": 0, "days_logged": 0, "trend": "no_data",
            }
    return result


def rank_weekly_gaps(weekly_tl: dict, gender: str) -> list:
    """Returns nutrients ranked by severity (lowest avg_pct first).
    Iron is always first for girls when avg_pct < 75%."""
    gaps = [
        {
            "nutrient": n,
            "avg_pct": d["weekly_avg_pct"],
            "avg_amount": d["weekly_avg_amount"],
            "target": d["target"],
            "days_below": d["days_below_target"],
            "days_logged": d["days_logged"],
        }
        for n, d in weekly_tl.items()
        if d["days_logged"] > 0
    ]
    gaps.sort(key=lambda g: g["avg_pct"])
    if gender.lower() in ("girl", "female", "f"):
        iron = next((g for g in gaps if g["nutrient"] == "iron_mg"), None)
        if iron and iron["avg_pct"] < 75:
            gaps.remove(iron)
            gaps.insert(0, iron)
    return gaps


def build_wins_list(weekly_tl: dict, streak: dict, athlete_name: str) -> list:
    """Returns up to 4 positive wins. Always returns at least 1."""
    wins = []

    for n, d in weekly_tl.items():
        if len(wins) >= 2:
            break
        if d["days_logged"] >= 2 and d["weekly_avg_pct"] >= 90:
            icon, label = NUTRIENT_LABELS.get(n, ("✓", n))
            wins.append({
                "icon": icon, "color": WIN_COLORS.get(n, "green"),
                "label": f"{label} nailed — every logged day",
                "detail": f"Hit {d['weekly_avg_pct']}% of target on average. Great consistency.",
            })

    if len(wins) < 3:
        for n, d in weekly_tl.items():
            if d["trend"] == "improving" and d["days_logged"] >= 3:
                _, label = NUTRIENT_LABELS.get(n, ("📈", n))
                wins.append({
                    "icon": "📈", "color": "blue",
                    "label": f"{label} trending up all week",
                    "detail": f"At {d['weekly_avg_pct']}% and improving — keep it going.",
                })
                break

    current_streak = streak.get("current_streak", 0)
    best_streak = streak.get("best_streak", 0)
    if current_streak >= 2 and len(wins) < 4:
        is_best = current_streak >= best_streak
        wins.append({
            "icon": "🗓", "color": "purple",
            "label": f"{'Best ever — ' if is_best else ''}{current_streak}-day logging streak",
            "detail": f"Consistency is the hardest part. {athlete_name} is building a real habit.",
        })

    if not wins:
        days = max((d["days_logged"] for d in weekly_tl.values()), default=0)
        wins.append({
            "icon": "📋", "color": "blue",
            "label": f"Showing up — {days} day{'s' if days != 1 else ''} logged this week",
            "detail": f"Every meal logged helps {athlete_name} fuel smarter. Keep going.",
        })

    return wins[:4]
