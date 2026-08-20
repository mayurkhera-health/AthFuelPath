"""Unit tests for the Fuel IQ Daily Challenge feature (schema + import script).

A deliberately separate feature from lessons/Myth Buster: one global
challenge published per calendar day, same for every athlete, with its own
content table, answers table, and streak — see
api/services/db_migrations.py::_create_fueliq_daily_challenge_tables.
"""

from datetime import date

import psycopg
import pytest

from api.database import get_conn
from api.services import fueliq_daily_challenge_service as fdc


def _mk_conn():
    return get_conn()


def _clean(conn):
    """All tables here (athletes, expo_push_tokens, fueliq_daily_challenges,
    fueliq_daily_challenge_answers, fueliq_daily_challenge_streak,
    fueliq_athlete_progress, report_config) already exist via
    db/postgres/001_baseline.sql, applied once per session by
    tests/conftest.py — the old per-test _create_*/executescript calls built
    a throwaway SQLite schema that's now redundant (and those functions are
    retired raw SQLite DDL that would error immediately against Postgres).

    tests/conftest.py's module-scoped `_fresh_db` fixture only truncates once
    per module (not per test function), and this file reuses fixed ids/dates
    (athlete id=1, challenge_date='2026-07-10') across many tests in the same
    module — so clear out this file's own rows (children before parents, to
    respect FKs) before each test builds its fixture data, the same
    isolation the old per-test sqlite3.connect(':memory:') gave for free.
    """
    conn.execute("DELETE FROM fueliq_daily_challenge_answers")
    conn.execute("DELETE FROM fueliq_daily_challenge_streak")
    conn.execute("DELETE FROM fueliq_athlete_progress")
    conn.execute("DELETE FROM fueliq_daily_challenges")
    conn.execute("DELETE FROM expo_push_tokens")
    conn.execute("DELETE FROM athletes")
    conn.execute("UPDATE report_config SET value = 10 WHERE key = 'fueliq_daily_challenge_points'")
    conn.commit()


def _daily_challenge_db():
    conn = _mk_conn()
    _clean(conn)
    return conn


def _item(title="T1", hook="hook", verdict="myth", science_text="science", source_citation=None):
    return {
        "title": title,
        "hook": hook,
        "verdict": verdict,
        "science_text": science_text,
        "source_citation": source_citation,
    }


def _seed_challenge(conn, challenge_date, title="T1", verdict="myth", points=10):
    conn.execute(
        "INSERT INTO fueliq_daily_challenges "
        "(challenge_date, title, hook, verdict, science_text, points) "
        "VALUES (%s, %s, 'hook', %s, 'science', %s)",
        (challenge_date, title, verdict, points),
    )
    conn.commit()


def _add_athlete(conn, athlete_id):
    conn.execute(
        "INSERT INTO athletes (id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, 'A', 14, 'Girl', 100, 5, 0)",
        (athlete_id,),
    )
    conn.commit()


def test_fueliq_daily_challenge_tables_are_created():
    # _create_fueliq_daily_challenge_tables() (api/services/db_migrations.py) is
    # retired raw SQLite DDL (AUTOINCREMENT, datetime('now')) that errors
    # immediately against Postgres — schema ownership moved to
    # db/postgres/001_baseline.sql, applied once per session by
    # tests/conftest.py. This verifies the same three tables exist in that
    # baseline schema instead of invoking the retired SQLite-only creation
    # function directly.
    conn = _mk_conn()
    tables = {
        r["table_name"]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'fueliq_daily_challenge%'"
        ).fetchall()
    }
    assert tables == {
        "fueliq_daily_challenges",
        "fueliq_daily_challenge_answers",
        "fueliq_daily_challenge_streak",
    }
    conn.close()


def test_fueliq_daily_challenges_challenge_date_is_unique():
    conn = _mk_conn()
    _clean(conn)
    conn.execute(
        "INSERT INTO fueliq_daily_challenges (challenge_date, title, hook, verdict, science_text) "
        "VALUES ('2026-07-10', 'T1', 'hook1', 'real', 'science1')"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO fueliq_daily_challenges (challenge_date, title, hook, verdict, science_text) "
            "VALUES ('2026-07-10', 'T2', 'hook2', 'myth', 'science2')"
        )
        conn.commit()
        assert False, "expected UNIQUE constraint on challenge_date to raise"
    except psycopg.errors.UniqueViolation:
        conn.rollback()
    conn.close()


def test_fueliq_daily_challenge_answers_unique_per_athlete_per_date():
    conn = _mk_conn()
    _clean(conn)
    _add_athlete(conn, 1)
    conn.execute(
        "INSERT INTO fueliq_daily_challenge_answers (athlete_id, challenge_date, guess, correct) "
        "VALUES (1, '2026-07-10', 'real', 1)"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO fueliq_daily_challenge_answers (athlete_id, challenge_date, guess, correct) "
            "VALUES (1, '2026-07-10', 'myth', 0)"
        )
        conn.commit()
        assert False, "expected UNIQUE constraint on (athlete_id, challenge_date) to raise"
    except psycopg.errors.UniqueViolation:
        conn.rollback()
    conn.close()


# ── Import script (fueliq_daily_challenge_service.import_daily_challenges) ──

def test_import_assigns_sequential_dates_from_today_when_nothing_scheduled():
    conn = _daily_challenge_db()
    today = date(2026, 7, 10)
    inserted = fdc.import_daily_challenges(
        conn, [_item(title="T1"), _item(title="T2"), _item(title="T3")], today=today
    )
    assert [r["challenge_date"] for r in inserted] == ["2026-07-10", "2026-07-11", "2026-07-12"]
    rows = conn.execute(
        "SELECT title, challenge_date FROM fueliq_daily_challenges ORDER BY challenge_date"
    ).fetchall()
    assert [r["title"] for r in rows] == ["T1", "T2", "T3"]
    conn.close()


def test_import_continues_after_the_latest_already_scheduled_date():
    conn = _daily_challenge_db()
    today = date(2026, 7, 10)
    fdc.import_daily_challenges(conn, [_item(title="T1")], today=today)
    inserted = fdc.import_daily_challenges(conn, [_item(title="T2")], today=today)
    # First batch landed on 07-10 (today); the second must continue from
    # 07-11, not collide back onto "today" again.
    assert inserted[0]["challenge_date"] == "2026-07-11"
    conn.close()


def test_import_is_idempotent_by_title():
    conn = _daily_challenge_db()
    today = date(2026, 7, 10)
    fdc.import_daily_challenges(conn, [_item(title="T1")], today=today)
    second = fdc.import_daily_challenges(conn, [_item(title="T1"), _item(title="T2")], today=today)
    # T1 already exists — only T2 is newly inserted.
    assert [r["title"] for r in second] == ["T2"]
    count = conn.execute("SELECT COUNT(*) AS c FROM fueliq_daily_challenges").fetchone()["c"]
    assert count == 2
    conn.close()


def test_import_stamps_points_from_config():
    conn = _daily_challenge_db()
    conn.execute("UPDATE report_config SET value = 20 WHERE key = 'fueliq_daily_challenge_points'")
    conn.commit()
    fdc.import_daily_challenges(conn, [_item(title="T1")], today=date(2026, 7, 10))
    points = conn.execute(
        "SELECT points FROM fueliq_daily_challenges WHERE title = 'T1'"
    ).fetchone()["points"]
    assert points == 20
    conn.close()


def test_import_rejects_item_missing_required_field():
    conn = _daily_challenge_db()
    bad = _item(title="T1")
    del bad["science_text"]
    with pytest.raises(ValueError):
        fdc.import_daily_challenges(conn, [bad], today=date(2026, 7, 10))
    # Nothing partially inserted — validation happens before any writes.
    count = conn.execute("SELECT COUNT(*) AS c FROM fueliq_daily_challenges").fetchone()["c"]
    assert count == 0
    conn.close()


def test_import_rejects_invalid_verdict():
    conn = _daily_challenge_db()
    with pytest.raises(ValueError):
        fdc.import_daily_challenges(
            conn, [_item(title="T1", verdict="definitely-real")], today=date(2026, 7, 10)
        )
    conn.close()


# ── get_todays_challenge ─────────────────────────────────────────────────────

def test_get_todays_challenge_returns_none_when_nothing_scheduled():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    result = fdc.get_todays_challenge(1, conn, today=date(2026, 7, 10))
    assert result["challenge"] is None
    assert result["streak"] == {"current": 0, "best": 0}
    assert result["total_completed"] == 0
    conn.close()


def test_get_todays_challenge_hides_verdict_and_science_before_answering():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10", title="T1")
    result = fdc.get_todays_challenge(1, conn, today=date(2026, 7, 10))
    challenge = result["challenge"]
    assert challenge["title"] == "T1"
    assert challenge["answered"] is False
    assert "verdict" not in challenge
    assert "science_text" not in challenge
    conn.close()


def test_get_todays_challenge_shows_guess_and_correctness_once_answered():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10", title="T1", verdict="myth")
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    result = fdc.get_todays_challenge(1, conn, today=date(2026, 7, 10))
    challenge = result["challenge"]
    assert challenge["answered"] is True
    assert challenge["guess"] == "myth"
    assert challenge["correct"] is True
    conn.close()


# ── submit_daily_challenge_verdict ───────────────────────────────────────────

def test_submit_daily_challenge_verdict_correct_guess():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10", verdict="myth", points=10)
    result = fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    assert result["already_answered"] is False
    assert result["correct"] is True
    assert result["science_text"] == "science"
    assert result["points_earned"] == 10
    conn.close()


def test_submit_daily_challenge_verdict_incorrect_guess_still_awards_points():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10", verdict="myth", points=10)
    result = fdc.submit_daily_challenge_verdict(1, "real", conn, today=date(2026, 7, 10))
    assert result["correct"] is False
    assert result["points_earned"] == 10
    conn.close()


def test_submit_daily_challenge_verdict_is_idempotent_no_double_award():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10", verdict="myth")
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    second = fdc.submit_daily_challenge_verdict(1, "real", conn, today=date(2026, 7, 10))
    assert second["already_answered"] is True
    assert second["points_earned"] == 0
    # The idempotent replay must not overwrite the original guess/correctness.
    result = fdc.get_todays_challenge(1, conn, today=date(2026, 7, 10))
    assert result["challenge"]["guess"] == "myth"
    conn.close()


def test_submit_daily_challenge_verdict_raises_when_nothing_scheduled():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    with pytest.raises(ValueError):
        fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    conn.close()


def test_submit_daily_challenge_verdict_does_not_touch_shared_fueliq_score():
    """Deliberately independent from the lesson/rank score pool — completing
    the Daily Challenge must never move an athlete's Rank or unlock a Level."""
    conn = _daily_challenge_db()
    # fueliq_athlete_progress already exists via db/postgres/001_baseline.sql
    # (the old inline CREATE TABLE built a throwaway SQLite copy of it).
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10", verdict="myth", points=10)
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    row = conn.execute("SELECT COUNT(*) AS c FROM fueliq_athlete_progress").fetchone()
    assert row["c"] == 0  # never touched — no progress row was ever created
    conn.close()


# ── Streak ───────────────────────────────────────────────────────────────────

def test_streak_is_one_after_first_ever_answer():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-10")
    result = fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    assert result["streak"] == {"current": 1, "best": 1}
    conn.close()


def test_streak_increments_on_consecutive_days():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-08", title="D1")
    _seed_challenge(conn, "2026-07-09", title="D2")
    _seed_challenge(conn, "2026-07-10", title="D3")
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 8))
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 9))
    result = fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    assert result["streak"] == {"current": 3, "best": 3}
    conn.close()


def test_streak_resets_after_a_missed_day_no_freeze_forgiveness():
    """Deliberately stricter than the lesson streak (fueliq_streak.py's freeze
    tokens) — a missed day always breaks the Daily Challenge streak, which is
    the point of the "answer today or lose it" urgency."""
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-08", title="D1")
    # 07-09 skipped
    _seed_challenge(conn, "2026-07-10", title="D2")
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 8))
    result = fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 10))
    assert result["streak"] == {"current": 1, "best": 1}
    conn.close()


def test_streak_best_persists_after_current_resets():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-08", title="D1")
    _seed_challenge(conn, "2026-07-09", title="D2")
    # 07-10 skipped
    _seed_challenge(conn, "2026-07-11", title="D3")
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 8))
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 9))
    result = fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 11))
    assert result["streak"] == {"current": 1, "best": 2}
    conn.close()


def test_total_completed_counts_across_the_athletes_history():
    conn = _daily_challenge_db()
    _add_athlete(conn, 1)
    _seed_challenge(conn, "2026-07-08", title="D1")
    _seed_challenge(conn, "2026-07-09", title="D2")
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 8))
    fdc.submit_daily_challenge_verdict(1, "myth", conn, today=date(2026, 7, 9))
    result = fdc.get_todays_challenge(1, conn, today=date(2026, 7, 9))
    assert result["total_completed"] == 2
    conn.close()


# ── Migration: push_sent_at ──────────────────────────────────────────────────
#
# _add_push_sent_to_daily_challenges() (api/services/db_migrations.py) is
# retired raw SQLite DDL (PRAGMA table_info + ALTER TABLE) that errors
# immediately against Postgres — the column it used to add is now a
# permanent part of the baseline schema (db/postgres/001_baseline.sql), so
# these two tests check for the column's presence (and single occurrence)
# in that baseline schema instead of invoking the retired function.

def test_push_sent_at_column_is_added():
    conn = _daily_challenge_db()
    cols = [
        r["column_name"]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'fueliq_daily_challenges'"
        ).fetchall()
    ]
    assert "push_sent_at" in cols
    conn.close()


def test_add_push_sent_column_is_idempotent():
    conn = _daily_challenge_db()
    cols = [
        r["column_name"]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'fueliq_daily_challenges'"
        ).fetchall()
    ]
    assert cols.count("push_sent_at") == 1  # never duplicated — running the old migration twice must not error
    conn.close()


# ── run_daily_challenge_push ─────────────────────────────────────────────────

def _add_token(conn, token, athlete_id=None, parent_id=None):
    conn.execute(
        "INSERT INTO expo_push_tokens (athlete_id, parent_id, token) VALUES (%s, %s, %s)",
        (athlete_id, parent_id, token),
    )
    conn.commit()


def test_push_noops_when_nothing_scheduled_today():
    conn = _daily_challenge_db()
    result = fdc.run_daily_challenge_push(conn, today=date(2026, 7, 10))
    assert result == {"sent": False, "reason": "no_challenge_today"}
    conn.close()


def test_push_noops_when_no_tokens_registered():
    conn = _daily_challenge_db()
    _seed_challenge(conn, "2026-07-10")
    result = fdc.run_daily_challenge_push(conn, today=date(2026, 7, 10))
    assert result == {"sent": False, "reason": "no_tokens"}
    conn.close()


def test_push_sends_to_athlete_tokens_only_not_parent_tokens(monkeypatch):
    conn = _daily_challenge_db()
    _seed_challenge(conn, "2026-07-10")
    _add_token(conn, "AthleteToken1", athlete_id=1)
    _add_token(conn, "AthleteToken2", athlete_id=2)
    _add_token(conn, "ParentToken1", parent_id=99)

    sent_to = {}

    def fake_send(tokens, title, body, data=None):
        sent_to["tokens"] = tokens
        sent_to["title"] = title
        sent_to["body"] = body
        sent_to["data"] = data
        return True

    monkeypatch.setattr("api.services.notification_service.send_expo_push", fake_send)
    result = fdc.run_daily_challenge_push(conn, today=date(2026, 7, 10))
    assert result["sent"] is True
    assert result["recipient_count"] == 2
    assert sorted(sent_to["tokens"]) == ["AthleteToken1", "AthleteToken2"]
    assert sent_to["title"]
    assert sent_to["body"]
    assert sent_to["data"] == {"type": "daily_challenge"}
    conn.close()


def test_push_is_idempotent_never_sends_twice_same_day(monkeypatch):
    conn = _daily_challenge_db()
    _seed_challenge(conn, "2026-07-10")
    _add_token(conn, "AthleteToken1", athlete_id=1)

    calls = {"n": 0}

    def fake_send(tokens, title, body, data=None):
        calls["n"] += 1
        return True

    monkeypatch.setattr("api.services.notification_service.send_expo_push", fake_send)
    first = fdc.run_daily_challenge_push(conn, today=date(2026, 7, 10))
    second = fdc.run_daily_challenge_push(conn, today=date(2026, 7, 10))
    assert first["sent"] is True
    assert second == {"sent": False, "reason": "already_sent"}
    assert calls["n"] == 1
    conn.close()


def test_push_marks_push_sent_at_on_the_challenge_row(monkeypatch):
    conn = _daily_challenge_db()
    _seed_challenge(conn, "2026-07-10")
    _add_token(conn, "AthleteToken1", athlete_id=1)
    monkeypatch.setattr("api.services.notification_service.send_expo_push", lambda t, ti, b, data=None: True)
    fdc.run_daily_challenge_push(conn, today=date(2026, 7, 10))
    row = conn.execute(
        "SELECT push_sent_at FROM fueliq_daily_challenges WHERE challenge_date = '2026-07-10'"
    ).fetchone()
    assert row["push_sent_at"] is not None
    conn.close()
