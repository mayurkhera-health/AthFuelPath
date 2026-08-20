"""
Fuel IQ §2.1 schedule-anchored notification triggers.

Trigger 1 (fueliq_morning) — fires ≈07:30 local when the athlete has a
  practice/training/strength event today and NO game/tournament.
  Copy: "Light day today. Quick — what's on your plate?"

Trigger 2 (fueliq_pregame) — fires ≈2 hours before the first logged
  game/tournament with a start_time. Skips silently and logs a
  fueliq_push_events row with outcome='skipped_no_start_time' when
  start_time is NULL — queryable via:
    SELECT * FROM fueliq_push_events WHERE outcome='skipped_no_start_time';

Quiet hours (§2.1): before 06:30 OR school hours 09:00–15:00 OR after 21:00.
Daily cap: FUELIQ_DAILY_CAP = 2 Fuel IQ pushes per athlete per day.
Dedup: notification_log (athlete_id, window_key='fueliq_*', send_date, recipient).
Feature gate: FUELIQ_ENABLED env var must be 'true'.
Per-athlete toggles: fueliq_notification_prefs table (morning_enabled, pregame_enabled).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from api.database import get_conn

log = logging.getLogger(__name__)

FUELIQ_MORNING_TARGET = "07:30"  # fire at ~7:30 am local (pre-school window)
FUELIQ_PREGAME_OFFSET = 120      # minutes before game_start_time for Trigger 2
FUELIQ_SLOP_MINUTES   = 8        # ±8 min around target (same as fuel-window scheduler)
FUELIQ_DAILY_CAP      = 2        # max Fuel IQ pushes per athlete per day


def _fueliq_enabled() -> bool:
    return os.getenv("FUELIQ_ENABLED", "false").lower() == "true"


# ── Quiet hours (§2.1) ─────────────────────────────────────────────────────────

def fueliq_in_quiet_hours(t: str) -> bool:
    """True if local time (HH:MM) is in a blackout window.
    Allowed: 06:30–09:00 (pre-school) and 15:00–21:00 (post-school)."""
    return t < "06:30" or ("09:00" <= t < "15:00") or t >= "21:00"


def _within_window(target: str, now: str, slop: int = FUELIQ_SLOP_MINUTES) -> bool:
    th, tm = map(int, target.split(":"))
    nh, nm = map(int, now.split(":"))
    return abs((th * 60 + tm) - (nh * 60 + nm)) <= slop


# ── Daily cap ──────────────────────────────────────────────────────────────────

def _today_fueliq_sent(athlete_id: int, date_str: str, conn) -> int:
    """Count Fuel IQ pushes already sent to the athlete stream today."""
    return conn.execute(
        "SELECT COUNT(*) AS count FROM notification_log "
        "WHERE athlete_id = %s AND send_date = %s AND window_key LIKE %s AND recipient = 'athlete'",
        (athlete_id, date_str, "fueliq_%"),
    ).fetchone()["count"]


# ── Audit log ──────────────────────────────────────────────────────────────────

def _log_push_event(athlete_id: int, trigger: str, outcome: str, date_str: str, conn) -> None:
    """INSERT OR IGNORE into fueliq_push_events — one row per
    (athlete, trigger, outcome, date) so we can query skip rates:
      SELECT outcome, COUNT(*) FROM fueliq_push_events
      WHERE trigger='pregame' GROUP BY outcome;
    """
    try:
        conn.execute(
            "INSERT INTO fueliq_push_events (athlete_id, trigger, outcome, event_date) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (athlete_id, trigger, outcome, date_str),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.warning("[FUELIQ] push event log failed for athlete %s: %s", athlete_id, exc)


# ── Per-athlete notification tick ──────────────────────────────────────────────

def _notify_athlete_fueliq(athlete_id: int, conn, now: datetime | None = None) -> None:
    from api.services.notification_service import (
        resolve_timezone, send_notification_guarded, get_notification_prefs, in_quiet_window,
    )

    token_rows = conn.execute(
        "SELECT token, timezone FROM expo_push_tokens WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchall()
    if not token_rows:
        return

    tz_str    = next((r["timezone"] for r in token_rows if r["timezone"]), None)
    tz        = resolve_timezone(tz_str)
    local_now = now.astimezone(tz) if now else datetime.now(tz=tz)
    local_date = local_now.strftime("%Y-%m-%d")
    local_time = local_now.strftime("%H:%M")

    # Read per-athlete prefs; default row is created on first access.
    conn.execute(
        "INSERT INTO fueliq_notification_prefs (athlete_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (athlete_id,),
    )
    conn.commit()
    prefs_row   = conn.execute(
        "SELECT morning_enabled, pregame_enabled FROM fueliq_notification_prefs WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    morning_on  = bool(prefs_row["morning_enabled"])
    pregame_on  = bool(prefs_row["pregame_enabled"])

    if not morning_on and not pregame_on:
        return

    # The athlete's own configured Quiet Hours (Settings > Notifications) must
    # be respected here too, on top of the fixed §2.1 school-hours blackout
    # below — the two are independent checks, not a replacement for each
    # other. A user who sets a stricter or looser custom window than the
    # spec default must actually see that reflected in Fuel IQ pushes, not
    # just the fuel-window pushes this same prefs row already gates.
    user_prefs = get_notification_prefs("athlete", athlete_id, conn)
    if user_prefs["quiet_hours_enabled"] and in_quiet_window(
        local_time, user_prefs["quiet_start"], user_prefs["quiet_end"]
    ):
        return

    tokens = [r["token"] for r in token_rows]

    event_rows = conn.execute(
        "SELECT event_type, start_time FROM events WHERE athlete_id = %s AND event_date = %s",
        (athlete_id, local_date),
    ).fetchall()

    # ── Trigger 1: morning light/moderate training day ─────────────────────────
    if morning_on and _within_window(FUELIQ_MORNING_TARGET, local_time):
        if not fueliq_in_quiet_hours(local_time):
            has_training = any(
                r["event_type"] in ("practice", "training", "strength") for r in event_rows
            )
            has_game = any(
                r["event_type"] in ("game", "tournament") for r in event_rows
            )
            if has_training and not has_game:
                if _today_fueliq_sent(athlete_id, local_date, conn) < FUELIQ_DAILY_CAP:
                    sent = send_notification_guarded(
                        athlete_id, "fueliq_morning", local_date, "athlete",
                        tokens, "⚡ Fuel IQ",
                        "Light day today. Quick — what's on your plate?",
                        conn,
                    )
                    _log_push_event(
                        athlete_id, "morning",
                        "sent" if sent else "dedup",
                        local_date, conn,
                    )

    # ── Trigger 2: ~2 hours before logged game ─────────────────────────────────
    if pregame_on:
        game_rows = [r for r in event_rows if r["event_type"] in ("game", "tournament")]
        for game in game_rows:
            start_time = game["start_time"]
            if not start_time:
                log.info(
                    "[FUELIQ] Pre-game push skipped (no start_time) athlete=%s date=%s",
                    athlete_id, local_date,
                )
                _log_push_event(athlete_id, "pregame", "skipped_no_start_time", local_date, conn)
                continue  # check next game in case a later one has start_time

            h, m       = map(int, start_time.split(":"))
            target_min = h * 60 + m - FUELIQ_PREGAME_OFFSET
            if target_min < 0:
                continue  # game before 2am, target would underflow, skip
            target_time = f"{target_min // 60:02d}:{target_min % 60:02d}"

            if _within_window(target_time, local_time) and not fueliq_in_quiet_hours(local_time):
                if _today_fueliq_sent(athlete_id, local_date, conn) < FUELIQ_DAILY_CAP:
                    sent = send_notification_guarded(
                        athlete_id, "fueliq_pregame", local_date, "athlete",
                        tokens, "⚡ Fuel IQ",
                        "Kickoff's close. You know this one.",
                        conn,
                    )
                    _log_push_event(
                        athlete_id, "pregame",
                        "sent" if sent else "dedup",
                        local_date, conn,
                    )
                break  # one pre-game push per day regardless of game count


# ── Scheduler entry point ──────────────────────────────────────────────────────

def run_fueliq_notification_tick(now: datetime | None = None) -> None:
    """Called every 15 minutes by APScheduler. Evaluates §2.1 triggers for
    every athlete with a registered push token. No-op when FUELIQ_ENABLED is
    not 'true'. `now` is test-only injection (UTC-aware datetime) — production
    calls always resolve real wall-clock time per athlete's own timezone."""
    if not _fueliq_enabled():
        return
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT athlete_id FROM expo_push_tokens WHERE athlete_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                _notify_athlete_fueliq(row["athlete_id"], conn, now=now)
            except Exception as exc:
                log.error("[FUELIQ] Tick failed for athlete %s: %s", row["athlete_id"], exc)
    finally:
        conn.close()
