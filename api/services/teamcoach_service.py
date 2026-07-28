"""TeamCoach dashboard data assembly.

All DB reads use get_read_conn() — read-only connection, 3s timeout (decision #3).
Never queries fueling_window_log from a request handler (non-negotiable constraint).
Engagement data comes exclusively from team_engagement_snapshot.
"""
from api.database import get_read_conn

# Decision #1 — Deliberate product decision, not a technical default.
# Decided Mayur Khera, 2026-07-21: consent not enforced for MVP pilot —
# TeamCoach accounts see full roster status regardless of parent opt-in.
# Revisit before scaling beyond pilot.
ENFORCE_CONSENT = False


# Tunable constants — update here without a schema migration.
# Revisit post-pilot based on whether flagged teams match coach intuition.
_ATTENTION_WEIGHT = 2   # weight on week-over-week player-count drop vs gap below threshold
_ATTENTION_FLAG_FLOOR = 0  # flag if attention_score strictly exceeds this value


def get_coach_teams(coach_id: int) -> dict:
    """Return all teams for a coach, enriched with snapshot data and attention scoring.

    Response shape:
      {
        "generated_at": str | None,   # most recent snapshot timestamp across all teams
        "season": str | None,         # season label (shown once on dashboard)
        "teams": [                    # sorted descending by attention_score
          {
            "id": int,
            "name": str,
            "threshold_pct": int,
            "joined_count": int,      # athletes currently on roster_membership
            "roster_count": int,      # from latest snapshot (or joined_count if no snap)
            "current_week": { "players_above_threshold": int, "roster_count": int,
                              "week_start": str } | None,
            "prior_week": { "players_above_threshold": int } | None,
            "attention_score": float, # (threshold_pct - current_pct) + drop*WEIGHT
            "needs_attention": bool,  # true if attention_score > _ATTENTION_FLAG_FLOOR
                                      # AND this roster has at least one real log ever
                                      # (see has_log_data) — a team with zero logging
                                      # pipeline data is "no data yet", not "failing".
            "has_log_data": bool,     # false if fueling_window_log has never had a
                                      # row for anyone on this roster
          }
        ]
      }
    """
    conn = get_read_conn()
    try:
        team_rows = conn.execute(
            """SELECT t.id, t.name, t.season, t.threshold_pct
               FROM teams t
               JOIN coach_team_access cta ON cta.team_id = t.id
               WHERE cta.coach_id = ?
               ORDER BY t.name""",
            (coach_id,),
        ).fetchall()

        result = []
        latest_generated_at = None

        for t in team_rows:
            joined_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM roster_membership WHERE team_id = ?",
                (t["id"],),
            ).fetchone()["cnt"]

            snaps = conn.execute(
                """SELECT week_start, players_above_threshold, roster_count, generated_at
                   FROM team_engagement_snapshot
                   WHERE team_id = ?
                   ORDER BY week_start DESC LIMIT 2""",
                (t["id"],),
            ).fetchall()

            cur = snaps[0] if snaps else None
            prior = snaps[1] if len(snaps) > 1 else None

            if cur and cur["generated_at"]:
                if not latest_generated_at or cur["generated_at"] > latest_generated_at:
                    latest_generated_at = cur["generated_at"]

            roster_count = cur["roster_count"] if cur else joined_count

            if cur and roster_count > 0:
                cur_pct = cur["players_above_threshold"] / roster_count * 100
                prior_count = prior["players_above_threshold"] if prior else cur["players_above_threshold"]
                attention_score = (
                    (t["threshold_pct"] - cur_pct)
                    + (prior_count - cur["players_above_threshold"]) * _ATTENTION_WEIGHT
                )
            else:
                attention_score = float(t["threshold_pct"])  # no snapshot → treat as fully below

            has_log_data = _team_has_any_real_log_data(conn, t["id"])

            result.append({
                "id": t["id"],
                "name": t["name"],
                "threshold_pct": t["threshold_pct"],
                "joined_count": joined_count,
                "roster_count": roster_count,
                "current_week": {
                    "players_above_threshold": cur["players_above_threshold"],
                    "roster_count": cur["roster_count"],
                    "week_start": cur["week_start"],
                } if cur else None,
                "prior_week": {
                    "players_above_threshold": prior["players_above_threshold"],
                } if prior else None,
                "attention_score": round(attention_score, 1),
                "needs_attention": has_log_data and attention_score > _ATTENTION_FLAG_FLOOR,
                "has_log_data": has_log_data,
            })

        result.sort(key=lambda x: x["attention_score"], reverse=True)

        return {
            "generated_at": latest_generated_at,
            "season": team_rows[0]["season"] if team_rows else None,
            "teams": result,
        }
    finally:
        conn.close()


def assert_coach_owns_team(coach_id: int, team_id: int) -> None:
    """Raise 403 if coach does not have access to this team."""
    from fastapi import HTTPException
    conn = get_read_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM coach_team_access WHERE coach_id=? AND team_id=?",
            (coach_id, team_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(403, "Access denied to this team")


def get_roster(team_id: int) -> list[dict]:
    conn = get_read_conn()
    try:
        rows = conn.execute(
            """SELECT a.id AS athlete_id, a.first_name, a.age, a.gender,
                      a.position, a.competition_level,
                      rm.parent_consent_flag, rm.joined_at
               FROM roster_membership rm
               JOIN athletes a ON a.id = rm.athlete_id
               WHERE rm.team_id = ?
               ORDER BY a.first_name""",
            (team_id,),
        ).fetchall()
        result = []
        for r in rows:
            result.append({
                "athlete_id": r["athlete_id"],
                "first_name": r["first_name"],
                "age": r["age"],
                "gender": r["gender"],
                "position": r["position"],
                "competition_level": r["competition_level"],
                "join_status": "joined",
                "logging_status": _logging_status(conn, r["athlete_id"]),
                "last_logged_at": _last_logged(conn, r["athlete_id"]),
                "parent_consent_flag": bool(r["parent_consent_flag"]),
                "joined_at": r["joined_at"],
            })
        return result
    finally:
        conn.close()


def _team_has_any_real_log_data(conn, team_id: int) -> bool:
    """Stopgap for the fact that fueling_window_log (what the snapshot job and
    this file's per-athlete status reads) is fed by a logging pipeline that
    doesn't exist in production yet — the real Today-tab confirm/unconfirm
    flow writes to a different table (confirmations). Until the snapshot
    pipeline is repointed at the real data (tracked separately — this isn't a
    one-line table swap, since the old fixed 6-slot completion math doesn't
    match the current variable-window-count engine), a roster with zero real
    log rows, ever, is "no data yet", not a genuine attention-worthy team."""
    row = conn.execute(
        """SELECT 1 FROM fueling_window_log
           WHERE athlete_id IN (SELECT athlete_id FROM roster_membership WHERE team_id = ?)
           LIMIT 1""",
        (team_id,),
    ).fetchone()
    return row is not None


def _last_logged(conn, athlete_id: int) -> str | None:
    row = conn.execute(
        """SELECT MAX(date) AS last_date FROM fueling_window_log
           WHERE athlete_id = ? AND completed = 1""",
        (athlete_id,),
    ).fetchone()
    return row["last_date"] if row and row["last_date"] else None


def _logging_status(conn, athlete_id: int) -> str:
    """Check for completed fueling-window logs in the past 7 days.
    Returns 'active', 'inactive', or 'no_data'.
    'no_data' is the expected state in production until mobile logging ships.
    """
    row = conn.execute(
        """SELECT COUNT(*) AS cnt
           FROM fueling_window_log
           WHERE athlete_id = ?
             AND completed = 1
             AND date >= date('now', '-7 days')""",
        (athlete_id,),
    ).fetchone()
    if row is None or row["cnt"] == 0:
        any_row = conn.execute(
            "SELECT 1 FROM fueling_window_log WHERE athlete_id = ? LIMIT 1",
            (athlete_id,),
        ).fetchone()
        return "inactive" if any_row else "no_data"
    return "active"


def _compute_current_streak(dates: list) -> int:
    """Consecutive completed days ending on today or yesterday (grace period)."""
    from datetime import date, timedelta
    if not dates:
        return 0
    date_set = set(dates)
    today = date.today()
    cursor = today if today.isoformat() in date_set else today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in date_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _compute_best_streak(dates: list) -> int:
    """Longest consecutive day run across all history."""
    import datetime
    from datetime import timedelta
    if not dates:
        return 0
    sorted_dates = sorted(datetime.date.fromisoformat(d) for d in set(dates))
    if len(sorted_dates) == 1:
        return 1
    best = current = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def get_athlete_detail(team_id: int, athlete_id: int) -> dict | None:
    """Per-athlete engagement detail for the coach detail view.
    Returns engagement/activity metrics only — no nutrition/clinical data.
    Scoped to team_id to prevent cross-team data leakage.
    """
    from datetime import date, timedelta
    conn = get_read_conn()
    try:
        row = conn.execute(
            """SELECT a.id, a.first_name, a.age, a.gender, a.position,
                      a.competition_level, rm.joined_at
               FROM roster_membership rm
               JOIN athletes a ON a.id = rm.athlete_id
               WHERE rm.team_id = ? AND rm.athlete_id = ?""",
            (team_id, athlete_id),
        ).fetchone()
        if not row:
            return None

        logs = conn.execute(
            """SELECT DISTINCT date FROM fueling_window_log
               WHERE athlete_id = ? AND completed = 1
               ORDER BY date DESC""",
            (athlete_id,),
        ).fetchall()
        dates = [r["date"] for r in logs]

        today = date.today()
        week_ago  = (today - timedelta(days=7)).isoformat()
        month_ago = (today - timedelta(days=30)).isoformat()

        return {
            "athlete_id": athlete_id,
            "first_name": row["first_name"],
            "age": row["age"],
            "gender": row["gender"],
            "position": row["position"],
            "competition_level": row["competition_level"],
            "joined_at": row["joined_at"],
            "logging_status": _logging_status(conn, athlete_id),
            "last_logged_at": dates[0] if dates else None,
            "current_streak": _compute_current_streak(dates),
            "best_streak": _compute_best_streak(dates),
            "days_logged_7d":   sum(1 for d in dates if d >= week_ago),
            "days_logged_30d":  sum(1 for d in dates if d >= month_ago),
            "total_days_logged": len(dates),
        }
    finally:
        conn.close()


def get_engagement(team_id: int) -> dict:
    """Read latest two snapshot rows for current + prior week trend.
    Never queries fueling_window_log — reads team_engagement_snapshot only.
    """
    conn = get_read_conn()
    try:
        rows = conn.execute(
            """SELECT week_start, threshold_pct, players_above_threshold,
                      roster_count, generated_at
               FROM team_engagement_snapshot
               WHERE team_id = ?
               ORDER BY week_start DESC
               LIMIT 2""",
            (team_id,),
        ).fetchall()
        if not rows:
            return {"current_week": None, "prior_week": None, "last_updated": None}
        current = dict(rows[0])
        prior = dict(rows[1]) if len(rows) > 1 else None
        return {
            "current_week": current,
            "prior_week": prior,
            "last_updated": current["generated_at"],
        }
    finally:
        conn.close()
