"""
Founder alerting channel — shared push-first / email-fallback delivery to the
founder's phone. Extracted from health_alerts.py so both the System Health
alerts and the beta login alerts send through ONE mechanism (no duplicated Expo
integration).

Channel: Expo push to ADMIN_ALERT_PARENT_ID's registered device(s); if the push
send fails/raises or there are no tokens, fall back to email (ADMIN_ALERT_EMAIL).
Email fires ONLY as fallback, never duplicated. Everything here is best-effort
and must never raise into a caller (a broken alert can't break a real request).
"""

import logging
import os

from api.database import get_conn
from api.services.email_service import send_email

log = logging.getLogger(__name__)


def _push(conn, title, body) -> bool:
    pid = os.getenv("ADMIN_ALERT_PARENT_ID")
    if not pid:
        return False
    try:
        tokens = [r["token"] for r in conn.execute(
            "SELECT token FROM expo_push_tokens WHERE parent_id = %s", (int(pid),)).fetchall()]
    except Exception:
        conn.rollback()
        tokens = []
    if not tokens:
        return False
    # Lazy import avoids a load-time cycle (notification_service -> health_service).
    from api.services.notification_service import send_expo_push
    # record=False so alert sends don't pollute the passive expo_push health log.
    return bool(send_expo_push(tokens, title, body, record=False))


def _email(title, body) -> bool:
    to = os.getenv("ADMIN_ALERT_EMAIL")
    if not to:
        return False
    try:
        return bool(send_email(title, body, to=[to]))
    except Exception:
        log.warning("founder alert email failed", exc_info=True)
        return False


def notify_founder(title, body, conn=None, *, force_email=False) -> str:
    """Deliver one alert to the founder. Push-first, email fallback.

    Pass an open `conn` to reuse it (health checks run inside the tick's
    connection); omit it and a short-lived connection is opened for the token
    lookup (safe to call from a FastAPI BackgroundTask). `force_email=True` skips
    push entirely (used when the failing thing IS the push channel). Returns a
    short note describing the channel + outcome, e.g. "push ✓". Never raises."""
    if force_email:
        ok = _email(title, body)
        return f"email {'✓' if ok else '✗'}"

    own = conn is None
    c = conn or get_conn()
    try:
        if _push(c, title, body):
            return "push ✓"
    except Exception as e:
        log.warning("founder alert push error: %s", e)
    finally:
        if own:
            c.close()

    ok = _email(title, body)
    return f"email {'✓' if ok else '✗'} (push failed)"
