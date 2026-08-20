"""
Health alerting — fires only on meaningful transitions, push-first to the
founder's device with email strictly as fallback.

Rules:
  down     = green|unknown -> red   → "🔴 [AthFuelPath] <check> failed: <detail>"
  recovery = red -> green           → "✅ [AthFuelPath] <check> recovered"
  (unknown -> green never alerts.)

Cooldown: repeated DOWN alerts for the same check are suppressed for 3h (flap
control, survives restart via health_checks.last_alerted_at). Recovery always
notifies. Delivery goes through the shared founder_alerts channel (push-first to
ADMIN_ALERT_PARENT_ID's device(s), email fallback to ADMIN_ALERT_EMAIL). If the
failing check IS expo_push, force email directly (force_email=True). All sends
are best-effort and never raise into the runner.
"""

import logging
from datetime import datetime, timedelta

from api.services import founder_alerts

log = logging.getLogger(__name__)

COOLDOWN_HOURS = 3


def _direction(from_status, to_status):
    if to_status == "red" and from_status in ("green", "unknown"):
        return "down"
    if to_status == "green" and from_status == "red":
        return "recovery"
    return None


def _in_cooldown(conn, check_name) -> bool:
    row = conn.execute(
        "SELECT last_alerted_at FROM health_checks WHERE check_name = %s", (check_name,)).fetchone()
    if not row or not row["last_alerted_at"]:
        return False
    try:
        return (datetime.utcnow() - datetime.fromisoformat(row["last_alerted_at"])) < timedelta(hours=COOLDOWN_HOURS)
    except Exception:
        return False


def _mark_alerted(conn, check_name):
    try:
        conn.execute("UPDATE health_checks SET last_alerted_at=%s WHERE check_name=%s",
                     (datetime.utcnow().isoformat(), check_name))
    except Exception:
        conn.rollback()
        log.debug("mark_alerted failed for %s", check_name, exc_info=True)


def _message(check_name, direction, detail):
    if direction == "down":
        return f"🔴 [AthFuelPath] {check_name} failed", f"{check_name} failed: {detail}"
    return f"✅ [AthFuelPath] {check_name} recovered", f"{check_name} recovered."


def dispatch(conn, check_name, from_status, to_status, detail):
    """Send an alert if this transition warrants one. Returns a short note
    (channel + outcome) to append to the incident, or None if no alert fired."""
    direction = _direction(from_status, to_status)
    if not direction:
        return None
    if direction == "down" and _in_cooldown(conn, check_name):
        return "suppressed (cooldown)"

    title, body = _message(check_name, direction, detail)

    # If the push channel itself is the failing check, go straight to email.
    if check_name == "expo_push":
        note = founder_alerts.notify_founder(title, body, conn, force_email=True)
        _mark_alerted(conn, check_name)
        return f"{note} (push unavailable)"

    note = founder_alerts.notify_founder(title, body, conn)
    _mark_alerted(conn, check_name)
    return note
