"""
Fuel IQ Streak — a genuinely separate streak from api/services/streak_service.py.

That module tracks "did you log a fuel window" (meal confirmations). This one
tracks "did you do something in Fuel IQ" — a lesson completion counts as a
qualifying day. The two are intentionally not conflated: a meal-logging
streak and a learning streak measure different behaviors.

(The Daily Challenge feature has its own separate streak entirely — see
api/services/fueliq_daily_challenge_service.py — deliberately not folded into
this one, since "did you learn a lesson" and "did you do today's daily
challenge" are different habits worth tracking independently.)

current/best streak are always computed live from fueliq_lesson_completions —
never cached — mirroring streak_service's own never-drift guarantee.
fueliq_athlete_progress stores only the non-derivable state (freeze tokens,
last-celebrated milestone), same split as streak_state.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from api.services import fueliq_service as fq

# Lesson streak dates are anchored to PST, matching the daily-challenge streak
# (fueliq_daily_challenge_service.py). The server runs UTC on Fly.io, so
# datetime('now') in SQLite returns UTC — we convert stored timestamps to PST
# local dates before comparing, so a lesson completed at 11 PM PST lands on
# the correct calendar day rather than the next UTC day.
_PST = ZoneInfo("America/Los_Angeles")


def _today_pst() -> date:
    return datetime.now(_PST).date()


MILESTONES = [7]
DEFAULT_FREEZE_TOKENS = 1


def _as_date(value) -> date:
    if value is None:
        return _today_pst()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _qualifying_dates(athlete_id: int, conn) -> set:
    """Set of PST-local YYYY-MM-DD strings the athlete completed a lesson on.

    completed_at is stored as UTC (SQLite's datetime('now') on Fly.io). Converting
    to PST before extracting the date means a lesson logged at 11 PM PST lands on
    the correct local calendar day, not the next UTC day."""
    rows = conn.execute(
        "SELECT completed_at FROM fueliq_lesson_completions WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchall()
    result = set()
    for r in rows:
        try:
            utc_dt = datetime.fromisoformat(r["completed_at"]).replace(tzinfo=ZoneInfo("UTC"))
            result.add(utc_dt.astimezone(_PST).date().isoformat())
        except (ValueError, TypeError):
            pass
    return result


def _best_streak(qual: set) -> int:
    if not qual:
        return 0
    dates = sorted(date.fromisoformat(d) for d in qual)
    best = cur = 1
    for i in range(1, len(dates)):
        cur = cur + 1 if (dates[i] - dates[i - 1]).days == 1 else 1
        best = max(best, cur)
    return best


def _freeze_tokens(athlete_id: int, conn) -> int:
    row = conn.execute(
        "SELECT freeze_tokens FROM fueliq_athlete_progress WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return int(row["freeze_tokens"]) if row else DEFAULT_FREEZE_TOKENS


def compute_current_streak(athlete_id: int, conn, today=None) -> dict:
    """Consecutive qualifying days ending today (or yesterday if today has no
    activity yet — today never breaks the streak). Bridges up to
    `freeze_tokens` missed days within the rolling 7-day window."""
    today_d = _as_date(today)
    qual = _qualifying_dates(athlete_id, conn)
    max_bridges = _freeze_tokens(athlete_id, conn)
    bridges_used = 0
    pending_bridges = 0

    anchor = today_d if today_d.isoformat() in qual else today_d - timedelta(days=1)
    streak = 0
    d = anchor
    while streak <= 3650:
        if d.isoformat() in qual:
            streak += 1
            bridges_used += pending_bridges
            pending_bridges = 0
            d -= timedelta(days=1)
            continue
        within_7 = d >= today_d - timedelta(days=6)
        if (bridges_used + pending_bridges) < max_bridges and within_7:
            pending_bridges += 1
            d -= timedelta(days=1)
            continue
        break

    return {"current": streak, "freeze_used_this_week": bridges_used > 0}


def register_activity(athlete_id: int, conn, today=None) -> dict:
    """Write path — call after a lesson completion or myth verdict. Updates
    fueliq_athlete_progress's streak columns and awards the 7-day milestone
    bonus once per crossing (mirrors streak_service.register_confirmation)."""
    fq._ensure_progress_row(athlete_id, conn)
    qual = _qualifying_dates(athlete_id, conn)
    cur = compute_current_streak(athlete_id, conn, today)
    best = max(_best_streak(qual), cur["current"])

    row = conn.execute(
        "SELECT last_celebrated_milestone FROM fueliq_athlete_progress WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    last = int(row["last_celebrated_milestone"])
    reached = max((m for m in MILESTONES if m <= cur["current"]), default=0)

    today_str = _as_date(today).isoformat()
    conn.execute(
        "UPDATE fueliq_athlete_progress SET current_streak = %s, best_streak = %s, "
        "last_activity_date = %s, updated_at = sqlite_now() "
        "WHERE athlete_id = %s",
        (cur["current"], best, today_str, athlete_id),
    )
    conn.commit()

    just = None
    if reached != last:
        conn.execute(
            "UPDATE fueliq_athlete_progress SET last_celebrated_milestone = %s WHERE athlete_id = %s",
            (reached, athlete_id),
        )
        conn.commit()
        if reached > last:
            just = reached
            bonus = int(fq._config_value(conn, "fueliq_streak_milestone_bonus", 15))
            fq._award_points(athlete_id, bonus, conn)

    return {
        "current": cur["current"],
        "best": best,
        "freeze_used_this_week": cur["freeze_used_this_week"],
        "just_reached_milestone": just,
    }
