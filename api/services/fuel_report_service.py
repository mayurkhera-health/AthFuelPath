"""
Fuel Report v2 — built from training load + confirmation taps only.
No meal logging. No nutrient data. Meaningful at zero taps.

Python computes all numbers. Bedrock writes all narrative copy.
"""

import json
from datetime import date as dt_date, timedelta

from api.database import get_conn
from api.services.meal_timing import generate_day_windows
from api.utils.week import get_week_start as _week_start_sunday

# Engine categories that map to confirmation tap types
_CATEGORY_TO_TYPE: dict[str, str] = {
    "fuel_before":   "pre_fuel",
    "quick_snack":   "pre_fuel",   # early-morning pre-event substitute
    "fuel_after":    "recovery",
    "between_games": "recovery",
    # fuel_during → hydration: never tappable, excluded from TAPPABLE_TYPES
    # everyday → not a confirmation window
}

TAPPABLE_TYPES = {"pre_fuel", "recovery"}

DAY_ABBR = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_week_start(reference: dt_date | None = None) -> str:
    d = reference or dt_date.today()
    return _week_start_sunday(d).isoformat()


def _get_week_dates(week_start: str) -> list[str]:
    start = dt_date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def _load_config(conn) -> dict:
    rows = conn.execute("SELECT key, value FROM report_config").fetchall()
    return {r["key"]: r["value"] for r in rows}


def _build_week_skeletons(athlete_id: int, week_dates: list[str], conn) -> dict[str, dict]:
    """Run the window engine once per day for the whole week."""
    out = {}
    for date_str in week_dates:
        try:
            out[date_str] = generate_day_windows(athlete_id, date_str, conn)
        except Exception:
            conn.rollback()
            out[date_str] = {"windows": []}
    return out


def _applicable_windows(skeletons: dict[str, dict]) -> dict[str, list[tuple[str, str]]]:
    """
    Returns {date_str: [(window_key, window_type), ...]} for every tappable window
    the engine generated that day.
    """
    result: dict[str, list] = {}
    for date_str, skeleton in skeletons.items():
        tappable = []
        for w in skeleton.get("windows", []):
            wtype = _CATEGORY_TO_TYPE.get(w.get("category", ""))
            if wtype in TAPPABLE_TYPES:
                tappable.append((w["window_key"], wtype))
        result[date_str] = tappable
    return result


# ── Training load ─────────────────────────────────────────────────────────────

def compute_load(athlete_id: int, week_dates: list[str], conn) -> dict:
    config    = _load_config(conn)
    threshold = int(config.get("load_high_game_days", 3))

    placeholders = ",".join(["%s"] * len(week_dates))
    rows = conn.execute(
        f"SELECT event_date FROM events "
        f"WHERE athlete_id = %s AND event_type IN ('game','tournament') "
        f"AND event_date IN ({placeholders})",
        [athlete_id, *week_dates],
    ).fetchall()
    game_days = len({r["event_date"] for r in rows})

    return {"game_days": game_days, "is_high": game_days >= threshold}


# ── Confirmation rates ────────────────────────────────────────────────────────

def compute_rates(
    athlete_id: int,
    week_dates: list[str],
    applicable: dict[str, list[tuple[str, str]]],
    conn,
) -> dict:
    tally_applicable: dict[str, int] = {"pre_fuel": 0, "recovery": 0}
    tally_confirmed:  dict[str, int] = {"pre_fuel": 0, "recovery": 0}

    for date_str, windows in applicable.items():
        for _key, wtype in windows:
            tally_applicable[wtype] += 1

    if any(tally_applicable.values()):
        placeholders = ",".join(["%s"] * len(week_dates))
        rows = conn.execute(
            f"SELECT log_date, window_key FROM confirmations "
            f"WHERE athlete_id = %s AND log_date IN ({placeholders})",
            [athlete_id, *week_dates],
        ).fetchall()
        confirmed_set = {(r["log_date"], r["window_key"]) for r in rows}

        for date_str, windows in applicable.items():
            for window_key, wtype in windows:
                if (date_str, window_key) in confirmed_set:
                    tally_confirmed[wtype] += 1

    def rate(wtype: str):
        total = tally_applicable[wtype]
        return round(tally_confirmed[wtype] / total, 2) if total else None

    return {
        "pre_fuel":  rate("pre_fuel"),
        "recovery":  rate("recovery"),
        "hydration": None,   # fuel_during never tappable — reserved for future hydration tap
    }


# ── Per-day dot data ──────────────────────────────────────────────────────────

def compute_dots(
    athlete_id: int,
    week_dates: list[str],
    applicable: dict[str, list[tuple[str, str]]],
    skeletons: dict[str, dict],
    conn,
) -> list[dict]:
    today_str = str(dt_date.today())

    placeholders = ",".join(["%s"] * len(week_dates))
    rows = conn.execute(
        f"SELECT log_date, window_key FROM confirmations "
        f"WHERE athlete_id = %s AND log_date IN ({placeholders})",
        [athlete_id, *week_dates],
    ).fetchall()
    confirmed_by_date: dict[str, set] = {}
    for r in rows:
        confirmed_by_date.setdefault(r["log_date"], set()).add(r["window_key"])

    event_rows = conn.execute(
        f"SELECT event_date, event_type FROM events "
        f"WHERE athlete_id = %s AND event_date IN ({placeholders})",
        [athlete_id, *week_dates],
    ).fetchall()
    event_by_date = {r["event_date"]: r["event_type"] for r in event_rows}

    dots = []
    for i, date_str in enumerate(week_dates):
        app_windows    = applicable.get(date_str, [])
        app_keys       = [k for k, _ in app_windows]
        confirmed_keys = confirmed_by_date.get(date_str, set())
        day_type       = skeletons.get(date_str, {}).get("day_type", "rest")

        dots.append({
            "date":             date_str,
            "day_abbr":         DAY_ABBR[i],
            "day_num":          dt_date.fromisoformat(date_str).day,
            "applicable_count": len(app_keys),
            "confirmed_count":  sum(1 for k in app_keys if k in confirmed_keys),
            "event_type":       event_by_date.get(date_str),
            "day_type":         day_type,
            "is_today":         date_str == today_str,
            "is_future":        date_str > today_str,
        })
    return dots


# ── Safety flag ───────────────────────────────────────────────────────────────

# Priority order: first match wins; at most one flag fires per report
_FLAG_CHECKS = [
    (
        "heat_high_load_low_prefuel",
        "pre_fuel",
        "prefuel_rate_low",
        "With a high-activity week, consistent pre-fueling before events is especially important. "
        "Eating 2–3 hours before games helps your athlete maintain energy and focus throughout.",
    ),
    (
        "heat_high_load_low_recovery",
        "recovery",
        "recovery_rate_low",
        "Recovery meals after games and practices rebuild muscle and prepare the body for the next "
        "effort. A busy week makes the post-session recovery window even more critical.",
    ),
    (
        "heat_high_load_low_hydration",
        "hydration",
        "hydration_rate_low",
        "Staying well-hydrated during a high-activity week supports performance and helps the body "
        "recover between sessions.",
    ),
]


def evaluate_safety_flag(load: dict, rates: dict, conn) -> dict | None:
    if not load["is_high"]:
        return None
    config = _load_config(conn)
    for flag_key, rate_key, config_key, message in _FLAG_CHECKS:
        rate = rates.get(rate_key)
        if rate is None:
            continue
        threshold = float(config.get(config_key, 0.5))
        if rate < threshold:
            return {"flag_key": flag_key, "message": message}
    return None


# ── Next action ───────────────────────────────────────────────────────────────

def pick_next_action(rates: dict, load: dict) -> dict:
    scored = {k: v for k, v in rates.items() if v is not None and k in TAPPABLE_TYPES}

    if not scored:
        return {
            "action": "Tap Yes on your fuel windows this week.",
            "reason": "Even one confirmation tap gives us data to coach from.",
        }

    if all(v >= 0.8 for v in scored.values()):
        return {
            "action": "Keep fueling consistently — you're on track.",
            "reason": "All confirmation rates are strong.",
        }

    worst_key  = min(scored, key=lambda k: scored[k])
    worst_rate = scored[worst_key]

    if worst_key == "pre_fuel":
        return {
            "action": "Eat 2–3 hours before every practice and game next week.",
            "reason": f"Pre-fuel rate was {round(worst_rate * 100)}% — the biggest gap to close.",
        }

    return {
        "action": "Have a recovery snack within 30 minutes after each session.",
        "reason": f"Recovery rate was {round(worst_rate * 100)}% — the key window to hit next week.",
    }


# ── Streak ────────────────────────────────────────────────────────────────────

def compute_streak(athlete_id: int, conn) -> int:
    config = _load_config(conn)
    min_confirms = int(config.get("streak_min_confirms_per_day", 1))

    rows = conn.execute(
        "SELECT log_date, COUNT(*) as cnt FROM confirmations "
        "WHERE athlete_id = %s GROUP BY log_date ORDER BY log_date DESC",
        (athlete_id,),
    ).fetchall()
    qualifying = {r["log_date"] for r in rows if r["cnt"] >= min_confirms}

    streak = 0
    check  = dt_date.today()
    while check.isoformat() in qualifying:
        streak += 1
        check -= timedelta(days=1)
    return streak


# ── Narrative (Bedrock) ───────────────────────────────────────────────────────

_COACH_SYSTEM = (
    "You are the Fueling2Win youth sports nutrition coach. Write warm, forward-looking copy "
    "for a youth soccer athlete's weekly Fuel Report. "
    "Rules: no food names, no numbers, no calories, no grams. "
    "Never use: missed, behind, deficit, failed, warning, lacking, critical, bad, poor. "
    "All copy is positive and win-framed. Respond ONLY with valid JSON."
)


def run_fuel_report_prompt(
    athlete_name: str,
    load: dict,
    rates: dict,
    dots: list,
    flag: dict | None,
    next_action: dict,
    streak: int,
) -> dict:
    from api.services.bedrock_client import converse_text, extract_json, is_configured

    prefuel_str  = f"{round(rates['pre_fuel']  * 100)}%" if rates["pre_fuel"]  is not None else "not applicable this week"
    recovery_str = f"{round(rates['recovery']  * 100)}%" if rates["recovery"]  is not None else "not applicable this week"
    confirmed_days = sum(1 for d in dots if d["confirmed_count"] > 0 and not d["is_future"])
    load_str = f"{'HIGH' if load['is_high'] else 'normal'} ({load['game_days']} game/tournament day{'s' if load['game_days'] != 1 else ''})"

    user_prompt = f"""Write {athlete_name}'s weekly Fuel Report narrative.

COMPUTED DATA (do not invent numbers or override these):
- Training load: {load_str}
- Pre-fuel confirmation rate: {prefuel_str}
- Recovery confirmation rate: {recovery_str}
- Days with at least one confirmation tap: {confirmed_days} of 7
- Fueling streak: {streak} consecutive day{"s" if streak != 1 else ""}
- Safety flag active: {"YES — " + flag["flag_key"] if flag else "NO"}
- Next recommended action: {next_action["action"]}

OUTPUT: Return exactly this JSON structure:
{{
  "what_went_well": "1–2 positive sentences celebrating something real from the data above. If rates are low, celebrate the high-activity week or that we have data to work with.",
  "flag_narrative": "If safety flag is active: 1–2 sentences for the PARENT (second person 'Your athlete…'). Factual, amber-toned, never alarming. If NO flag: return empty string.",
  "encouragement": "One forward-looking closing sentence addressed to {athlete_name} by name. Energizing."
}}"""

    fallback = {
        "what_went_well": f"Great effort staying active this week, {athlete_name}.",
        "flag_narrative": flag["message"] if flag else "",
        "encouragement": f"Keep fueling your potential, {athlete_name} — every tap counts.",
    }

    if not is_configured():
        return fallback

    try:
        raw = converse_text(
            system=_COACH_SYSTEM,
            user=user_prompt,
            max_tokens=400,
            temperature=0.65,
        )
        return json.loads(extract_json(raw))
    except Exception:
        return fallback


# ── Main builder ──────────────────────────────────────────────────────────────

def build_fuel_report(athlete_id: int, week_start: str | None = None) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            return None
        athlete_name = dict(row)["first_name"]

        resolved_start = week_start or _get_week_start()
        week_dates     = _get_week_dates(resolved_start)

        # Run window engine once per day, reuse results
        skeletons  = _build_week_skeletons(athlete_id, week_dates, conn)
        applicable = _applicable_windows(skeletons)

        load        = compute_load(athlete_id, week_dates, conn)
        rates       = compute_rates(athlete_id, week_dates, applicable, conn)
        dots        = compute_dots(athlete_id, week_dates, applicable, skeletons, conn)
        flag        = evaluate_safety_flag(load, rates, conn)
        next_action = pick_next_action(rates, load)
        streak      = compute_streak(athlete_id, conn)
        narrative   = run_fuel_report_prompt(
            athlete_name=athlete_name,
            load=load,
            rates=rates,
            dots=dots,
            flag=flag,
            next_action=next_action,
            streak=streak,
        )

        return {
            "athlete":     {"first_name": athlete_name},
            "week_start":  resolved_start,
            "week_end":    week_dates[-1],
            "load":        load,
            "rates":       rates,
            "dots":        dots,
            "safety_flag": flag,
            "narrative":   narrative,
            "next_action": next_action,
            "streak":      streak,
            "disclaimer":  "Fueling2Win provides food education guidance — not medical nutrition therapy.",
        }
    finally:
        conn.close()
