"""Unit tests for the Fuel IQ §2.1 schedule-anchored notification triggers
(api/services/fueliq_notification_service.py) — morning training-day nudge
and pre-game reminder, layered on top of the shared notification_log dedup
table and per-athlete fueliq_notification_prefs toggles."""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.services.db_migrations import (
    _create_expo_push_tokens,
    _add_timezone_to_tokens,
    _create_notification_log,
    _create_notification_prefs,
    _create_fueliq_notification_prefs,
    _create_fueliq_push_events,
)
from api.services import fueliq_notification_service as fns

PST = ZoneInfo("America/Los_Angeles")


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fueliq_notif_db():
    conn = _mk_conn()
    conn.executescript("CREATE TABLE athletes (id INTEGER PRIMARY KEY);")
    conn.executescript("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER,
            event_name TEXT,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            start_time TEXT
        );
    """)
    _create_expo_push_tokens(conn)
    _add_timezone_to_tokens(conn)
    _create_notification_log(conn)
    _create_notification_prefs(conn)
    _create_fueliq_notification_prefs(conn)
    _create_fueliq_push_events(conn)
    conn.commit()
    return conn


def _add_athlete(conn, athlete_id):
    conn.execute("INSERT OR IGNORE INTO athletes (id) VALUES (?)", (athlete_id,))
    conn.commit()


def _add_token(conn, token, athlete_id, timezone="America/Los_Angeles"):
    _add_athlete(conn, athlete_id)
    conn.execute(
        "INSERT INTO expo_push_tokens (athlete_id, token, timezone) VALUES (?, ?, ?)",
        (athlete_id, token, timezone),
    )
    conn.commit()


def _add_event(conn, athlete_id, event_type, event_date, start_time=None):
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time) "
        "VALUES (?, 'E', ?, ?, ?)",
        (athlete_id, event_type, event_date, start_time),
    )
    conn.commit()


def _set_prefs(conn, athlete_id, morning_enabled=True, pregame_enabled=True):
    conn.execute(
        "INSERT INTO fueliq_notification_prefs (athlete_id, morning_enabled, pregame_enabled) "
        "VALUES (?, ?, ?) ON CONFLICT(athlete_id) DO UPDATE SET "
        "morning_enabled = excluded.morning_enabled, pregame_enabled = excluded.pregame_enabled",
        (athlete_id, int(morning_enabled), int(pregame_enabled)),
    )
    conn.commit()


def _patch_send(monkeypatch):
    """Force DRY_RUN off: notification_service.py's DRY_RUN is computed once at
    first import, and if api.main (imported by conftest's session-scoped
    scheduler-disable fixture) has already run load_dotenv() with a local
    NOTIFICATION_DRY_RUN=true, send_notification_guarded would short-circuit
    before ever calling send_expo_push — same override test_notification_service.py
    uses for its own dry-run tests."""
    import api.services.notification_service as ns
    monkeypatch.setattr(ns, "DRY_RUN", False)
    sent = []
    monkeypatch.setattr(
        ns, "send_expo_push",
        lambda tokens, title, body, data=None: sent.append((tokens, title, body)) or True,
    )
    return sent


# ─── fueliq_in_quiet_hours ──────────────────────────────────────────────────────

class TestFueliqInQuietHours:
    def test_before_0630_is_quiet(self):
        assert fns.fueliq_in_quiet_hours("05:00") is True

    def test_0629_is_quiet(self):
        assert fns.fueliq_in_quiet_hours("06:29") is True

    def test_0630_is_not_quiet(self):
        assert fns.fueliq_in_quiet_hours("06:30") is False

    def test_0859_is_not_quiet(self):
        assert fns.fueliq_in_quiet_hours("08:59") is False

    def test_0900_school_hours_is_quiet(self):
        assert fns.fueliq_in_quiet_hours("09:00") is True

    def test_1459_school_hours_is_quiet(self):
        assert fns.fueliq_in_quiet_hours("14:59") is True

    def test_1500_after_school_is_not_quiet(self):
        assert fns.fueliq_in_quiet_hours("15:00") is False

    def test_2059_is_not_quiet(self):
        assert fns.fueliq_in_quiet_hours("20:59") is False

    def test_2100_is_quiet(self):
        assert fns.fueliq_in_quiet_hours("21:00") is True

    def test_midnight_is_quiet(self):
        assert fns.fueliq_in_quiet_hours("00:00") is True


# ─── _today_fueliq_sent ─────────────────────────────────────────────────────────

class TestTodayFueliqSent:
    def test_zero_when_nothing_sent(self):
        conn = _fueliq_notif_db()
        assert fns._today_fueliq_sent(1, "2026-07-10", conn) == 0

    def test_counts_fueliq_window_keys_only(self):
        conn = _fueliq_notif_db()
        conn.execute(
            "INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token) "
            "VALUES (1, 'fueliq_morning', '2026-07-10', 'athlete', 'tok')"
        )
        conn.execute(
            "INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token) "
            "VALUES (1, 'pre_event_meal', '2026-07-10', 'athlete', 'tok')"
        )
        conn.commit()
        assert fns._today_fueliq_sent(1, "2026-07-10", conn) == 1

    def test_ignores_parent_recipient(self):
        conn = _fueliq_notif_db()
        conn.execute(
            "INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token) "
            "VALUES (1, 'fueliq_morning', '2026-07-10', 'parent', 'tok')"
        )
        conn.commit()
        assert fns._today_fueliq_sent(1, "2026-07-10", conn) == 0

    def test_scoped_to_athlete_and_date(self):
        conn = _fueliq_notif_db()
        conn.execute(
            "INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token) "
            "VALUES (2, 'fueliq_morning', '2026-07-10', 'athlete', 'tok')"
        )
        conn.execute(
            "INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token) "
            "VALUES (1, 'fueliq_morning', '2026-07-09', 'athlete', 'tok')"
        )
        conn.commit()
        assert fns._today_fueliq_sent(1, "2026-07-10", conn) == 0


# ─── _log_push_event ────────────────────────────────────────────────────────────

class TestLogPushEvent:
    def test_inserts_a_row(self):
        conn = _fueliq_notif_db()
        fns._log_push_event(1, "morning", "sent", "2026-07-10", conn)
        row = conn.execute("SELECT * FROM fueliq_push_events").fetchone()
        assert row["athlete_id"] == 1
        assert row["trigger"] == "morning"
        assert row["outcome"] == "sent"

    def test_is_idempotent_per_athlete_trigger_outcome_date(self):
        conn = _fueliq_notif_db()
        fns._log_push_event(1, "pregame", "skipped_no_start_time", "2026-07-10", conn)
        fns._log_push_event(1, "pregame", "skipped_no_start_time", "2026-07-10", conn)
        count = conn.execute("SELECT COUNT(*) FROM fueliq_push_events").fetchone()[0]
        assert count == 1


# ─── _notify_athlete_fueliq — Trigger 1 (morning) ──────────────────────────────

class TestMorningTrigger:
    def test_sends_on_training_day_with_no_game(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "practice", "2026-07-10")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert len(sent) == 1
        assert sent[0][0] == ["Tok1"]
        row = conn.execute(
            "SELECT outcome FROM fueliq_push_events WHERE athlete_id = 1 AND trigger = 'morning'"
        ).fetchone()
        assert row["outcome"] == "sent"

    def test_skips_when_game_also_scheduled(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "practice", "2026-07-10")
        _add_event(conn, 1, "game", "2026-07-10", start_time="18:00")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []

    def test_skips_when_no_training_event(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []

    def test_skips_outside_time_window(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "training", "2026-07-10")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 9, 0, tzinfo=PST)  # 90 min past 07:30 target
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []

    def test_respects_morning_disabled_pref(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "strength", "2026-07-10")
        _set_prefs(conn, 1, morning_enabled=False)
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []

    def test_default_prefs_are_auto_created_and_enabled(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "practice", "2026-07-10")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert len(sent) == 1
        row = conn.execute(
            "SELECT morning_enabled, pregame_enabled FROM fueliq_notification_prefs WHERE athlete_id = 1"
        ).fetchone()
        assert row["morning_enabled"] == 1
        assert row["pregame_enabled"] == 1

    def test_respects_athletes_own_configured_quiet_hours(self, monkeypatch):
        """Regression: Fuel IQ pushes used to only check the fixed §2.1
        blackout (before 06:30 / school hours / after 21:00) and completely
        ignored the athlete's own Quiet Hours setting from Settings >
        Notifications — the same prefs row that already gates fuel-window
        pushes. 07:30 is outside the §2.1 blackout, but an athlete who
        extended their own quiet hours to end at 08:00 must still be
        respected here."""
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "practice", "2026-07-10")
        conn.execute(
            "INSERT INTO notification_prefs (profile_type, profile_id, quiet_hours_enabled, quiet_start, quiet_end) "
            "VALUES ('athlete', 1, 1, '22:00', '08:00')"
        )
        conn.commit()
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []

    def test_disabling_quiet_hours_entirely_still_allows_the_default_push(self, monkeypatch):
        """A user who turns Quiet Hours off entirely must not be newly
        blocked by this check — only the still-active §2.1 blackout applies."""
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "practice", "2026-07-10")
        conn.execute(
            "INSERT INTO notification_prefs (profile_type, profile_id, quiet_hours_enabled, quiet_start, quiet_end) "
            "VALUES ('athlete', 1, 0, '22:00', '08:00')"
        )
        conn.commit()
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert len(sent) == 1


# ─── _notify_athlete_fueliq — Trigger 2 (pregame) ──────────────────────────────

class TestPregameTrigger:
    def test_sends_two_hours_before_game(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "game", "2026-07-10", start_time="18:00")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 16, 0, tzinfo=PST)  # exactly 2hr before 18:00
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert len(sent) == 1
        row = conn.execute(
            "SELECT outcome FROM fueliq_push_events WHERE athlete_id = 1 AND trigger = 'pregame'"
        ).fetchone()
        assert row["outcome"] == "sent"

    def test_logs_skip_when_no_start_time(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "tournament", "2026-07-10", start_time=None)
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 16, 0, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []
        row = conn.execute(
            "SELECT outcome FROM fueliq_push_events WHERE athlete_id = 1 AND trigger = 'pregame'"
        ).fetchone()
        assert row["outcome"] == "skipped_no_start_time"

    def test_falls_through_to_second_game_with_start_time(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "game", "2026-07-10", start_time=None)
        _add_event(conn, 1, "game", "2026-07-10", start_time="18:00")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 16, 0, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert len(sent) == 1

    def test_respects_pregame_disabled_pref(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "game", "2026-07-10", start_time="18:00")
        _set_prefs(conn, 1, pregame_enabled=False)
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 16, 0, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []

    def test_quiet_hours_block_pregame_send(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        # Target time 2hr before 11:00 kickoff = 09:00, inside school-hours blackout.
        _add_event(conn, 1, "game", "2026-07-10", start_time="11:00")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 9, 0, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []


# ─── Daily cap ──────────────────────────────────────────────────────────────────

class TestDailyCap:
    def test_second_push_blocked_once_cap_reached(self, monkeypatch):
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        conn.executemany(
            "INSERT INTO notification_log (athlete_id, window_key, send_date, recipient, token) "
            "VALUES (1, ?, '2026-07-10', 'athlete', 'tok')",
            [("fueliq_x1",), ("fueliq_x2",)],
        )
        conn.commit()
        _add_event(conn, 1, "practice", "2026-07-10")
        sent = _patch_send(monkeypatch)

        now = datetime(2026, 7, 10, 7, 30, tzinfo=PST)
        fns._notify_athlete_fueliq(1, conn, now=now)

        assert sent == []


# ─── run_fueliq_notification_tick ───────────────────────────────────────────────

class TestRunFueliqNotificationTick:
    def test_noop_when_flag_disabled(self, monkeypatch):
        monkeypatch.setenv("FUELIQ_ENABLED", "false")
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_event(conn, 1, "practice", "2026-07-10")
        sent = _patch_send(monkeypatch)
        monkeypatch.setattr(fns, "get_conn", lambda: conn)

        fns.run_fueliq_notification_tick(now=datetime(2026, 7, 10, 7, 30, tzinfo=PST))

        assert sent == []

    def test_sends_across_multiple_athletes_when_enabled(self, monkeypatch):
        monkeypatch.setenv("FUELIQ_ENABLED", "true")
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_token(conn, "Tok2", athlete_id=2)
        _add_event(conn, 1, "practice", "2026-07-10")
        _add_event(conn, 2, "strength", "2026-07-10")
        sent = _patch_send(monkeypatch)
        monkeypatch.setattr(fns, "get_conn", lambda: conn)

        fns.run_fueliq_notification_tick(now=datetime(2026, 7, 10, 7, 30, tzinfo=PST))

        assert len(sent) == 2

    def test_one_athlete_failure_does_not_block_others(self, monkeypatch):
        monkeypatch.setenv("FUELIQ_ENABLED", "true")
        conn = _fueliq_notif_db()
        _add_token(conn, "Tok1", athlete_id=1)
        _add_token(conn, "Tok2", athlete_id=2)
        _add_event(conn, 2, "practice", "2026-07-10")
        sent = _patch_send(monkeypatch)
        monkeypatch.setattr(fns, "get_conn", lambda: conn)

        real_notify = fns._notify_athlete_fueliq

        def flaky_notify(athlete_id, conn, now=None):
            if athlete_id == 1:
                raise RuntimeError("boom")
            return real_notify(athlete_id, conn, now=now)

        monkeypatch.setattr(fns, "_notify_athlete_fueliq", flaky_notify)
        fns.run_fueliq_notification_tick(now=datetime(2026, 7, 10, 7, 30, tzinfo=PST))

        assert len(sent) == 1
