"""
Grocery list weekly reset.

Runs inside the 15-minute APScheduler tick. On Sunday 00:00–00:14 in each
athlete's local timezone, deletes shopping_list_items and recipe_list_items
for the PREVIOUS week's lists. DELETE is idempotent — running twice on the
same week_start is a no-op.
"""
import logging
from datetime import datetime, timedelta

from api.database import get_conn
from api.utils.week import get_week_start
from api.services.notification_service import resolve_timezone

log = logging.getLogger(__name__)


def run_grocery_reset_tick() -> None:
    """Called every 15 minutes by APScheduler."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT athlete_id, MAX(timezone) AS timezone "
            "FROM expo_push_tokens WHERE athlete_id IS NOT NULL GROUP BY athlete_id"
        ).fetchall()
        for row in rows:
            try:
                _reset_if_due(row["athlete_id"], row["timezone"], conn)
            except Exception as exc:
                conn.rollback()
                log.error("Grocery reset tick failed for athlete %s: %s", row["athlete_id"], exc)
    finally:
        conn.close()


def _reset_if_due(athlete_id: int, tz_str: str | None, conn) -> None:
    tz = resolve_timezone(tz_str)
    local_now = datetime.now(tz=tz)

    # Only fire on Sunday (Python weekday 6) in the first 15 minutes after midnight.
    if local_now.weekday() != 6 or local_now.hour != 0 or local_now.minute >= 15:
        return

    prev_week_start = (get_week_start(local_now.date()) - timedelta(days=7)).isoformat()

    conn.execute(
        "DELETE FROM shopping_list_items WHERE list_id IN "
        "(SELECT id FROM shopping_lists WHERE athlete_id = %s AND week_start = %s)",
        (athlete_id, prev_week_start),
    )

    conn.execute(
        "DELETE FROM recipe_list_items WHERE list_id IN "
        "(SELECT id FROM recipe_lists WHERE athlete_id = %s AND week_start = %s)",
        (athlete_id, prev_week_start),
    )

    conn.commit()
    log.info("Grocery reset: athlete=%s cleared week_start=%s", athlete_id, prev_week_start)
