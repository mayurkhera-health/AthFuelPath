"""
Admin Analytics dashboard — hybrid PostHog + our own SQLite.

Data-source policy:
  • PostHog Query API (HogQL) → top events, WAU/retention, event discovery, and
    a signups probe. Free tier includes the Query API (unlike Mixpanel's).
  • Our SQLite (always available, free) → families total, sync adoption %,
    synced-vs-manual split, problem-report / feature-idea counts, the whole
    activation funnel, and the signups line (parents.created_at — complete).
The dashboard NEVER 500s because PostHog is down: PostHog-sourced cards return
{available: false, reason} and the DB cards always render.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from api.database import get_conn
from api.services import posthog_client
from api.services.admin_auth import require_admin

router = APIRouter()


def _iso_days_ago(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).isoformat()


def _scalar(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return (row["count"] or 0) if row else 0


def _active_where(conn) -> str:
    """WHERE fragment (on the parents table) that excludes anonymized tombstones
    from the old AthFuelPath-Admin soft-delete. account_status only exists in prod, so
    this is '1=1' (no-op) on fresh/test DBs."""
    has_col = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'parents' AND column_name = 'account_status'"
    ).fetchone() is not None
    return "(account_status IS NULL OR account_status != 'hard_deleted')" if has_col else "1=1"


# ── Shared DB metrics (single source of truth — reused by the plain /overview) ─
def db_metrics(conn, days: int = 30) -> dict:
    """Core database-derived analytics. No PostHog, so always fast + available.
    Consumed by /analytics/overview AND the plain-language /overview endpoint."""
    since_30 = _iso_days_ago(days)
    since_7 = _iso_days_ago(7)
    aw = _active_where(conn)                          # excludes deleted parents
    active_ids = f"SELECT id FROM parents WHERE {aw}"
    active_athletes = f"SELECT id FROM athletes WHERE parent_id IN ({active_ids})"

    families_total = _scalar(conn, f"SELECT COUNT(*) AS count FROM parents WHERE {aw}")
    signups_window = _scalar(conn, f"SELECT COUNT(*) AS count FROM parents WHERE created_at >= %s AND {aw}", (since_30,))
    athletes_total = _scalar(conn, f"SELECT COUNT(*) AS count FROM athletes WHERE parent_id IN ({active_ids})")
    athletes_connected = _scalar(conn,
        f"SELECT COUNT(*) AS count FROM athletes WHERE (byga_ics_url IS NOT NULL OR playmetrics_ics_url IS NOT NULL) "
        f"AND parent_id IN ({active_ids})")
    sync_pct = round(100 * athletes_connected / athletes_total) if athletes_total else 0
    active_7d = _scalar(conn, f"""
        SELECT COUNT(DISTINCT athlete_id) AS count FROM (
            SELECT athlete_id FROM meal_logs   WHERE logged_at  >= %s
            UNION SELECT athlete_id FROM window_logs WHERE created_at >= %s
            UNION SELECT athlete_id FROM water_logs  WHERE updated_at >= %s
        ) WHERE athlete_id IN ({active_athletes})""", (since_7, since_7, since_7))
    rows = conn.execute(
        f"SELECT substr(created_at,1,10) AS d, COUNT(*) AS n FROM parents "
        f"WHERE created_at >= %s AND {aw} GROUP BY d ORDER BY d", (since_30,)).fetchall()
    signup_series = [{"date": r["d"], "count": r["n"]} for r in rows]
    problem_7d = _scalar(conn, "SELECT COUNT(*) AS count FROM problem_reports WHERE created_at >= %s", (since_7,)) \
        if _table_exists(conn, "problem_reports") else 0
    ideas_7d = _scalar(conn, "SELECT COUNT(*) AS count FROM feature_requests WHERE submitted_at >= %s", (since_7,)) \
        if _table_exists(conn, "feature_requests") else 0
    src_rows = conn.execute("SELECT COALESCE(source,'manual') AS s, COUNT(*) AS n FROM events GROUP BY s").fetchall()
    event_sources = {r["s"]: r["n"] for r in src_rows}
    return {
        "families_total": families_total, "signups_window": signups_window, "window_days": days,
        "active_7d": active_7d,
        "athletes_total": athletes_total, "athletes_connected": athletes_connected, "sync_pct": sync_pct,
        "signup_series": signup_series,
        "problem_reports_7d": problem_7d, "feature_ideas_7d": ideas_7d, "event_sources": event_sources,
    }


def funnel_steps(conn) -> list:
    """Activation funnel steps (DB-derived). Reused by /overview for the
    calendar-connection and meal-plan counts."""
    aw = _active_where(conn)
    active_ids = f"SELECT id FROM parents WHERE {aw}"
    signed_up = _scalar(conn, f"SELECT COUNT(*) AS count FROM parents WHERE {aw}")
    created_athlete = _scalar(conn, f"SELECT COUNT(DISTINCT parent_id) AS count FROM athletes WHERE parent_id IN ({active_ids})")
    # "Connected calendar" = auto-sync URL OR a one-time uploaded .ics file (uid).
    connected_calendar = _scalar(conn, f"""
        SELECT COUNT(DISTINCT a.parent_id) AS count FROM athletes a
        WHERE a.parent_id IN ({active_ids})
          AND (a.byga_ics_url IS NOT NULL OR a.playmetrics_ics_url IS NOT NULL
            OR EXISTS(SELECT 1 FROM events e WHERE e.athlete_id = a.id AND e.uid IS NOT NULL AND e.uid != ''))""")
    planned = _scalar(conn, f"""
        SELECT COUNT(DISTINCT a.parent_id) AS count FROM athletes a
        WHERE a.parent_id IN ({active_ids})
          AND (EXISTS(SELECT 1 FROM meal_plans mp WHERE mp.athlete_id = a.id)
            OR EXISTS(SELECT 1 FROM meal_plan_selections ms WHERE ms.athlete_id = a.id))""")

    def step(label, value, prev):
        return {"label": label, "value": value,
                "pct_of_start": round(100 * value / signed_up) if signed_up else 0,
                "pct_of_prev": round(100 * value / prev) if prev else 0}
    return [
        step("Signed up", signed_up, signed_up),
        step("Created athlete", created_athlete, signed_up),
        step("Connected calendar", connected_calendar, created_athlete),
        step("Built meal plan", planned, connected_calendar),
    ]


def calendar_platform_breakdown(conn) -> dict:
    """Per-family calendar platform, current-state, DB-sourced (exact, no PostHog,
    no cache staleness). A family is counted once with BYGA-priority: BYGA if any
    of its athletes has a byga_ics_url, else PlayMetrics if any has a
    playmetrics_ics_url, else Not connected. Buckets sum to total families.

    Tiebreak: save_sync_url never clears the other platform's column, so an
    athlete/family can have both — BYGA wins, matching the Users-list
    _calendar_status priority, so each family lands in exactly one bucket."""
    aw = _active_where(conn)
    active_ids = f"SELECT id FROM parents WHERE {aw}"
    byga = _scalar(conn, f"SELECT COUNT(DISTINCT parent_id) AS count FROM athletes "
                         f"WHERE parent_id IN ({active_ids}) AND byga_ics_url IS NOT NULL")
    playmetrics = _scalar(conn,
        f"SELECT COUNT(DISTINCT parent_id) AS count FROM athletes "
        f"WHERE parent_id IN ({active_ids}) AND playmetrics_ics_url IS NOT NULL "
        f"AND parent_id NOT IN (SELECT parent_id FROM athletes WHERE byga_ics_url IS NOT NULL)")
    total = _scalar(conn, f"SELECT COUNT(*) AS count FROM parents WHERE {aw}")
    return {"source": "db", "byga": byga, "playmetrics": playmetrics,
            "not_connected": max(0, total - byga - playmetrics), "total_families": total}


# ── Overview ─────────────────────────────────────────────────────────────────
@router.get("/analytics/overview")
def overview(days: int = 30, force: bool = False, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        m = db_metrics(conn, days)
        calendar_platform = calendar_platform_breakdown(conn)
    finally:
        conn.close()

    # PostHog enrichment (optional). One probe query tells us whether the Query
    # API is actually usable (creds valid + reachable).
    ph_signups = posthog_client.signups_over_time(days, force=force)
    ph_status = {
        "configured": posthog_client.is_configured(),
        "available": bool(ph_signups.get("available")),
        "reason": ph_signups.get("reason"),
    }
    return {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "posthog_available": ph_status["available"],
        "posthog_status": ph_status,
        "cards": {
            "signups": {"value": m["signups_window"], "window_days": m["window_days"], "source": "db"},
            "active_users_7d": {"value": m["active_7d"], "source": "db"},
            "families_total": {"value": m["families_total"], "source": "db"},
            "sync_adoption": {"percent": m["sync_pct"], "connected": m["athletes_connected"],
                              "total": m["athletes_total"], "source": "db"},
        },
        "calendar_platform": calendar_platform,
        "signups_over_time": {"source": "db", "points": m["signup_series"], "posthog": ph_signups},
        "app_health": {"problem_reports_7d": m["problem_reports_7d"],
                       "feature_ideas_7d": m["feature_ideas_7d"], "event_sources": m["event_sources"]},
    }


# ── Activation funnel (DB-derived, always available) ─────────────────────────
@router.get("/analytics/funnel")
def funnel(days: int = 30, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        steps = funnel_steps(conn)
    finally:
        conn.close()
    return {"source": "db", "steps": steps, "note": "All steps derived from our own data."}


# ── Retention / WAU (PostHog, with DB WAU fallback) ──────────────────────────
@router.get("/analytics/retention")
def retention(weeks: int = 8, force: bool = False, _: bool = Depends(require_admin)):
    weeks = max(1, min(12, weeks))
    ph = posthog_client.retention(weeks, force=force)
    if ph.get("available"):
        return {"source": "posthog", "available": True,
                "points": ph["data"]["points"],
                "note": "Weekly active users (distinct people) from PostHog."}

    # Fallback: weekly-active-users trend from our DB (active families only).
    conn = get_conn()
    try:
        active_athletes = f"SELECT id FROM athletes WHERE parent_id IN (SELECT id FROM parents WHERE {_active_where(conn)})"
        points = []
        for w in range(weeks - 1, -1, -1):
            start = _iso_days_ago((w + 1) * 7)
            end = _iso_days_ago(w * 7)
            wau = _scalar(conn, f"""
                SELECT COUNT(DISTINCT athlete_id) AS count FROM (
                    SELECT athlete_id FROM meal_logs   WHERE logged_at  >= %s AND logged_at  < %s
                    UNION SELECT athlete_id FROM window_logs WHERE created_at >= %s AND created_at < %s
                    UNION SELECT athlete_id FROM water_logs  WHERE updated_at >= %s AND updated_at < %s
                ) WHERE athlete_id IN ({active_athletes})""", (start, end, start, end, start, end))
            points.append({"week_start": start[:10], "active": wau})
        return {"source": "db_wau_fallback", "available": True,
                "reason": ph.get("reason"), "points": points,
                "note": "PostHog not connected — showing DB weekly-active-users trend instead."}
    finally:
        conn.close()


# ── Top events (PostHog) ─────────────────────────────────────────────────────
@router.get("/analytics/events")
def top_events(days: int = 30, force: bool = False, _: bool = Depends(require_admin)):
    return posthog_client.top_events(days, force=force)


# ── Live activity feed (PostHog events + batched DB name resolution) ──────────
def _as_int(v):
    """parent_id from PostHog properties can arrive as int, float, or str."""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


@router.get("/analytics/activity")
def activity(limit: int = 20, force: bool = False, _: bool = Depends(require_admin)):
    """Newest ~20 canonical actions, with parent_id resolved to a first name via a
    SINGLE batched DB query (no N+1). Unresolvable ids show 'Unknown'. Degrades to
    {available: false, reason} when PostHog is unreachable, like the other cards."""
    limit = max(1, min(50, limit))
    ph = posthog_client.recent_activity(limit, force=force)
    if not ph.get("available"):
        return ph
    rows = ph.get("data", {}).get("rows", [])

    ids = {pid for r in rows if (pid := _as_int(r.get("parent_id")))}
    names = {}
    if ids:
        conn = get_conn()
        try:
            placeholders = ",".join(["%s"] * len(ids))
            for r in conn.execute(
                    f"SELECT id, full_name FROM parents WHERE id IN ({placeholders})",
                    tuple(ids)).fetchall():
                parts = (r["full_name"] or "").strip().split()
                names[r["id"]] = parts[0] if parts else None
        finally:
            conn.close()

    out = [{"event": r["event"], "timestamp": r["timestamp"],
            "parent_first": names.get(_as_int(r.get("parent_id"))) or "Unknown"} for r in rows]
    return {"available": True, "as_of": ph.get("as_of"), "rows": out}


# ── Problem reports list (DB-derived — the actual reported text) ─────────────
@router.get("/analytics/problem-reports")
def problem_reports(days: int = 7, limit: int = 50, _: bool = Depends(require_admin)):
    """The individual problem reports behind the App-health count. Newest first.
    `days` defaults to 7 to match the "reported this week" figure; `days=0` returns
    all recent reports (up to `limit`). Empty list if the table doesn't exist yet."""
    limit = max(1, min(200, limit))
    conn = get_conn()
    try:
        if not _table_exists(conn, "problem_reports"):
            return {"reports": [], "count": 0, "days": days}
        where, params = "", []
        if days and days > 0:
            where = "WHERE created_at >= %s"
            params.append(_iso_days_ago(days))
        rows = conn.execute(
            f"SELECT id, description, app_version, platform, role_hint, created_at "
            f"FROM problem_reports {where} ORDER BY created_at DESC LIMIT %s",
            (*params, limit)).fetchall()
    finally:
        conn.close()
    reports = [{"id": r["id"], "description": r["description"], "app_version": r["app_version"],
                "platform": r["platform"], "role_hint": r["role_hint"], "created_at": r["created_at"]}
               for r in rows]
    return {"reports": reports, "count": len(reports), "days": days}


# ── Event-name discovery (verify mobile events are landing in PostHog) ────────
@router.get("/analytics/discover")
def discover(force: bool = False, _: bool = Depends(require_admin)):
    return {
        "discovered": posthog_client.discover_event_names(force=force),
        "canonical_events": posthog_client.CANONICAL_EVENTS,
        "how_to_verify": "Each canonical event should appear here once the mobile "
                         "app has fired it. Missing events mean that mobile hook "
                         "isn't wired yet.",
    }


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (name,),
    ).fetchone() is not None
