"""
Fuel IQ — gamified nutrition-education engine.

Score is earned-never-lost (no decay, no penalties — spec §5.1). Level-unlock
is a pure function of score, derived on every read, the same way
streak_service never caches a derived value. `fueliq_athlete_progress` stores
only the non-derivable state (raw score, streak counters, freeze tokens).
"""

import os

_LEVEL_THRESHOLDS = {1: 0, 2: 65, 3: 120, 4: 145, 5: 165}


def fueliq_enabled() -> bool:
    return os.environ.get("FUELIQ_ENABLED", "false").lower() == "true"


def level_unlocked(score: int, level: int) -> bool:
    return score >= _LEVEL_THRESHOLDS[level]


def _config_value(conn, key: str, default: float) -> float:
    row = conn.execute("SELECT value FROM report_config WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else default


def _ensure_progress_row(athlete_id: int, conn) -> None:
    conn.execute(
        "INSERT INTO fueliq_athlete_progress (athlete_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (athlete_id,),
    )
    conn.commit()


def get_progress(athlete_id: int, conn) -> dict:
    """Read-path progress block for the Fuel IQ hub. Creates a default row
    on an athlete's first-ever read."""
    _ensure_progress_row(athlete_id, conn)
    row = conn.execute(
        "SELECT score, current_streak, best_streak, freeze_tokens, last_activity_date "
        "FROM fueliq_athlete_progress WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return {
        "score": row["score"],
        "current_streak": row["current_streak"],
        "best_streak": row["best_streak"],
        "freeze_tokens": row["freeze_tokens"],
        "last_activity_date": row["last_activity_date"],
    }


def import_lessons(
    conn, items: list[dict], review_status: str = "draft", reviewed_by: str | None = None
) -> list[dict]:
    """Insert a batch of lessons (each carrying its own questions), e.g. from
    a content file like content/fueliq_lessons_proposed.json. Idempotent by
    title — re-running the same content file never creates duplicates, so a
    content author's running list can safely include already-imported
    lessons alongside new ones.

    review_status defaults to 'draft': flipping content to 'approved' (spec
    §11.1, RDN sign-off) must be a deliberate, explicit argument, not an
    accident of importing."""
    points_default = int(_config_value(conn, "fueliq_lesson_points", 10))
    inserted = []
    for item in items:
        exists = conn.execute(
            "SELECT 1 FROM fueliq_lessons WHERE title = %s", (item["title"],)
        ).fetchone()
        if exists:
            continue
        lesson_id = conn.execute(
            "INSERT INTO fueliq_lessons "
            "(level, order_in_level, is_myth, title, hook, fact_body, takeaway, "
            " category, source_citation, points, review_status, reviewed_by, review_date) "
            "VALUES (%s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                item["level"],
                item["order_in_level"],
                item["title"],
                item["hook"],
                item.get("fact_body"),
                item.get("takeaway"),
                item.get("category"),
                item["source_citation"],
                item.get("points", points_default),
                review_status,
                reviewed_by,
                None if reviewed_by is None else _now(conn),
            ),
        ).fetchone()["id"]
        for q_order, q in enumerate(item["questions"], start=1):
            conn.execute(
                "INSERT INTO fueliq_questions "
                "(lesson_id, question_text, option_a, option_b, option_c, correct_option, "
                " explanation, misconception_tag, order_in_lesson) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    lesson_id,
                    q["question_text"],
                    q["option_a"],
                    q["option_b"],
                    q["option_c"],
                    q["correct_option"],
                    q["explanation"],
                    q.get("misconception_tag"),
                    q.get("order_in_lesson", q_order),
                ),
            )
        inserted.append({"title": item["title"], "level": item["level"]})

    conn.commit()
    return inserted


def _now(conn) -> str:
    return conn.execute("SELECT sqlite_now() AS n").fetchone()["n"]


def _award_points(athlete_id: int, points: int, conn) -> None:
    """Score is earned-never-lost — always additive, never set/decremented."""
    _ensure_progress_row(athlete_id, conn)
    conn.execute(
        "UPDATE fueliq_athlete_progress SET score = score + %s, updated_at = sqlite_now() "
        "WHERE athlete_id = %s",
        (points, athlete_id),
    )
    conn.commit()


def complete_lesson(athlete_id: int, lesson_id: int, conn, perfect_quiz: bool = False) -> dict:
    """Write path for finishing a lesson's reward screen. Idempotent per
    (athlete_id, lesson_id) — replaying a completion (e.g. a retried request)
    never double-awards points."""
    existing = conn.execute(
        "SELECT 1 FROM fueliq_lesson_completions WHERE athlete_id = %s AND lesson_id = %s",
        (athlete_id, lesson_id),
    ).fetchone()
    if existing:
        return {
            "already_completed": True,
            "points_earned": 0,
            "progress": get_progress(athlete_id, conn),
            "newly_earned_badges": [],
        }

    lesson_points = int(
        conn.execute("SELECT points FROM fueliq_lessons WHERE id = %s", (lesson_id,)).fetchone()["points"]
    )
    points_earned = lesson_points
    if perfect_quiz:
        points_earned += int(_config_value(conn, "fueliq_perfect_quiz_bonus", 5))

    conn.execute(
        "INSERT INTO fueliq_lesson_completions (athlete_id, lesson_id, perfect_quiz, points_earned) "
        "VALUES (%s, %s, %s, %s)",
        (athlete_id, lesson_id, int(perfect_quiz), points_earned),
    )
    conn.commit()
    _award_points(athlete_id, points_earned, conn)
    from api.services import fueliq_streak  # local import — avoids a circular import
    streak = fueliq_streak.register_activity(athlete_id, conn)
    return {
        "already_completed": False,
        "points_earned": points_earned,
        "progress": get_progress(athlete_id, conn),
        "newly_earned_badges": check_and_award_badges(athlete_id, conn),
        "streak": streak,
    }


def submit_quiz_answer(athlete_id: int, question_id: int, selected_option: str, conn) -> dict:
    """Write path for a single quiz question. No score effect — quiz answers
    only unlock the lesson-complete points via `perfect_quiz`; wrong answers
    are logged for the misconception-tag analytics (spec §6.3), never penalized."""
    question = conn.execute(
        "SELECT correct_option, explanation, misconception_tag FROM fueliq_questions WHERE id = %s",
        (question_id,),
    ).fetchone()
    correct = selected_option == question["correct_option"]
    conn.execute(
        "INSERT INTO fueliq_quiz_attempts "
        "(athlete_id, question_id, selected_option, correct, misconception_tag) "
        "VALUES (%s, %s, %s, %s, %s)",
        (athlete_id, question_id, selected_option, int(correct), question["misconception_tag"]),
    )
    conn.commit()
    return {
        "correct": correct,
        "explanation": question["explanation"],
        "misconception_tag": question["misconception_tag"],
    }


# ── Badges (spec §7.1) ───────────────────────────────────────────────────────
# Collect-don't-grind: small, permanent set. Earned-never-lost, same as score.

def _has_first_whistle(athlete_id: int, conn) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_lesson_completions WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return row["c"] >= 1


def _has_hydration_hero(athlete_id: int, conn) -> bool:
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_lessons "
        "WHERE is_myth = 0 AND review_status = 'approved' AND category = 'hydration'"
    ).fetchone()["c"]
    if total == 0:
        return False
    done = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_lesson_completions lc "
        "JOIN fueliq_lessons l ON l.id = lc.lesson_id "
        "WHERE lc.athlete_id = %s AND l.category = 'hydration'",
        (athlete_id,),
    ).fetchone()["c"]
    return done >= total


def _has_perfect_week(athlete_id: int, conn) -> bool:
    row = conn.execute(
        "SELECT best_streak FROM fueliq_athlete_progress WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return bool(row) and row["best_streak"] >= 7


def _level_complete(athlete_id: int, level: int, conn) -> bool:
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_lessons WHERE is_myth = 0 AND review_status = 'approved' AND level = %s",
        (level,),
    ).fetchone()["c"]
    if total == 0:
        return False
    done = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_lesson_completions lc "
        "JOIN fueliq_lessons l ON l.id = lc.lesson_id "
        "WHERE lc.athlete_id = %s AND l.level = %s",
        (athlete_id, level),
    ).fetchone()["c"]
    return done >= total


def _has_game_day_ready(athlete_id: int, conn) -> bool:
    return _level_complete(athlete_id, 2, conn)


def _has_full_tank(athlete_id: int, conn) -> bool:
    for level in _LEVEL_THRESHOLDS:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM fueliq_lessons WHERE is_myth = 0 AND review_status = 'approved' AND level = %s",
            (level,),
        ).fetchone()["c"]
        if total == 0:
            continue
        perfect = conn.execute(
            "SELECT COUNT(*) AS c FROM fueliq_lesson_completions lc "
            "JOIN fueliq_lessons l ON l.id = lc.lesson_id "
            "WHERE lc.athlete_id = %s AND l.level = %s AND lc.perfect_quiz = 1",
            (athlete_id, level),
        ).fetchone()["c"]
        if perfect >= total:
            return True
    return False


def _has_three_in_a_row(athlete_id: int, conn) -> bool:
    """3-day lesson streak — simplest form: best_streak ever reached ≥ 3."""
    row = conn.execute(
        "SELECT best_streak FROM fueliq_athlete_progress WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return bool(row) and row["best_streak"] >= 3


def _has_team_player(athlete_id: int, conn) -> bool:
    """Team Challenges are Post-MVP (spec §12) — no data source exists yet, so
    this badge is defined but permanently unearnable until that feature ships."""
    return False


def _has_level_up(athlete_id: int, conn) -> bool:
    """Earned the first time an athlete reaches Level 2."""
    row = conn.execute(
        "SELECT score FROM fueliq_athlete_progress WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return bool(row) and level_unlocked(row["score"], 2)


BADGE_CHECKS = {
    "first_whistle": _has_first_whistle,
    "three_in_a_row": _has_three_in_a_row,
    "hydration_hero": _has_hydration_hero,
    "perfect_week": _has_perfect_week,
    "game_day_ready": _has_game_day_ready,
    "full_tank": _has_full_tank,
    "team_player": _has_team_player,
    "level_up": _has_level_up,
}

# Display metadata for the Badge Gallery — order matches spec §7.1.
# "myth_slayer" (Clean Sheet, "Bust 5 myths") was deleted along with the old
# Myth Buster feature it read from — dev-only, no earned rows existed yet.
BADGE_DEFINITIONS = [
    {"key": "first_whistle", "name": "Kickoff", "hint": "Complete your first lesson"},
    {"key": "three_in_a_row", "name": "Three in a Row", "hint": "Build a 3-day lesson streak"},
    {"key": "hydration_hero", "name": "Hydration Hero", "hint": "Complete all water lessons"},
    {"key": "perfect_week", "name": "Seven-Day Starter", "hint": "Hit a 7-day streak"},
    {"key": "game_day_ready", "name": "Match Ready", "hint": "Complete Level 2"},
    {"key": "team_player", "name": "Team Player", "hint": "Complete your first Team Challenge"},
    {"key": "full_tank", "name": "Golden Boot", "hint": "100% of a level with perfect quizzes"},
    {"key": "level_up", "name": "Level Up", "hint": "Reach your first new level"},
]


def list_badges(athlete_id: int, conn) -> list[dict]:
    """Badge Gallery read path — every defined badge, earned or locked."""
    earned_at = {
        r["badge_key"]: r["earned_at"]
        for r in conn.execute(
            "SELECT badge_key, earned_at FROM fueliq_badges_earned WHERE athlete_id = %s",
            (athlete_id,),
        ).fetchall()
    }
    return [
        {**b, "earned": b["key"] in earned_at, "earned_at": earned_at.get(b["key"])}
        for b in BADGE_DEFINITIONS
    ]


def check_and_award_badges(athlete_id: int, conn) -> list[str]:
    """Runs every badge check and awards any newly-qualifying badge. Idempotent
    — a badge already in fueliq_badges_earned is never re-awarded or re-returned."""
    already = {
        r["badge_key"]
        for r in conn.execute(
            "SELECT badge_key FROM fueliq_badges_earned WHERE athlete_id = %s", (athlete_id,)
        ).fetchall()
    }
    newly_earned = [
        key for key, check in BADGE_CHECKS.items() if key not in already and check(athlete_id, conn)
    ]
    for key in newly_earned:
        conn.execute(
            "INSERT INTO fueliq_badges_earned (athlete_id, badge_key) VALUES (%s, %s) "
            "ON CONFLICT (athlete_id, badge_key) DO NOTHING",
            (athlete_id, key),
        )
    if newly_earned:
        conn.commit()
    return newly_earned


DEFAULT_MIN_COHORT = 5

# Display names for lesson category codes — kept server-side so raw DB
# values never reach the client. Fallback: title-case the raw value if an
# unknown category appears after new content is imported.
_CATEGORY_DISPLAY: dict[str, str] = {
    "hydration": "Hydration",
    "nutrient_timing": "Nutrient Timing",
    "performance_plate": "Performance Plate",
    "eating_frequency": "Eating Frequency",
    "sweat_electrolytes": "Sweat & Electrolytes",
    "smart_shopping_prep": "Smart Shopping",
}

STRONGEST_AT_MIN_COMPLETIONS = 1  # interim floor until more lesson content ships per category


def compute_strongest_at(athlete_id: int, conn, min_completions: int = STRONGEST_AT_MIN_COMPLETIONS) -> dict | None:
    """Lesson-completion proxy for the 'Strongest at' mastery signal (§6,
    Addendum B). Returns the category where this athlete has the most lesson
    completions, provided they have at least `min_completions` in that
    category. Tie-break: whichever tied category had its most recent
    completion later. Returns None when no category meets the floor."""
    row = conn.execute(
        """
        SELECT l.category, COUNT(*) AS cnt, MAX(lc.completed_at) AS last_completed
        FROM fueliq_lesson_completions lc
        JOIN fueliq_lessons l ON l.id = lc.lesson_id
        WHERE lc.athlete_id = %s AND l.category IS NOT NULL
        GROUP BY l.category
        HAVING COUNT(*) >= %s
        ORDER BY cnt DESC, last_completed DESC
        LIMIT 1
        """,
        (athlete_id, min_completions),
    ).fetchone()
    if not row:
        return None
    category = row["category"]
    display_name = _CATEGORY_DISPLAY.get(category, category.replace("_", " ").title())
    return {"category": category, "display_name": display_name}


def compute_percentile(athlete_id: int, conn, min_cohort: int = DEFAULT_MIN_COHORT) -> dict:
    """Solo-athlete percentile vs. anonymized same-age cohort (spec §7.2,
    §12). With a small early user base, "beats 72% of 16-year-olds" is
    numerically absurd for a cohort of 1 or 2 — suppress the percentile
    below `min_cohort` and report insufficient_data instead of a misleading
    number. An athlete with no fueliq_athlete_progress row hasn't engaged
    yet and counts at the Rookie baseline (50), not as absent — otherwise a
    cohort of mostly-unengaged peers would inflate everyone's percentile."""
    row = conn.execute("SELECT age FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
    if not row or row["age"] is None:
        return {"percentile": None, "cohort_size": 0, "insufficient_data": True}

    age = row["age"]
    cohort_ids = [r["id"] for r in conn.execute("SELECT id FROM athletes WHERE age = %s", (age,)).fetchall()]
    scores = {}
    for aid in cohort_ids:
        prog = conn.execute(
            "SELECT score FROM fueliq_athlete_progress WHERE athlete_id = %s", (aid,)
        ).fetchone()
        scores[aid] = prog["score"] if prog else 50
    cohort_size = len(scores)

    if cohort_size < min_cohort:
        return {"percentile": None, "cohort_size": cohort_size, "insufficient_data": True}

    my_score = scores[athlete_id]
    beaten = sum(1 for s in scores.values() if s < my_score)
    percentile = round(100 * beaten / (cohort_size - 1)) if cohort_size > 1 else 100
    return {"percentile": percentile, "cohort_size": cohort_size, "insufficient_data": False}
