"""Unit tests for the Fuel IQ streak (api/services/fueliq_streak.py).

A genuinely separate streak from api/services/streak_service.py's meal-
confirmation streak — "did you log meals" and "did you learn something" are
different behaviors and shouldn't be conflated (see the Fuel IQ plan's Q5).
"""

from datetime import date, timedelta

import pytest

from api.database import get_conn
from api.services import fueliq_streak as fs


def _mk_conn():
    return get_conn()


def _fueliq_db():
    """Real shared Postgres test connection (tests/conftest.py already applies
    the full baseline schema + a module-scoped truncate/reseed). Explicitly
    resets athlete_id=1's Fuel IQ rows here so each test in this module gets
    clean state, since the module-scoped truncate only runs once per module,
    not once per test — unlike the old standalone sqlite3.connect(':memory:')
    this replaces, which gave every test a brand-new isolated DB for free."""
    conn = _mk_conn()
    conn.execute(
        "INSERT INTO athletes (id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (1, 'Alex', 15, 'female', 120, 5, 5) ON CONFLICT (id) DO NOTHING"
    )
    conn.execute("DELETE FROM fueliq_lesson_completions WHERE athlete_id = 1")
    conn.execute("DELETE FROM fueliq_quiz_attempts WHERE athlete_id = 1")
    conn.execute("DELETE FROM fueliq_badges_earned WHERE athlete_id = 1")
    conn.execute("DELETE FROM fueliq_athlete_progress WHERE athlete_id = 1")
    conn.commit()
    return conn


def _lesson_completion(conn, athlete_id, completed_at):
    lesson_id = conn.execute(
        "INSERT INTO fueliq_lessons "
        "(level, order_in_level, is_myth, title, hook, fact_body, takeaway, source_citation, review_status) "
        "VALUES (1, 1, 0, 'L', 'hook', 'fact', 'takeaway', 'cite', 'approved') RETURNING id"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO fueliq_lesson_completions (athlete_id, lesson_id, points_earned, completed_at) "
        "VALUES (%s, %s, 10, %s)",
        (athlete_id, lesson_id, completed_at),
    )
    conn.commit()


def test_qualifying_dates_from_lesson_completions():
    conn = _fueliq_db()
    _lesson_completion(conn, 1, "2026-06-10 10:00:00")
    _lesson_completion(conn, 1, "2026-06-11 10:00:00")
    assert fs._qualifying_dates(1, conn) == {"2026-06-10", "2026-06-11"}
    conn.close()


def test_current_streak_counts_consecutive_days():
    conn = _fueliq_db()
    today = date(2026, 6, 17)
    for days_ago in range(3):
        d = (today - timedelta(days=days_ago)).isoformat()
        _lesson_completion(conn, 1, f"{d} 10:00:00")
    assert fs.compute_current_streak(1, conn, today)["current"] == 3
    conn.close()


def test_no_activity_is_zero_streak():
    conn = _fueliq_db()
    assert fs.compute_current_streak(1, conn, date(2026, 6, 17))["current"] == 0
    conn.close()


def test_freeze_bridges_one_missed_day():
    conn = _fueliq_db()
    today = date(2026, 6, 17)
    _lesson_completion(conn, 1, f"{today.isoformat()} 10:00:00")
    # 06-16 missed
    _lesson_completion(conn, 1, f"{(today - timedelta(days=2)).isoformat()} 10:00:00")
    result = fs.compute_current_streak(1, conn, today)
    assert result["current"] == 2
    conn.close()


def test_register_activity_fires_milestone_at_seven_days():
    conn = _fueliq_db()
    today = date(2026, 6, 17)
    for days_ago in range(6, -1, -1):  # 7 consecutive days ending today
        d = (today - timedelta(days=days_ago)).isoformat()
        _lesson_completion(conn, 1, f"{d} 10:00:00")

    result = fs.register_activity(1, conn, today)
    assert result["current"] == 7
    assert result["just_reached_milestone"] == 7
    conn.close()


def test_register_activity_awards_milestone_bonus_points_once():
    conn = _fueliq_db()
    today = date(2026, 6, 17)
    for days_ago in range(6, -1, -1):
        d = (today - timedelta(days=days_ago)).isoformat()
        _lesson_completion(conn, 1, f"{d} 10:00:00")

    from api.services import fueliq_service as fq
    score_before = fq.get_progress(1, conn)["score"]
    fs.register_activity(1, conn, today)
    score_after = fq.get_progress(1, conn)["score"]
    assert score_after == score_before + 15  # fueliq_streak_milestone_bonus

    # Registering again the same day must not re-award the bonus.
    fs.register_activity(1, conn, today)
    assert fq.get_progress(1, conn)["score"] == score_after
    conn.close()


def test_register_activity_updates_progress_streak_columns():
    conn = _fueliq_db()
    today = date(2026, 6, 17)
    _lesson_completion(conn, 1, f"{today.isoformat()} 10:00:00")
    fs.register_activity(1, conn, today)

    from api.services import fueliq_service as fq
    progress = fq.get_progress(1, conn)
    assert progress["current_streak"] == 1
    assert progress["best_streak"] == 1
    conn.close()
