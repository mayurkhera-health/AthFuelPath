"""
Fuel IQ — gamified nutrition-education tab.

GET  /api/{athlete_id}/fueliq/hub
GET  /api/{athlete_id}/fueliq/lessons?level=N
GET  /api/{athlete_id}/fueliq/lessons/{lesson_id}
POST /api/{athlete_id}/fueliq/lessons/{lesson_id}/complete
POST /api/{athlete_id}/fueliq/questions/{question_id}/answer
GET  /api/{athlete_id}/fueliq/badges

Feature-flagged (FUELIQ_ENABLED) — ships dark, mirroring plate.py/fueling_targets.py.
When off, every endpoint returns a minimal `{"enabled": False}`-shaped payload
instead of doing DB work, same convention as the Performance Plate route.

(Myth Buster — a separate list of always-available myth lessons a lesson
picker could route to — was removed here; replaced by the Daily Challenge
feature, a single global challenge per day. See
api/routes/fueliq_daily_challenge.py.)
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_conn
from api.models import FuelIQLessonComplete, FuelIQQuizAnswer
from api.services import fueliq_service as fq
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()

_LEVELS = (1, 2, 3, 4, 5)

_LEVEL_NAMES = {
    1: "Kickoff",
    2: "Energy Builder",
    3: "Match Ready",
    4: "Performance Leader",
    5: "Fuel IQ Champion",
}


@router.get("/{athlete_id}/hub")
def get_hub(athlete_id: int, identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        progress = fq.get_progress(athlete_id, conn)
        badges = [
            r["badge_key"]
            for r in conn.execute(
                "SELECT badge_key FROM fueliq_badges_earned WHERE athlete_id = %s",
                (athlete_id,),
            ).fetchall()
        ]
        levels = [
            {
                "level": lvl,
                "unlocked": fq.level_unlocked(progress["score"], lvl),
                "level_name": _LEVEL_NAMES[lvl],
            }
            for lvl in _LEVELS
        ]
        percentile = fq.compute_percentile(athlete_id, conn)
        strongest_at = fq.compute_strongest_at(athlete_id, conn)

        # next_game — next future game or tournament for Fuel Week anchoring.
        # Uses >= today so a same-day game (days_away=0, Fuel Week day 7) is included.
        # start_time is nullable; Phase 5 notification triggers must null-check it.
        today_dt = date.today()
        today_str = today_dt.isoformat()
        next_game_row = conn.execute(
            "SELECT event_date, event_type, event_name, start_time "
            "FROM events WHERE athlete_id = %s AND event_date >= %s "
            "AND event_type IN ('game', 'tournament') ORDER BY event_date, start_time LIMIT 1",
            (athlete_id, today_str),
        ).fetchone()
        next_game = (
            {
                "event_date": next_game_row["event_date"],
                "event_type": next_game_row["event_type"],
                "event_name": next_game_row["event_name"],
                "start_time": next_game_row["start_time"],
                "days_away": (date.fromisoformat(next_game_row["event_date"]) - today_dt).days,
            }
            if next_game_row
            else None
        )

        # fuel_week — 7-day arc anchored to next_game.event_date (§5.1, Phase 4).
        # arc = game_date − 6 through game_date (Day 1 → Day 7 = game day).
        # current_day = 7 − days_away  when days_away ∈ [0, 6]  (active).
        # is_teaser = True             when days_away === 7       (arc starts tomorrow).
        # null                         when days_away > 7 or no game.
        # "fueled" per day = at least streak_min_confirms_per_day confirmations that date.
        fuel_week = None
        if next_game and next_game["days_away"] <= 7:
            game_dt = date.fromisoformat(next_game["event_date"])
            is_teaser = next_game["days_away"] == 7
            current_day = None if is_teaser else 7 - next_game["days_away"]

            # arc_dates[0] = Day 1 = game_dt − 6d … arc_dates[6] = Day 7 = game_dt
            arc_dates = [(game_dt - timedelta(days=6 - i)).isoformat() for i in range(7)]

            # "Fueled" = completed at least one lesson that calendar day (Daily Challenge
            # = lesson-based per Addendum A §2). Source is fueliq_lesson_completions,
            # NOT the meal-confirmation table — Fuel Week tracks learning engagement,
            # not eating behavior.
            # Note: completed_at is stored UTC (datetime('now')); DATE() returns a UTC
            # date. arc_dates are server-local dates (also UTC on Fly), so the grouping
            # is consistent. Timezone edge cases (athlete completes lesson at 11 PM local
            # while server rolls to next UTC day) are an accepted limitation for v1.
            lesson_rows = conn.execute(
                "SELECT to_char(completed_at::timestamp, 'YYYY-MM-DD') AS lesson_date "
                "FROM fueliq_lesson_completions "
                "WHERE athlete_id = %s AND to_char(completed_at::timestamp, 'YYYY-MM-DD') IN ({}) "
                "GROUP BY lesson_date".format(",".join(["%s"] * 7)),
                (athlete_id, *arc_dates),
            ).fetchall()
            lesson_dates = {r["lesson_date"] for r in lesson_rows}

            days = []
            for idx, arc_date_str in enumerate(arc_dates):
                arc_dt = game_dt - timedelta(days=6 - idx)
                is_future_day = arc_dt > today_dt
                days.append({
                    "date": arc_date_str,
                    "day_number": idx + 1,
                    "is_today": arc_dt == today_dt,
                    "is_future": is_future_day,
                    "is_game_day": idx == 6,
                    "fueled": None if is_future_day else (arc_date_str in lesson_dates),
                })

            fuel_week = {
                "game_date": next_game["event_date"],
                "event_name": next_game["event_name"],
                "event_type": next_game["event_type"],
                "days_away": next_game["days_away"],
                "is_teaser": is_teaser,
                "current_day": current_day,
                "days": days,
            }
    finally:
        conn.close()

    return {
        "enabled": True,
        **progress,
        "levels": levels,
        "badges_earned": badges,
        "percentile": percentile,
        "strongest_at": strongest_at,
        "next_game": next_game,
        "fuel_week": fuel_week,
    }


@router.get("/{athlete_id}/lessons")
def list_lessons(athlete_id: int, level: int = Query(...), identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        progress = fq.get_progress(athlete_id, conn)
        unlocked = fq.level_unlocked(progress["score"], level)
        rows = conn.execute(
            "SELECT id, title, hook, points, order_in_level FROM fueliq_lessons "
            "WHERE level = %s AND is_myth = 0 AND review_status = 'approved' "
            "ORDER BY order_in_level",
            (level,),
        ).fetchall()
        completed_ids = {
            r["lesson_id"]
            for r in conn.execute(
                "SELECT lesson_id FROM fueliq_lesson_completions WHERE athlete_id = %s",
                (athlete_id,),
            ).fetchall()
        }
    finally:
        conn.close()

    lessons = [
        {**dict(r), "completed": r["id"] in completed_ids} for r in rows
    ]
    return {"enabled": True, "level": level, "unlocked": unlocked, "lessons": lessons}


@router.get("/{athlete_id}/lessons/{lesson_id}")
def get_lesson(athlete_id: int, lesson_id: int, identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        lesson = conn.execute(
            "SELECT id, level, title, hook, fact_body, visual_ref, takeaway, points "
            "FROM fueliq_lessons WHERE id = %s AND is_myth = 0 AND review_status = 'approved'",
            (lesson_id,),
        ).fetchone()
        if not lesson:
            raise HTTPException(404, f"Lesson {lesson_id} not found")

        progress = fq.get_progress(athlete_id, conn)
        if not fq.level_unlocked(progress["score"], lesson["level"]):
            raise HTTPException(403, f"Level {lesson['level']} is not unlocked yet")

        questions = conn.execute(
            "SELECT id, question_text, option_a, option_b, option_c FROM fueliq_questions "
            "WHERE lesson_id = %s ORDER BY order_in_lesson",
            (lesson_id,),
        ).fetchall()
    finally:
        conn.close()

    return {"enabled": True, **dict(lesson), "questions": [dict(q) for q in questions]}


@router.post("/{athlete_id}/lessons/{lesson_id}/complete")
def complete_lesson(athlete_id: int, lesson_id: int, body: FuelIQLessonComplete, identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        exists = conn.execute(
            "SELECT 1 FROM fueliq_lessons WHERE id = %s AND is_myth = 0", (lesson_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(404, f"Lesson {lesson_id} not found")
        result = fq.complete_lesson(athlete_id, lesson_id, conn, perfect_quiz=body.perfect_quiz)
    finally:
        conn.close()

    return {"enabled": True, **result}


@router.post("/{athlete_id}/questions/{question_id}/answer")
def answer_question(athlete_id: int, question_id: int, body: FuelIQQuizAnswer, identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        exists = conn.execute(
            "SELECT 1 FROM fueliq_questions WHERE id = %s", (question_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(404, f"Question {question_id} not found")
        result = fq.submit_quiz_answer(athlete_id, question_id, body.selected_option, conn)
    finally:
        conn.close()

    return {"enabled": True, **result}


@router.get("/{athlete_id}/badges")
def get_badges(athlete_id: int, identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        badges = fq.list_badges(athlete_id, conn)
    finally:
        conn.close()

    return {"enabled": True, "badges": badges}
