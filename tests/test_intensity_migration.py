"""Tests for the additive intensity migrations."""

import sqlite3

from api.services.db_migrations import (
    _add_intensity_to_events,
    _add_intensity_to_daily_targets,
)


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _seed_schema(conn):
    conn.executescript("""
        CREATE TABLE athletes (
            id INTEGER PRIMARY KEY, competition_level TEXT
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY, athlete_id INTEGER,
            event_name TEXT, event_type TEXT, event_date TEXT
        );
        CREATE TABLE daily_targets (
            id INTEGER PRIMARY KEY, athlete_id INTEGER, target_date TEXT
        );
    """)


def test_events_intensity_column_created_and_backfilled():
    conn = _mk_conn()
    _seed_schema(conn)
    conn.execute("INSERT INTO athletes (id, competition_level) VALUES (1, 'elite_club')")
    conn.execute("INSERT INTO athletes (id, competition_level) VALUES (2, 'recreational')")
    conn.execute("INSERT INTO events (id, athlete_id, event_name, event_type, event_date) VALUES (10, 1, 'Game', 'game', '2026-06-21')")
    conn.execute("INSERT INTO events (id, athlete_id, event_name, event_type, event_date) VALUES (11, 1, 'Yoga', 'rest', '2026-06-22')")
    conn.execute("INSERT INTO events (id, athlete_id, event_name, event_type, event_date) VALUES (12, 2, 'Game', 'game', '2026-06-21')")

    _add_intensity_to_events(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    assert "intensity" in cols
    rows = {r["id"]: r["intensity"] for r in conn.execute("SELECT id, intensity FROM events").fetchall()}
    assert rows[10] == "high"   # elite_club game
    assert rows[11] == "low"    # rest floors to low
    assert rows[12] == "low"    # recreational game


def test_events_migration_is_idempotent():
    conn = _mk_conn()
    _seed_schema(conn)
    _add_intensity_to_events(conn)
    _add_intensity_to_events(conn)  # must not raise
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    assert cols.count("intensity") == 1


def test_daily_targets_intensity_column_created():
    conn = _mk_conn()
    _seed_schema(conn)
    _add_intensity_to_daily_targets(conn)
    _add_intensity_to_daily_targets(conn)  # idempotent
    cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_targets)").fetchall()}
    assert "intensity" in cols
