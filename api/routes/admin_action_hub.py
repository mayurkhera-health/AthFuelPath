"""
Action Hub — an operations-oriented dashboard: a live "needs attention" feed
built from REAL signals (red System Health checks, at-risk families, this-week
problem reports), plus real metric cards, a weekly-activity heatmap, and the
health summary.

Grounded adaptation of the "Mission Control" spec: no world map (we store no
locations), no retry/notify remediation (no such endpoints) — attention items
carry a "View" action that navigates to the relevant screen. Reuses existing
data functions (db_metrics, funnel_steps, get_health_snapshot) — no new source
of truth.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from api.database import get_conn
from api.routes.admin_analytics import db_metrics, funnel_steps, _active_where
from api.routes.admin_overview import HEALTH_PLAIN, _health_line
from api.services import health_service
from api.services.admin_auth import require_admin

router = APIRouter()


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (name,),
    ).fetchone() is not None


def _attention(conn):
    """Real, actionable signals ordered errors-first. Each item: severity,
    category, title, detail, and a navigate action (or None)."""
    aw = _active_where(conn)
    active_ids = f"SELECT id FROM parents WHERE {aw}"
    now = datetime.utcnow()
    items = []

    # 1. Red System Health checks → error.
    for r in conn.execute("SELECT check_name, detail FROM health_checks WHERE status = 'red'").fetchall():
        name = HEALTH_PLAIN.get(r["check_name"], r["check_name"])
        items.append({
            "severity": "error", "category": "System health", "icon": "🔴",
            "title": name[0].upper() + name[1:],
            "detail": r["detail"] or "Not working right now.",
            "action": {"label": "View health", "section": "health"},
        })

    # 2. Sync-stale families: calendar connected but not synced in 48h → error.
    cutoff_48h = (now - timedelta(hours=48)).isoformat()
    for r in conn.execute(f"""
        SELECT DISTINCT p.id, p.full_name FROM parents p JOIN athletes a ON a.parent_id = p.id
        WHERE p.id IN ({active_ids}) AND (a.byga_ics_url IS NOT NULL OR a.playmetrics_ics_url IS NOT NULL)
          AND NOT EXISTS(SELECT 1 FROM events e WHERE e.athlete_id = a.id
                         AND e.synced_at IS NOT NULL AND e.synced_at > %s)
        LIMIT 10""", (cutoff_48h,)).fetchall():
        items.append({
            "severity": "error", "category": "Calendar sync", "icon": "🔁",
            "title": r["full_name"], "detail": "Calendar connected but hasn't synced in over 48 hours.",
            "action": {"label": "View family", "section": "users", "id": r["id"]},
        })

    # 3. Never-connected families: signed up >3d ago, has athletes, no calendar
    #    of any kind (auto-sync or uploaded .ics) → warning.
    cutoff_3d = (now - timedelta(days=3)).isoformat()
    for r in conn.execute(f"""
        SELECT p.id, p.full_name FROM parents p
        WHERE p.id IN ({active_ids}) AND p.created_at < %s
          AND EXISTS(SELECT 1 FROM athletes a WHERE a.parent_id = p.id)
          AND NOT EXISTS(SELECT 1 FROM athletes a WHERE a.parent_id = p.id
             AND (a.byga_ics_url IS NOT NULL OR a.playmetrics_ics_url IS NOT NULL
                  OR EXISTS(SELECT 1 FROM events e WHERE e.athlete_id = a.id AND e.uid IS NOT NULL AND e.uid != '')))
        ORDER BY p.created_at LIMIT 10""", (cutoff_3d,)).fetchall():
        items.append({
            "severity": "warning", "category": "Onboarding", "icon": "📅",
            "title": r["full_name"], "detail": "Signed up but hasn't connected a calendar yet.",
            "action": {"label": "View family", "section": "users", "id": r["id"]},
        })

    # 4. Problem reports this week → warning (one summary item).
    since_7 = (now - timedelta(days=7)).isoformat()
    if _table_exists(conn, "problem_reports"):
        n = conn.execute("SELECT COUNT(*) AS count FROM problem_reports WHERE created_at >= %s", (since_7,)).fetchone()["count"]
        if n:
            items.append({
                "severity": "warning", "category": "Problem reports", "icon": "🐛",
                "title": f"{n} new problem {'report' if n == 1 else 'reports'} this week",
                "detail": "Users reported issues in the app this week.",
                "action": {"label": "View analytics", "section": "analytics"},
            })

    items.sort(key=lambda i: 0 if i["severity"] == "error" else 1)
    return items


def _heatmap(conn, weeks=8):
    """Weekly activity heatmap data: active-athlete count per day over the last
    `weeks` weeks. Frontend arranges the points into a weekday × week grid."""
    aw = _active_where(conn)
    active_athletes = f"SELECT id FROM athletes WHERE parent_id IN (SELECT id FROM parents WHERE {aw})"
    since = (datetime.utcnow() - timedelta(days=weeks * 7)).isoformat()
    rows = conn.execute(f"""
        SELECT day, COUNT(DISTINCT athlete_id) AS c FROM (
            SELECT substr(logged_at,1,10) AS day, athlete_id FROM meal_logs   WHERE logged_at  >= %s
            UNION SELECT substr(created_at,1,10), athlete_id FROM window_logs WHERE created_at >= %s
            UNION SELECT substr(updated_at,1,10), athlete_id FROM water_logs  WHERE updated_at >= %s
        ) WHERE athlete_id IN ({active_athletes})
        GROUP BY day""", (since, since, since)).fetchall()
    points = [{"date": r["day"], "count": r["c"]} for r in rows]
    return {"weeks": weeks, "points": points, "max": max([p["count"] for p in points], default=0)}


@router.get("/action-hub")
def action_hub(_: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        attention = _attention(conn)
        m = db_metrics(conn, days=30)
        steps = {s["label"]: s["value"] for s in funnel_steps(conn)}
        connected = steps.get("Connected calendar", 0)
        fam = m["families_total"]
        metrics = [
            {"label": "Families", "value": fam, "sub": "total"},
            {"label": "New this month", "value": m["signups_window"], "sub": "last 30 days"},
            {"label": "Active this week", "value": m["active_7d"], "sub": "athletes"},
            {"label": "Calendar adoption", "value": f"{round(100 * connected / fam) if fam else 0}%",
             "sub": f"{connected} of {fam} families"},
        ]
        health = _health_line(health_service.get_health_snapshot(conn))
        heatmap = _heatmap(conn)
    finally:
        conn.close()

    return {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "health": health,
        "urgent_count": sum(1 for a in attention if a["severity"] == "error"),
        "attention": attention,
        "metrics": metrics,
        "heatmap": heatmap,
    }
