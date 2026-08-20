"""Daily engagement snapshot generator for TeamCoach.

Reads confirmations (the real Today-tab "I Ate This" log) to compute
per-athlete completion rate for a week, then upserts a summary to
team_engagement_snapshot.

The denominator is NOT a fixed slot count — the window-generation engine
(window_templates.generate_windows_for_day, via scheduled_tap_window_keys)
produces a variable number of confirmable windows per day (1-5, per its
guardrails), so each day's scheduled count is computed from the engine and
summed across the week.

Called by:
  - APScheduler: daily at 11pm PT (api/main.py lifespan)
  - /api/admin/team-coach/teams/{id}/snapshot (manual trigger / backfill)

TeamCoach request handlers NEVER call this — they read team_engagement_snapshot.
"""
from datetime import date, timedelta
from api.database import get_conn
from api.services.window_templates import scheduled_tap_window_keys

DEFAULT_THRESHOLD_PCT = 80


def _current_week_start() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _week_dates(week_start: str) -> list[str]:
    start = date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def generate_snapshot(team_id: int, week_start: str | None = None) -> dict:
    """Compute and upsert snapshot for one team for the given week.
    week_start defaults to the current Monday (ISO format YYYY-MM-DD).
    Returns the computed row as a dict.
    """
    if week_start is None:
        week_start = _current_week_start()

    conn = get_conn()
    try:
        team = conn.execute(
            "SELECT threshold_pct FROM teams WHERE id = %s", (team_id,)
        ).fetchone()
        if not team:
            return {"team_id": team_id, "status": "team_not_found"}

        threshold_pct = team["threshold_pct"]

        roster = conn.execute(
            "SELECT athlete_id FROM roster_membership WHERE team_id = %s",
            (team_id,),
        ).fetchall()
        roster_count = len(roster)

        if roster_count == 0:
            _upsert(conn, team_id, week_start, threshold_pct, 0, 0)
            return {
                "team_id": team_id, "week_start": week_start,
                "threshold_pct": threshold_pct,
                "roster_count": 0, "players_above_threshold": 0,
            }

        athlete_ids = [r["athlete_id"] for r in roster]
        week_dates = _week_dates(week_start)
        week_end = week_dates[-1]
        placeholders = ",".join(["%s"] * len(athlete_ids))
        confirmed = conn.execute(
            f"""SELECT athlete_id, COUNT(*) AS total_confirmed
                FROM confirmations
                WHERE athlete_id IN ({placeholders})
                  AND log_date >= %s
                  AND log_date <= %s
                GROUP BY athlete_id""",
            (*athlete_ids, week_start, week_end),
        ).fetchall()
        confirmed_map = {r["athlete_id"]: r["total_confirmed"] for r in confirmed}

        above = 0
        for aid in athlete_ids:
            total_scheduled = sum(
                len(scheduled_tap_window_keys(aid, d, conn)) for d in week_dates
            )
            completed = confirmed_map.get(aid, 0)
            if total_scheduled > 0:
                pct = 100 * completed / total_scheduled
                if pct >= threshold_pct:
                    above += 1

        _upsert(conn, team_id, week_start, threshold_pct, above, roster_count)
        return {
            "team_id": team_id,
            "week_start": week_start,
            "threshold_pct": threshold_pct,
            "roster_count": roster_count,
            "players_above_threshold": above,
        }
    finally:
        conn.close()


def _upsert(conn, team_id, week_start, threshold_pct, above, roster_count):
    conn.execute(
        """INSERT INTO team_engagement_snapshot
               (team_id, week_start, threshold_pct, players_above_threshold, roster_count)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT(team_id, week_start) DO UPDATE SET
               threshold_pct=excluded.threshold_pct,
               players_above_threshold=excluded.players_above_threshold,
               roster_count=excluded.roster_count,
               generated_at=sqlite_now()""",
        (team_id, week_start, threshold_pct, above, roster_count),
    )
    conn.commit()


def generate_all_snapshots() -> None:
    """Regenerate snapshot for every team. Called by daily APScheduler job."""
    conn = get_conn()
    try:
        team_ids = [r["id"] for r in conn.execute("SELECT id FROM teams").fetchall()]
    finally:
        conn.close()
    for tid in team_ids:
        generate_snapshot(tid)
