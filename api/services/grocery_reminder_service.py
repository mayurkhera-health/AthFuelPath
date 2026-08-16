"""
Saturday grocery list reset warning.

Runs inside the 15-minute APScheduler tick. On Saturday near 10:00 AM in
each parent's local timezone (±8 min, matching the existing window slop),
sends a push notification reminding them the grocery list resets tonight.

Skips if the family has no items on the current week's grocery list.
Deduplicates via notification_log (athlete_id=parent_id, window_key,
send_date, recipient) — one send per parent per Saturday.
"""
import logging
from datetime import datetime, date as _date, timedelta

from api.database import get_conn
from api.utils.week import get_week_start
from api.services.notification_service import resolve_timezone, send_notification_guarded
from api.services import email_templates
from api.services.email_service import send_email

log = logging.getLogger(__name__)

_WINDOW_KEY = "grocery_reset_warning"
_TARGET_HOUR = 10
_TARGET_MINUTE = 0
_SLOP_MINUTES = 8

_TITLE = "Your grocery list resets tomorrow"
_BODY = (
    "Take a screenshot of anything you want to keep — "
    "your list clears tonight at midnight to make room for next week."
)


def run_grocery_reminder_tick() -> None:
    """Called every 15 minutes by APScheduler."""
    conn = get_conn()
    try:
        parent_rows = conn.execute(
            "SELECT DISTINCT parent_id FROM expo_push_tokens WHERE parent_id IS NOT NULL"
        ).fetchall()
        for row in parent_rows:
            try:
                _remind_if_due(row["parent_id"], conn)
            except Exception as exc:
                log.error("Grocery reminder tick failed for parent %s: %s", row["parent_id"], exc)
    finally:
        conn.close()


def _remind_if_due(parent_id: int, conn) -> None:
    token_rows = conn.execute(
        "SELECT token, timezone FROM expo_push_tokens WHERE parent_id = ?",
        (parent_id,),
    ).fetchall()
    if not token_rows:
        return

    tz_str = next((r["timezone"] for r in token_rows if r["timezone"]), None)
    tz = resolve_timezone(tz_str)
    local_now = datetime.now(tz=tz)

    # Only fire on Saturday (Python weekday 5).
    if local_now.weekday() != 5:
        return

    # Within ±8 minutes of 10:00 AM.
    now_min = local_now.hour * 60 + local_now.minute
    target_min = _TARGET_HOUR * 60 + _TARGET_MINUTE
    if abs(now_min - target_min) > _SLOP_MINUTES:
        return

    local_date = local_now.strftime("%Y-%m-%d")
    local_week_start = get_week_start(local_now.date()).isoformat()

    # Check if any athlete in this family has grocery items this week.
    athlete_ids = [
        r["id"] for r in conn.execute(
            "SELECT id FROM athletes WHERE parent_id = ?", (parent_id,)
        ).fetchall()
    ]
    if not athlete_ids:
        return

    has_items = any(
        conn.execute(
            "SELECT 1 FROM shopping_list_items si "
            "JOIN shopping_lists sl ON sl.id = si.list_id "
            "WHERE sl.athlete_id = ? AND sl.week_start = ? LIMIT 1",
            (aid, local_week_start),
        ).fetchone()
        for aid in athlete_ids
    )
    if not has_items:
        return

    tokens = [r["token"] for r in token_rows]
    first_send = send_notification_guarded(
        parent_id,  # stored as athlete_id in notification_log for dedup
        _WINDOW_KEY,
        local_date,
        "parent",
        tokens,
        _TITLE,
        _BODY,
        conn,
    )
    if not first_send:
        return

    parent_row = conn.execute(
        "SELECT email, full_name FROM parents WHERE id = ?", (parent_id,)
    ).fetchone()
    if not parent_row:
        return
    parent_first = (parent_row["full_name"] or "").split()[0] or "there"
    athlete_items = _build_athlete_items(athlete_ids, local_week_start, conn)
    if not athlete_items:
        return
    text, html = email_templates.grocery_list_email(parent_first, local_week_start, athlete_items)
    week_end = (_date.fromisoformat(local_week_start) + timedelta(days=6)).strftime("%-d")
    week_start_label = _date.fromisoformat(local_week_start).strftime("%b %-d")
    subject = f"Your AthFuelPath grocery list — {week_start_label}–{week_end}"
    send_email(subject, text, [parent_row["email"]], html=html)


def _build_athlete_items(athlete_ids: list[int], week_start: str, conn) -> list[dict]:
    result = []
    for aid in athlete_ids:
        athlete_row = conn.execute(
            "SELECT first_name FROM athletes WHERE id = ?", (aid,)
        ).fetchone()
        athlete_name = athlete_row["first_name"] if athlete_row else f"Athlete {aid}"

        rows = conn.execute(
            "SELECT si.name, si.category, si.source "
            "FROM shopping_list_items si "
            "JOIN shopping_lists sl ON sl.id = si.list_id "
            "WHERE sl.athlete_id = ? AND sl.week_start = ? "
            "ORDER BY si.category, si.name",
            (aid, week_start),
        ).fetchall()

        by_category: dict[str, list[str]] = {}
        extras: list[str] = []
        for r in rows:
            if r["source"] == "custom":
                extras.append(r["name"])
            else:
                cat = r["category"] or "other"
                by_category.setdefault(cat, []).append(r["name"])

        if by_category or extras:
            result.append({
                "athlete_name": athlete_name,
                "by_category": by_category,
                "extras": extras,
            })
    return result
