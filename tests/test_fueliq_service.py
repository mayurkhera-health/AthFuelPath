"""Unit tests for Fuel IQ (api/services/fueliq_service.py)."""

import sqlite3

import pytest

from api.services.db_migrations import _create_fueliq_tables, _create_report_config
from api.services import fueliq_service as fq


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fueliq_db():
    """In-memory DB with athletes + the fueliq_* tables the service reads/writes."""
    conn = _mk_conn()
    conn.executescript("""
        CREATE TABLE athletes (id INTEGER PRIMARY KEY, first_name TEXT, age INTEGER);
        INSERT INTO athletes (id, first_name, age) VALUES (1, 'Alex', 14);
        INSERT INTO athletes (id, first_name, age) VALUES (2, 'Sam', 14);
    """)
    _create_fueliq_tables(conn)
    _create_report_config(conn)
    conn.commit()
    return conn


def _add_athlete(conn, athlete_id, age, score=None):
    conn.execute(
        "INSERT INTO athletes (id, first_name, age) VALUES (?, 'Cohort', ?)", (athlete_id, age)
    )
    if score is not None:
        conn.execute(
            "INSERT INTO fueliq_athlete_progress (athlete_id, score) VALUES (?, ?)",
            (athlete_id, score),
        )
    conn.commit()


def _insert_lesson(conn, points=10, level=1, order_in_level=1, category=None, title="Test Lesson"):
    cur = conn.execute(
        "INSERT INTO fueliq_lessons "
        "(level, order_in_level, is_myth, title, hook, fact_body, takeaway, "
        " source_citation, points, review_status, category) "
        "VALUES (?, ?, 0, ?, 'hook', 'fact', 'takeaway', 'cite', ?, 'approved', ?)",
        (level, order_in_level, title, points, category),
    )
    conn.commit()
    return cur.lastrowid


def _insert_question(conn, lesson_id, correct_option="b"):
    cur = conn.execute(
        "INSERT INTO fueliq_questions "
        "(lesson_id, question_text, option_a, option_b, option_c, correct_option, "
        " explanation, misconception_tag, order_in_lesson) "
        "VALUES (?, 'q', 'A', 'B', 'C', ?, 'because', 'tag1', 1)",
        (lesson_id, correct_option),
    )
    conn.commit()
    return cur.lastrowid


def test_fueliq_tables_are_created():
    conn = _mk_conn()
    conn.executescript("CREATE TABLE athletes (id INTEGER PRIMARY KEY);")
    _create_fueliq_tables(conn)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fueliq_%'"
        ).fetchall()
    }
    assert tables == {
        "fueliq_lessons",
        "fueliq_questions",
        "fueliq_athlete_progress",
        "fueliq_lesson_completions",
        "fueliq_quiz_attempts",
        "fueliq_badges_earned",
    }
    conn.close()


@pytest.mark.parametrize(
    "level,threshold",
    [(1, 0), (2, 65), (3, 120), (4, 145), (5, 165)],
)
def test_level_unlock_threshold(level, threshold):
    assert fq.level_unlocked(threshold, level) is True


@pytest.mark.parametrize(
    "level,threshold",
    [(2, 65), (3, 120), (4, 145), (5, 165)],
)
def test_level_locked_below_threshold(level, threshold):
    assert fq.level_unlocked(threshold - 1, level) is False


def test_level_1_always_unlocked_at_baseline_score():
    assert fq.level_unlocked(50, 1) is True


def test_get_progress_creates_default_row_for_new_athlete():
    conn = _fueliq_db()
    progress = fq.get_progress(1, conn)
    assert progress["score"] == 50
    assert progress["current_streak"] == 0
    assert progress["best_streak"] == 0
    conn.close()


def test_get_progress_is_idempotent():
    conn = _fueliq_db()
    fq.get_progress(1, conn)
    row_count = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_athlete_progress WHERE athlete_id = 1"
    ).fetchone()["c"]
    fq.get_progress(1, conn)
    row_count_again = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_athlete_progress WHERE athlete_id = 1"
    ).fetchone()["c"]
    assert row_count == 1
    assert row_count_again == 1
    conn.close()


def test_report_config_seeds_fueliq_point_values():
    conn = _mk_conn()
    _create_report_config(conn)
    rows = {
        r["key"]: r["value"]
        for r in conn.execute(
            "SELECT key, value FROM report_config WHERE key LIKE 'fueliq_%'"
        ).fetchall()
    }
    assert rows == {
        "fueliq_lesson_points": 10.0,
        "fueliq_perfect_quiz_bonus": 5.0,
        "fueliq_streak_milestone_bonus": 15.0,
        "fueliq_review_points": 5.0,
        "fueliq_daily_challenge_points": 10.0,
    }
    conn.close()


def _lesson_item(title, level=1, order_in_level=1, category="hydration", num_questions=3):
    return {
        "level": level,
        "order_in_level": order_in_level,
        "title": title,
        "hook": f"{title} hook",
        "fact_body": f"{title} fact body",
        "takeaway": f"{title} takeaway",
        "category": category,
        "source_citation": "Test Source Flyer",
        "questions": [
            {
                "question_text": f"{title} question {i}",
                "option_a": "A",
                "option_b": "B",
                "option_c": "C",
                "correct_option": "a",
                "explanation": f"{title} explanation {i}",
            }
            for i in range(1, num_questions + 1)
        ],
    }


def test_import_lessons_creates_lessons_and_questions():
    conn = _fueliq_db()
    inserted = fq.import_lessons(conn, [_lesson_item("Hydration"), _lesson_item("Sweat", order_in_level=2)])
    assert [r["title"] for r in inserted] == ["Hydration", "Sweat"]
    lessons = conn.execute(
        "SELECT title, level, is_myth, review_status FROM fueliq_lessons WHERE is_myth = 0"
    ).fetchall()
    assert len(lessons) == 2
    # Imported content is never pre-approved by default — the RDN sign-off gate
    # (spec §11.1) must be a deliberate, explicit argument, not an accident of import.
    assert all(r["review_status"] == "draft" for r in lessons)
    assert all(r["level"] == 1 for r in lessons)
    conn.close()


def test_import_lessons_is_idempotent_by_title():
    conn = _fueliq_db()
    fq.import_lessons(conn, [_lesson_item("Hydration")])
    second = fq.import_lessons(conn, [_lesson_item("Hydration"), _lesson_item("Sweat", order_in_level=2)])
    assert [r["title"] for r in second] == ["Sweat"]
    count = conn.execute("SELECT COUNT(*) AS c FROM fueliq_lessons").fetchone()["c"]
    assert count == 2
    conn.close()


def test_import_lessons_stamps_approved_review_status_when_requested():
    conn = _fueliq_db()
    fq.import_lessons(conn, [_lesson_item("Hydration")], review_status="approved", reviewed_by="RDN Jane")
    row = conn.execute(
        "SELECT review_status, reviewed_by, review_date FROM fueliq_lessons WHERE title = 'Hydration'"
    ).fetchone()
    assert row["review_status"] == "approved"
    assert row["reviewed_by"] == "RDN Jane"
    assert row["review_date"] is not None
    conn.close()


def test_import_lessons_gives_each_lesson_its_own_questions():
    conn = _fueliq_db()
    fq.import_lessons(conn, [_lesson_item("Hydration", num_questions=3), _lesson_item("Sweat", order_in_level=2, num_questions=2)])
    lessons = conn.execute(
        "SELECT id, title FROM fueliq_lessons WHERE is_myth = 0 ORDER BY order_in_level"
    ).fetchall()
    counts = {}
    for lesson in lessons:
        questions = conn.execute(
            "SELECT correct_option FROM fueliq_questions WHERE lesson_id = ?", (lesson["id"],)
        ).fetchall()
        counts[lesson["title"]] = len(questions)
        assert all(q["correct_option"] in ("a", "b", "c") for q in questions)
    assert counts == {"Hydration": 3, "Sweat": 2}
    conn.close()


def test_import_lessons_questions_are_answerable_end_to_end():
    """The imported quiz must actually work through submit_quiz_answer /
    complete_lesson — not just exist as rows."""
    conn = _fueliq_db()
    fq.import_lessons(conn, [_lesson_item("Hydration", num_questions=3)])
    lesson = conn.execute(
        "SELECT id FROM fueliq_lessons WHERE is_myth = 0 AND order_in_level = 1"
    ).fetchone()
    questions = conn.execute(
        "SELECT id, correct_option FROM fueliq_questions WHERE lesson_id = ? ORDER BY order_in_lesson",
        (lesson["id"],),
    ).fetchall()
    assert len(questions) == 3  # guards against the empty-list-passes-vacuously bug
    answers = [fq.submit_quiz_answer(1, q["id"], q["correct_option"], conn) for q in questions]
    assert all(a["correct"] is True for a in answers)

    result = fq.complete_lesson(1, lesson["id"], conn, perfect_quiz=True)
    assert result["already_completed"] is False
    assert result["points_earned"] == 15  # 10 lesson points + 5 perfect-quiz bonus
    conn.close()


def test_complete_lesson_awards_points_and_updates_score():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn, points=10)
    result = fq.complete_lesson(1, lesson_id, conn)
    assert result["points_earned"] == 10
    assert result["already_completed"] is False
    assert fq.get_progress(1, conn)["score"] == 60
    conn.close()


def test_complete_lesson_perfect_quiz_bonus():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn, points=10)
    result = fq.complete_lesson(1, lesson_id, conn, perfect_quiz=True)
    assert result["points_earned"] == 15  # 10 + fueliq_perfect_quiz_bonus (5)
    assert fq.get_progress(1, conn)["score"] == 65
    conn.close()


def test_complete_lesson_is_idempotent_no_double_award():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn, points=10)
    fq.complete_lesson(1, lesson_id, conn)
    second = fq.complete_lesson(1, lesson_id, conn)
    assert second["already_completed"] is True
    assert second["points_earned"] == 0
    assert fq.get_progress(1, conn)["score"] == 60
    conn.close()


def test_submit_quiz_answer_correct():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    question_id = _insert_question(conn, lesson_id, correct_option="b")
    result = fq.submit_quiz_answer(1, question_id, "b", conn)
    assert result["correct"] is True
    assert result["explanation"] == "because"
    conn.close()


def test_submit_quiz_answer_incorrect_has_no_penalty():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    question_id = _insert_question(conn, lesson_id, correct_option="b")
    result = fq.submit_quiz_answer(1, question_id, "a", conn)
    assert result["correct"] is False
    assert result["misconception_tag"] == "tag1"
    # Wrong answers cost nothing (spec §3.5) — score is untouched by quiz answers,
    # only by lesson completion.
    assert fq.get_progress(1, conn)["score"] == 50
    conn.close()


# ── Badges ───────────────────────────────────────────────────────────────────

def test_first_whistle_awarded_on_first_lesson_completion():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    assert fq.check_and_award_badges(1, conn) == []  # nothing completed yet
    # complete_lesson awards inline, so the badge shows up in ITS return value —
    # a second explicit check afterward correctly finds nothing new to award.
    result = fq.complete_lesson(1, lesson_id, conn)
    assert result["newly_earned_badges"] == ["first_whistle"]
    conn.close()


def test_badge_award_is_idempotent():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    fq.complete_lesson(1, lesson_id, conn)
    fq.check_and_award_badges(1, conn)
    assert fq.check_and_award_badges(1, conn) == []  # already earned, not re-awarded
    earned = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_badges_earned WHERE athlete_id = 1 AND badge_key = 'first_whistle'"
    ).fetchone()["c"]
    assert earned == 1
    conn.close()


def test_hydration_hero_requires_all_hydration_lessons_complete():
    conn = _fueliq_db()
    l1 = _insert_lesson(conn, category="hydration", title="Water Is a Skill", order_in_level=1)
    l2 = _insert_lesson(conn, category="hydration", title="Hydration Timing", order_in_level=2)
    result1 = fq.complete_lesson(1, l1, conn)
    assert "hydration_hero" not in result1["newly_earned_badges"]
    result2 = fq.complete_lesson(1, l2, conn)
    assert "hydration_hero" in result2["newly_earned_badges"]
    conn.close()


def test_perfect_week_from_best_streak():
    conn = _fueliq_db()
    fq.get_progress(1, conn)  # ensure the progress row exists
    assert "perfect_week" not in fq.check_and_award_badges(1, conn)
    conn.execute("UPDATE fueliq_athlete_progress SET best_streak = 7 WHERE athlete_id = 1")
    conn.commit()
    assert "perfect_week" in fq.check_and_award_badges(1, conn)
    conn.close()


def test_game_day_ready_requires_all_level_2_lessons_complete():
    conn = _fueliq_db()
    l1 = _insert_lesson(conn, level=2, order_in_level=1)
    l2 = _insert_lesson(conn, level=2, order_in_level=2, title="Lesson Two")
    result1 = fq.complete_lesson(1, l1, conn)
    assert "game_day_ready" not in result1["newly_earned_badges"]
    result2 = fq.complete_lesson(1, l2, conn)
    assert "game_day_ready" in result2["newly_earned_badges"]
    conn.close()


def test_level_up_badge_awarded_at_the_real_level_2_threshold_not_a_stale_100():
    """Regression: _has_level_up used to hardcode score >= 100 while the real
    Level 2 threshold (_LEVEL_THRESHOLDS[2]) is 65 — an athlete who leveled up
    at score 65-99 never got the badge. Baseline score is 50; a 10-point
    lesson with a perfect-quiz bonus (+5) reaches exactly 65."""
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn, points=10)
    assert fq.get_progress(1, conn)["score"] == 50
    result = fq.complete_lesson(1, lesson_id, conn, perfect_quiz=True)
    assert fq.get_progress(1, conn)["score"] == 65
    assert "level_up" in result["newly_earned_badges"]
    conn.close()


def test_full_tank_requires_perfect_quiz_on_every_lesson_in_a_level():
    conn = _fueliq_db()
    l1 = _insert_lesson(conn, level=1, order_in_level=1)
    l2 = _insert_lesson(conn, level=1, order_in_level=2, title="Lesson Two")
    fq.complete_lesson(1, l1, conn, perfect_quiz=True)
    fq.complete_lesson(1, l2, conn, perfect_quiz=False)
    assert "full_tank" not in fq.check_and_award_badges(1, conn)
    conn.execute(
        "UPDATE fueliq_lesson_completions SET perfect_quiz = 1 WHERE athlete_id = 1 AND lesson_id = ?",
        (l2,),
    )
    conn.commit()
    assert "full_tank" in fq.check_and_award_badges(1, conn)
    conn.close()


def test_team_player_is_never_awarded_pending_team_challenges():
    """Team Challenges are explicitly Post-MVP (spec §12) — this badge is
    defined but structurally unearnable until that feature ships."""
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    fq.complete_lesson(1, lesson_id, conn)
    assert "team_player" not in fq.check_and_award_badges(1, conn)
    conn.close()


def test_complete_lesson_surfaces_newly_earned_badges():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    result = fq.complete_lesson(1, lesson_id, conn)
    assert result["newly_earned_badges"] == ["first_whistle"]
    conn.close()


def test_list_badges_returns_every_defined_badge():
    conn = _fueliq_db()
    badges = fq.list_badges(1, conn)
    assert len(badges) == 8
    assert all(b["earned"] is False for b in badges)
    assert all(b["earned_at"] is None for b in badges)
    keys = {b["key"] for b in badges}
    assert "first_whistle" in keys
    assert "team_player" in keys
    conn.close()


def test_list_badges_marks_earned_badges():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    fq.complete_lesson(1, lesson_id, conn)  # earns first_whistle
    badges = {b["key"]: b for b in fq.list_badges(1, conn)}
    assert badges["first_whistle"]["earned"] is True
    assert badges["first_whistle"]["earned_at"] is not None
    conn.close()


# ── Streak integration ───────────────────────────────────────────────────────

def test_complete_lesson_registers_streak_activity():
    conn = _fueliq_db()
    lesson_id = _insert_lesson(conn)
    result = fq.complete_lesson(1, lesson_id, conn)
    assert result["streak"]["current"] == 1
    assert fq.get_progress(1, conn)["current_streak"] == 1
    conn.close()


# ── Percentile ───────────────────────────────────────────────────────────────

def test_percentile_insufficient_data_below_min_cohort():
    conn = _fueliq_db()  # only 2 athletes, both age 14 — below default min_cohort
    result = fq.compute_percentile(1, conn)
    assert result["insufficient_data"] is True
    assert result["percentile"] is None
    assert result["cohort_size"] == 2
    conn.close()


def test_percentile_computed_once_cohort_is_large_enough():
    conn = _fueliq_db()
    fq.get_progress(1, conn)  # athlete 1: baseline score 50
    conn.execute("UPDATE fueliq_athlete_progress SET score = 90 WHERE athlete_id = 1")
    conn.commit()
    # _fueliq_db() already seeds athlete 2 ("Sam") at age 14 with no progress row
    # (baseline 50) — plus 4 more added here -> cohort of 6, athlete 1 beats all 5 others.
    _add_athlete(conn, 10, age=14, score=50)
    _add_athlete(conn, 11, age=14, score=60)
    _add_athlete(conn, 12, age=14, score=70)
    _add_athlete(conn, 13, age=14, score=80)

    result = fq.compute_percentile(1, conn, min_cohort=5)
    assert result["insufficient_data"] is False
    assert result["cohort_size"] == 6
    assert result["percentile"] == 100  # beats all 5 others


def test_percentile_excludes_other_age_cohorts():
    conn = _fueliq_db()
    fq.get_progress(1, conn)
    _add_athlete(conn, 10, age=14, score=90)
    _add_athlete(conn, 11, age=14, score=90)
    _add_athlete(conn, 12, age=14, score=90)
    _add_athlete(conn, 20, age=17, score=1000)  # different age, must not count
    result = fq.compute_percentile(1, conn, min_cohort=5)
    # athletes 1, 2 ("Sam", seeded by _fueliq_db()), 10, 11, 12 — all age 14.
    assert result["cohort_size"] == 5
    conn.close()


def test_percentile_treats_unengaged_athletes_as_baseline_score():
    """An athlete with no fueliq_athlete_progress row hasn't touched Fuel IQ
    yet — they count in the cohort at the Rookie baseline (50), not as absent,
    so an early athlete's percentile isn't inflated by only counting engaged peers."""
    conn = _fueliq_db()
    fq.get_progress(1, conn)
    conn.execute("UPDATE fueliq_athlete_progress SET score = 60 WHERE athlete_id = 1")
    conn.commit()
    _add_athlete(conn, 10, age=14)  # no progress row at all -> baseline 50
    _add_athlete(conn, 11, age=14)
    _add_athlete(conn, 12, age=14)
    _add_athlete(conn, 13, age=14)
    result = fq.compute_percentile(1, conn, min_cohort=5)
    assert result["percentile"] == 100  # 60 beats the four baseline-50 peers
    conn.close()
