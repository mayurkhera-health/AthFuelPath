"""
Beta login alerts — ping the founder's phone on every parent login/signup so she
can see who's actively using the app during beta.

Routed through founder_alerts (shared push-first / email-fallback channel), so
there's ONE alert mechanism, not a second Expo integration. Context-aware:
first-ever login reads as a new signup, later logins as returning.

No throttle / cooldown / dedup by design — a deliberate beta stance. Turn it
down after beta with the LOGIN_ALERTS_MODE env var (no code change):
    all               — alert on every login + new signup (default, beta)
    new_signups_only  — only first-ever logins (new signups)
    off               — no login alerts at all

Best-effort and non-blocking: a failed alert must never break or slow a real
login. Callers fire this from a BackgroundTask (runs after the response), and
everything here is additionally wrapped so it can never raise.
"""

import logging
import os

from api.services import founder_alerts

log = logging.getLogger(__name__)


def _mode() -> str:
    return (os.getenv("LOGIN_ALERTS_MODE", "all") or "all").strip().lower()


def _first_name(parent: dict) -> str:
    parts = (parent.get("full_name") or "").split()
    return parts[0] if parts else "Someone"


def notify_login(parent: dict, *, is_new: bool, athlete_hint: str = "") -> None:
    """Alert the founder about a parent login. Opens its own DB connection (safe
    to run as a FastAPI BackgroundTask). Honors LOGIN_ALERTS_MODE. Never raises."""
    try:
        mode = _mode()
        if mode == "off":
            return
        if mode == "new_signups_only" and not is_new:
            return

        first = _first_name(parent)
        if is_new:
            title = "🎉 New AthFuelPath signup"
            body = f"{first} just signed up"
            if athlete_hint:
                body += f" · {athlete_hint}"
        else:
            title = "👋 AthFuelPath login"
            body = f"{first} logged in"

        founder_alerts.notify_founder(title, body)  # own short-lived connection
    except Exception:
        log.warning("login alert failed (non-blocking)", exc_info=True)


def athlete_hint(athletes: list) -> str:
    """A tiny 'Emma, Forward'-style tag from the first athlete, if any."""
    if not athletes:
        return ""
    a = athletes[0]
    name = (a.get("first_name") or "").strip()
    pos = (a.get("position") or "").strip()
    if name and pos:
        return f"{name}, {pos}"
    return name or pos or ""
