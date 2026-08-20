"""Unit tests for the Fuel Streak service (api/services/streak_service.py)."""

from datetime import date, timedelta

import pytest

from api.database import get_conn


def _mk_conn():
    return get_conn()


def test_streak_state_table_is_created():
    # streak_state is owned by db/postgres/001_baseline.sql (applied once per
    # test session) rather than created at runtime now. The old helper this
    # test used to call directly (db_migrations._create_streak_state) is
    # retired SQLite DDL (`datetime('now')` with no Postgres cast) that
    # errors immediately against Postgres even under CREATE TABLE IF NOT
    # EXISTS, since Postgres still resolves the DEFAULT expression's type
    # before checking whether the table already exists. Assert the real
    # (baseline-created) table's shape instead of trying to (re)create it.
    conn = _mk_conn()
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ("streak_state",),
    ).fetchall()
    cols = {r["column_name"] for r in rows}
    assert cols == {
        "athlete_id",
        "freeze_tokens",
        "last_celebrated_milestone",
        "updated_at",
    }
    conn.close()


from api.services import streak_service as ss


_STREAK_ATHLETE_IDS = (1, 7)


def _ensure_athletes(conn):
    # confirmations.athlete_id REFERENCES athletes(id), so every athlete_id
    # this file exercises must exist as a real row first.
    for aid in _STREAK_ATHLETE_IDS:
        conn.execute(
            "INSERT INTO athletes (id, parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
            "VALUES (%s, NULL, 'Alex', 14, 'Boy', 120, 5, 6) ON CONFLICT (id) DO NOTHING",
            (aid,),
        )


def _streak_db():
    """Real (shared) Postgres connection, reset to a clean slate for this test.

    confirmations/window_logs/report_config/streak_state/events/meal_plans
    all already exist via db/postgres/001_baseline.sql (applied once per test
    session; TRUNCATEd once per module by conftest's module-scoped _fresh_db
    fixture) — so unlike the old per-test in-memory SQLite DB, isolation here
    means clearing just the rows this file touches, not recreating tables.
    """
    conn = _mk_conn()
    conn.execute("DELETE FROM confirmations")
    conn.execute("DELETE FROM window_logs")
    conn.execute("DELETE FROM report_config")
    conn.execute("DELETE FROM streak_state")
    conn.execute("DELETE FROM meal_plans")
    conn.execute("DELETE FROM events")
    _ensure_athletes(conn)
    conn.execute(
        "INSERT INTO report_config (key, value, description, updated_at) VALUES (%s, %s, %s, sqlite_now())",
        ("streak_min_confirms_per_day", 1.0, ""),
    )
    conn.commit()
    return conn


def _confirm(conn, athlete_id, log_date, window_key="pre_event_meal", window_type="pre_fuel"):
    conn.execute(
        "INSERT INTO confirmations (athlete_id, log_date, window_key, window_type) VALUES (%s, %s, %s, %s)",
        (athlete_id, log_date, window_key, window_type),
    )
    conn.commit()


def test_qualifying_dates_from_confirmations():
    conn = _streak_db()
    _confirm(conn, 1, "2026-06-10")
    _confirm(conn, 1, "2026-06-11")
    assert ss._qualifying_dates(1, conn) == {"2026-06-10", "2026-06-11"}
    conn.close()


def test_qualifying_dates_union_with_window_logs():
    conn = _streak_db()
    _confirm(conn, 1, "2026-06-10")
    conn.execute(
        "INSERT INTO window_logs (athlete_id, window_id, log_date) VALUES (1, 'breakfast', '2026-06-12')"
    )
    conn.commit()
    assert ss._qualifying_dates(1, conn) == {"2026-06-10", "2026-06-12"}
    conn.close()


def test_best_streak_finds_longest_run():
    # 06-01,02,03 (run of 3), gap, 06-05,06 (run of 2) -> best 3
    qual = {"2026-06-01", "2026-06-02", "2026-06-03", "2026-06-05", "2026-06-06"}
    assert ss._best_streak(qual) == 3


def test_week_strip_is_sunday_to_saturday():
    # Wednesday 2026-06-17; Sunday of that week is 2026-06-14
    # qual has Mon 2026-06-15 (index 1) and Wed 2026-06-17 (index 3)
    qual = {"2026-06-15", "2026-06-17"}
    strip = ss._week_strip(qual, date(2026, 6, 17))
    assert strip == [False, True, False, True, False, False, False]


def test_current_streak_counts_consecutive_days():
    conn = _streak_db()
    today = date(2026, 6, 17)
    for days_ago in range(3):  # 06-17, 06-16, 06-15
        _confirm(conn, 1, (today - timedelta(days=days_ago)).isoformat())
    assert ss.compute_current_streak(1, conn, today)["current"] == 3
    conn.close()


def test_today_not_logged_does_not_break_streak():
    """Today is still 'open' — a prior streak stays alive until the day ends."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())  # yesterday
    _confirm(conn, 1, (today - timedelta(days=2)).isoformat())  # day before
    # today NOT logged -> streak counts back from yesterday = 2 (not 0)
    assert ss.compute_current_streak(1, conn, today)["current"] == 2
    conn.close()


def test_freeze_bridges_one_missed_day():
    """One missed day within the last 7 is auto-protected (freeze)."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())                          # today
    # 06-16 MISSED
    _confirm(conn, 1, (today - timedelta(days=2)).isoformat())    # 06-15
    _confirm(conn, 1, (today - timedelta(days=3)).isoformat())    # 06-14
    result = ss.compute_current_streak(1, conn, today)
    assert result["current"] == 3          # today + 06-15 + 06-14, bridging 06-16
    assert result["freeze_used_this_week"] is True
    conn.close()


def test_freeze_bridges_at_most_one_day():
    """Two consecutive missed days cannot both be bridged with a single token."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())                          # today
    # 06-16 and 06-15 BOTH missed
    _confirm(conn, 1, (today - timedelta(days=3)).isoformat())    # 06-14
    # streak = just today; cannot reach 06-14 across a 2-day gap
    assert ss.compute_current_streak(1, conn, today)["current"] == 1
    conn.close()


def test_no_confirmations_is_zero():
    conn = _streak_db()
    assert ss.compute_current_streak(1, conn, date(2026, 6, 17))["current"] == 0
    conn.close()


def _streak_db_with_state():
    # streak_state already exists (created by the baseline schema) and is
    # cleared inside _streak_db() above; the extra _create_streak_state()
    # call this used to make is the same retired SQLite DDL flagged in
    # test_streak_state_table_is_created, so this is now just an alias.
    return _streak_db()


def test_get_streak_block_shape():
    conn = _streak_db_with_state()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())
    block = ss.get_streak(1, conn, today)
    assert block["current"] == 2
    assert block["today_done"] is True
    assert block["next_milestone"] == 5          # ladder 2/5/10/21, current 2 -> next 5
    assert block["just_reached_milestone"] is None  # read path never celebrates
    assert len(block["week_strip"]) == 7
    conn.close()


def test_register_confirmation_fires_milestone_once():
    conn = _streak_db_with_state()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())  # current = 2 -> tier 2

    first = ss.register_confirmation(1, conn, today)
    assert first["just_reached_milestone"] == 2   # crosses tier 2

    second = ss.register_confirmation(1, conn, today)
    assert second["just_reached_milestone"] is None  # already celebrated
    conn.close()


def test_register_confirmation_recelebrates_after_reset():
    conn = _streak_db_with_state()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())
    _confirm(conn, 1, (today - timedelta(days=1)).isoformat())
    assert ss.register_confirmation(1, conn, today)["just_reached_milestone"] == 2

    # Simulate a later day where the streak has fallen back to 1, then climbs to 2 again.
    conn.execute("DELETE FROM confirmations")
    later = date(2026, 7, 1)
    _confirm(conn, 1, later.isoformat())
    _confirm(conn, 1, (later - timedelta(days=1)).isoformat())
    # last_celebrated reset happens on the intervening low-streak registration
    ss.register_confirmation(1, conn, later - timedelta(days=1))  # current 1 -> tier 0, resets marker
    assert ss.register_confirmation(1, conn, later)["just_reached_milestone"] == 2
    conn.close()


def test_freeze_not_reported_when_streak_runs_out_of_history():
    """A bridge past the start of history is not a 'used' freeze (no day follows it)."""
    conn = _streak_db()
    today = date(2026, 6, 17)
    _confirm(conn, 1, today.isoformat())  # day-1 athlete: only today logged
    result = ss.compute_current_streak(1, conn, today)
    assert result["current"] == 1
    assert result["freeze_used_this_week"] is False
    conn.close()


def test_register_is_importable_by_route_layer():
    # Guards the exact call the route makes: register_confirmation(athlete_id, conn, today=log_date)
    conn = _streak_db_with_state()
    _confirm(conn, 7, "2026-06-17")
    block = ss.register_confirmation(7, conn, today="2026-06-17")
    assert block["current"] == 1
    assert "just_reached_milestone" in block
    conn.close()


def test_build_today_view_includes_streak(monkeypatch):
    """build_today_view must add a 'streak' block computed from confirmations."""
    import api.services.today_service as tsvc

    # athletes/events/meal_plans already exist via the baseline schema (and
    # athlete id 1 is ensured by _streak_db()), so no ad hoc table creation
    # is needed here — just the confirmation row build_today_view reads.
    conn = _streak_db_with_state()
    today = "2026-06-17"
    _confirm(conn, 1, today)

    # build_today_view imports these locally from their own modules, so patch THERE.
    import api.services.window_templates as wt
    import api.services.nutrition_analysis as na
    monkeypatch.setattr(
        wt, "generate_windows_for_day",
        lambda athlete_id, day, events, force_v2=False: {"day_type": "rest", "windows": []},
        raising=False,
    )
    monkeypatch.setattr(na, "get_week_start", lambda: "2026-06-15", raising=False)
    monkeypatch.setattr(na, "get_week_dates",
                        lambda ws: [f"2026-06-{15+i:02d}" for i in range(7)], raising=False)

    view = tsvc.build_today_view(1, conn, today=today)
    assert "streak" in view
    assert view["streak"]["current"] == 1
    assert view["streak"]["today_done"] is True
    conn.close()
