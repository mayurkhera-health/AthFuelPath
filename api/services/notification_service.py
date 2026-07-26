"""
api/services/notification_service.py

15-minute push notification scheduler for athlete fuel windows.

Architecture:
  run_notification_tick() — called by APScheduler every 15 min
    → for each athlete with an Expo token
        → resolve their local timezone (from expo_push_tokens.timezone)
        → call generate_windows_v2() → get_event_window_times()
        → select top 2 windows by priority rank
        → for each window whose open_time is within ±8 min of local now:
            → skip if quiet hours (before 06:30 or at/after 22:00)
            → skip if already logged (window_logs OR confirmations)
            → INSERT-before-send to notification_log (dedup guard)
            → POST to Expo push API for athlete stream and parent stream

Pure functions (in_quiet_hours, rank_for_notification, etc.) are importable
for testing without any DB or network access.
"""

from __future__ import annotations

import logging
import os
import requests
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime

from api.database import get_conn

log = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
FALLBACK_TZ   = "America/Los_Angeles"
DAILY_CAP     = 2
WINDOW_SLOP_MINUTES = 8  # fire if open_time is within ±8 min of local now

# Set NOTIFICATION_DRY_RUN=true to log what would be sent without calling Expo.
# Use this for all testing until copy is approved and a real device is ready.
DRY_RUN = os.getenv("NOTIFICATION_DRY_RUN", "false").lower() == "true"


# ── Timezone ───────────────────────────────────────────────────────────────────

def resolve_timezone(tz_str: str | None) -> ZoneInfo:
    if not tz_str:
        log.warning(
            "expo_push_tokens.timezone is NULL — using Pacific fallback. "
            "Ensure mobile app re-registers token with timezone on next launch."
        )
        return ZoneInfo(FALLBACK_TZ)
    try:
        return ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        log.warning("Unknown timezone %r — falling back to %s", tz_str, FALLBACK_TZ)
        return ZoneInfo(FALLBACK_TZ)


# ── Guardrails ─────────────────────────────────────────────────────────────────

def in_quiet_hours(open_time: str) -> bool:
    """Return True if open_time (HH:MM) falls before 06:30 or at/after 22:00."""
    return open_time < "06:30" or open_time >= "22:00"


_DEFAULT_NOTIFICATION_PREFS = {
    "training_days": True, "game_days": True,
    "quiet_hours_enabled": True, "quiet_start": "22:00", "quiet_end": "07:00",
}


def get_notification_prefs(profile_type: str, profile_id: int, conn) -> dict:
    """A profile that's never opened Settings has no row — default to
    DEFAULT_NOTIF_PREFS on the mobile side (both day types on, quiet hours
    22:00-07:00), matching today's actual behavior for existing users."""
    row = conn.execute(
        "SELECT training_days, game_days, quiet_hours_enabled, quiet_start, quiet_end "
        "FROM notification_prefs WHERE profile_type = ? AND profile_id = ?",
        (profile_type, profile_id),
    ).fetchone()
    if not row:
        return dict(_DEFAULT_NOTIFICATION_PREFS)
    return {
        "training_days": bool(row["training_days"]),
        "game_days": bool(row["game_days"]),
        "quiet_hours_enabled": bool(row["quiet_hours_enabled"]),
        "quiet_start": row["quiet_start"],
        "quiet_end": row["quiet_end"],
    }


def in_quiet_window(local_time: str, start: str, end: str) -> bool:
    """HH:MM string comparison. Handles overnight wraparound (e.g. 22:00
    start, 07:00 end) — the common case, since quiet hours span midnight."""
    if start <= end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def should_notify_recipient(prefs: dict, is_game: bool, local_time: str) -> bool:
    """A single recipient's (athlete's or parent's) own Training/Game Day +
    Quiet Hours prefs gate their OWN stream independently — one person
    silencing their phone never affects the other's."""
    if prefs["quiet_hours_enabled"] and in_quiet_window(local_time, prefs["quiet_start"], prefs["quiet_end"]):
        return False
    if is_game and not prefs["game_days"]:
        return False
    if not is_game and not prefs["training_days"]:
        return False
    return True


def rank_for_notification(w: dict) -> int:
    """Lower rank = higher priority. Rank 99 = skip entirely."""
    if w["priority"]:
        return 0
    if w["category"] in ("fuel_before", "quick_snack") and "top_up_snack" not in w["window_key"]:
        return 1
    if w["category"] in ("refuel_ready", "between_games"):
        return 2
    if w["category"] == "fuel_after":
        return 3
    return 99  # everyday, top-up snacks, fuel_during nudges — skip


def select_notification_windows(windows: list[dict]) -> list[dict]:
    eligible = [
        w for w in windows
        if w["is_tappable"]
        and not in_quiet_hours(w["open_time"])
        and rank_for_notification(w) < 99
    ]
    return sorted(eligible, key=lambda w: (rank_for_notification(w), w["sort_time"]))[:DAILY_CAP]


# ── Suppress-if-logged ─────────────────────────────────────────────────────────

def already_logged(athlete_id: int, window_key: str, date_str: str, conn) -> bool:
    """Return True if this window was already captured or confirmed today."""
    captured = conn.execute(
        "SELECT 1 FROM window_logs "
        "WHERE athlete_id = ? AND window_id = ? AND log_date = ? LIMIT 1",
        (athlete_id, window_key, date_str),
    ).fetchone()
    confirmed = conn.execute(
        "SELECT 1 FROM confirmations "
        "WHERE athlete_id = ? AND window_key = ? AND log_date = ? LIMIT 1",
        (athlete_id, window_key, date_str),
    ).fetchone()
    return bool(captured or confirmed)


# ── Expo push ──────────────────────────────────────────────────────────────────

def send_expo_push(
    tokens: list[str], title: str, body: str, record: bool = True, data: dict | None = None
) -> bool:
    """Send one Expo push batch. Returns True on a successful POST. `record`
    (default True) logs the outcome for the System Health passive expo_push check;
    alert sends pass record=False so they don't pollute that signal. `data`
    (optional) is Expo's tap-payload — read by the mobile app's
    useNotificationHandler to route a tap to the right screen; omitted
    entirely (not sent as `data: null`) when not provided, so existing
    callers are unaffected. Never raises."""
    if DRY_RUN:
        log.info("[DRY RUN] push → %s | %r | %r | data=%r", tokens, title, body, data)
        return True
    messages = [
        {"to": t, "title": title, "body": body, "sound": "default", **({"data": data} if data else {})}
        for t in tokens
    ]
    ok = False
    detail = ""
    try:
        resp = requests.post(EXPO_PUSH_URL, json=messages, timeout=10)
        ok = resp.status_code == 200
        if not ok:
            detail = f"HTTP {resp.status_code}"
    except Exception as exc:
        log.warning("Expo push failed: %s", exc)
        detail = str(exc)[:120]
    if record:
        try:  # lazy import avoids a load-time cycle
            from api.services.health_service import record_expo_send
            record_expo_send(ok, detail)
        except Exception:
            pass
    return ok


# ── INSERT-before-send dedup ───────────────────────────────────────────────────

def send_notification_guarded(
    athlete_id: int,
    window_key: str,
    date_str: str,
    recipient: str,
    tokens: list[str],
    title: str,
    body: str,
    conn,
) -> bool:
    """
    INSERT-before-send: prevents double-fire on retry; a crash between INSERT
    and send causes a silent miss on re-run (acceptable for best-effort reminders).
    Returns True if the notification was sent.

    In DRY_RUN mode: logs the payload and returns True without touching
    notification_log, so dry-run runs cannot poison the dedup table for
    later real sends.
    """
    if not tokens:
        return False
    if DRY_RUN:
        log.info(
            "[DRY RUN] athlete=%s window=%s recipient=%s | %r | %r",
            athlete_id, window_key, recipient, title, body,
        )
        return True
    try:
        conn.execute(
            "INSERT OR IGNORE INTO notification_log "
            "(athlete_id, window_key, send_date, recipient, token) VALUES (?, ?, ?, ?, ?)",
            (athlete_id, window_key, date_str, recipient, tokens[0]),
        )
        conn.commit()
    except Exception:
        return False

    if conn.execute("SELECT changes()").fetchone()[0] == 0:
        return False  # UNIQUE fired — already sent

    send_expo_push(tokens, title, body)
    return True


# ── Copy strings ───────────────────────────────────────────────────────────────

def _athlete_copy(
    window_key: str,
    is_game: bool,
    event_name: str | None,
    start_time_display: str | None,
) -> tuple[str, str]:
    st = start_time_display

    if window_key.startswith("pre_event_meal"):
        if is_game:
            body = (
                f"Time to eat! Your game starts at {st}. Fuel up now so you're ready to play your best."
                if st
                else "Time to eat! Fuel up now so you're ready to play your best."
            )
            return "⚡ Game Day Fuel", body
        body = (
            f"Practice starts at {st}. Eat now — your body needs fuel before you train."
            if st
            else "Eat now — your body needs fuel before you train."
        )
        return "⚡ Fuel Up", body

    if window_key.startswith("quick_morning_snack"):
        return "🌅 Early Game Today", "Early morning game — eat something light right now before you head out."

    if window_key.startswith("fuel_after_primary"):
        return "💪 Recovery Time", "Great work! Eat something in the next 30 min — your body is ready to recover."

    if window_key.startswith("refuel_ready"):
        return "🔄 Refuel Now", "Time to eat between sessions. Fuel up now so you're strong for what's next."

    if window_key.startswith("between_games"):
        return "⚡ Quick Break", "Short break before your next game — eat something quick and drink fluids now."

    return "⏰ Time to Eat", "Your fuel window is open — eat something now to keep your energy up."


def _parent_copy(
    window_key: str,
    is_game: bool,
    event_name: str | None,
    first_name: str,
) -> tuple[str, str] | None:
    en = event_name or "the event"

    if window_key.startswith("pre_event_meal"):
        if is_game:
            return (
                f"{first_name}'s Fuel Before",
                f"This is the fuel window before {en}. A meal now sets them up for the game.",
            )
        return (
            f"{first_name}'s Fuel Before",
            f"Fuel window is open before {first_name}'s session.",
        )

    if window_key.startswith("quick_morning_snack"):
        return (
            f"Early Game for {first_name}",
            "Early start today — a light snack before the game, then a proper meal after.",
        )

    if window_key.startswith("fuel_after_primary"):
        return (
            f"{first_name}'s Recharge Snack",
            "First 30 min after activity is the key recovery window — protein + carbs when ready.",
        )

    if window_key.startswith("refuel_ready"):
        return (
            f"Refuel for {first_name}",
            "Between sessions — this is the window to recover and fuel up for what's next.",
        )

    if window_key.startswith("between_games"):
        return (
            "Between Games",
            f"Short break between {first_name}'s games — quick carbs and fluid.",
        )

    return None


# ── Timing helper ──────────────────────────────────────────────────────────────

def _within_window(open_time: str, now_time: str, minutes: int = WINDOW_SLOP_MINUTES) -> bool:
    oh, om = map(int, open_time.split(":"))
    nh, nm = map(int, now_time.split(":"))
    return abs((oh * 60 + om) - (nh * 60 + nm)) <= minutes


def _format_start_time(start_time: str | None) -> str | None:
    if not start_time:
        return None
    try:
        h, m = map(int, start_time.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}"
    except (ValueError, AttributeError):
        return start_time


# ── Per-athlete notification logic ─────────────────────────────────────────────

def _notify_athlete(athlete_id: int, conn) -> None:
    from api.services.window_engine_v2 import Event, generate_windows_v2, get_event_window_times

    # Tokens + timezone for this athlete
    token_rows = conn.execute(
        "SELECT token, timezone FROM expo_push_tokens WHERE athlete_id = ?",
        (athlete_id,),
    ).fetchall()
    if not token_rows:
        return

    tz_str = next((r["timezone"] for r in token_rows if r["timezone"]), None)
    tz = resolve_timezone(tz_str)

    local_now  = datetime.now(tz=tz)
    local_date = local_now.strftime("%Y-%m-%d")
    local_time = local_now.strftime("%H:%M")

    # Today's events
    event_rows = conn.execute(
        "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time",
        (athlete_id, local_date),
    ).fetchall()
    events = [
        Event(
            id=r["id"],
            athlete_id=r["athlete_id"],
            event_type=r["event_type"],
            event_date=r["event_date"],
            start_time=r["start_time"],
            duration_hours=r["duration_hours"],
        )
        for r in event_rows
    ]

    result   = generate_windows_v2(events, local_date)
    windows  = get_event_window_times(result)
    selected = select_notification_windows(windows)
    if not selected:
        return

    # Athlete context for copy
    athlete_row = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
    if not athlete_row:
        return
    athlete    = dict(athlete_row)
    first_name = athlete["first_name"]
    parent_id  = athlete.get("parent_id")

    is_game = False
    event_name = None
    start_time_display = None
    if event_rows:
        first_ev   = dict(event_rows[0])
        is_game    = first_ev.get("event_type", "") in ("game", "tournament")
        event_name = first_ev.get("event_name")
        start_time_display = _format_start_time(first_ev.get("start_time"))

    athlete_tokens = [r["token"] for r in token_rows]
    parent_tokens: list[str] = []
    if parent_id:
        parent_tokens = [
            r["token"]
            for r in conn.execute(
                "SELECT token FROM expo_push_tokens WHERE parent_id = ?", (parent_id,)
            ).fetchall()
        ]

    # Each recipient's own Training/Game Day + Quiet Hours prefs gate their
    # own stream — computed once per tick, not per-window (day-type and the
    # current clock time don't change window-to-window within one tick).
    athlete_ok = should_notify_recipient(
        get_notification_prefs("athlete", athlete_id, conn), is_game, local_time
    )
    parent_ok = bool(parent_id) and should_notify_recipient(
        get_notification_prefs("parent", parent_id, conn), is_game, local_time
    )

    for w in selected:
        window_key = w["window_key"]

        if not _within_window(w["open_time"], local_time):
            continue
        if already_logged(athlete_id, window_key, local_date, conn):
            continue

        # Athlete stream
        if athlete_ok:
            a_title, a_body = _athlete_copy(window_key, is_game, event_name, start_time_display)
            send_notification_guarded(
                athlete_id, window_key, local_date, "athlete",
                athlete_tokens, a_title, a_body, conn,
            )

        # Parent stream
        p_copy = _parent_copy(window_key, is_game, event_name, first_name)
        if parent_ok and p_copy and parent_tokens:
            p_title, p_body = p_copy
            send_notification_guarded(
                athlete_id, window_key, local_date, "parent",
                parent_tokens, p_title, p_body, conn,
            )


# ── Scheduler entry point ──────────────────────────────────────────────────────

def run_notification_tick() -> None:
    """Called every 15 minutes by APScheduler. One DB connection for the whole tick."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT athlete_id FROM expo_push_tokens WHERE athlete_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                _notify_athlete(row["athlete_id"], conn)
            except Exception as exc:
                log.error("Notification tick failed for athlete %s: %s", row["athlete_id"], exc)
    finally:
        conn.close()
