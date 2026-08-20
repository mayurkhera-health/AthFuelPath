"""
Fuel IQ Daily Challenge — a single global myth-style challenge published per
calendar day, replacing the old per-athlete Myth Buster pool it grew out of.
Not personalized and not rotated per athlete: every athlete sees the same
`fueliq_daily_challenges` row on a given day (spec decision — no sibling
comparison concerns since there's nothing athlete-specific to compare).

PST is the server's reference clock for "what day is it" — matches the fixed
push-notification time, deliberately not each athlete's own local timezone.

Deliberately independent of the rest of Fuel IQ (spec decision, not an
oversight): completing the Daily Challenge never touches
fueliq_athlete_progress.score — it can't move an athlete's Rank or unlock a
Level. It has its own points (informational — shown on the reward moment
only) and its own streak (fueliq_daily_challenge_streak, NOT
fueliq_streak.py's lesson-activity streak). The streak also has no freeze-
token forgiveness — a missed day always resets it, on purpose: the whole
point of "Daily" is the same-day urgency.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from api.services import fueliq_service as fq
from api.services import notification_service

_PUSH_TITLE = "⚡ Daily Challenge"
_PUSH_BODY = "Your daily Fuel IQ challenge is ready."

_PST = ZoneInfo("America/Los_Angeles")
_VALID_VERDICTS = {"real", "myth"}
_REQUIRED_FIELDS = ("title", "hook", "verdict", "science_text")


def _today_pst() -> date:
    return datetime.now(_PST).date()


def _validate_item(item: dict) -> None:
    missing = [f for f in _REQUIRED_FIELDS if not item.get(f)]
    if missing:
        raise ValueError(f"Daily Challenge item missing required field(s) {missing}: {item}")
    if item["verdict"] not in _VALID_VERDICTS:
        raise ValueError(
            f"Daily Challenge item has invalid verdict {item['verdict']!r} "
            f"(must be 'real' or 'myth'): {item}"
        )


def _next_available_date(conn, today: date | None = None) -> date:
    """The date the next imported challenge should land on — the day after
    whatever's already scheduled furthest out, or today (PST) if nothing is
    scheduled yet, so a first-ever import is live immediately rather than
    waiting until tomorrow."""
    row = conn.execute("SELECT MAX(challenge_date) AS d FROM fueliq_daily_challenges").fetchone()
    if not row or not row["d"]:
        return today or _today_pst()
    return date.fromisoformat(row["d"]) + timedelta(days=1)


def import_daily_challenges(conn, items: list[dict], today: date | None = None) -> list[dict]:
    """Insert a batch of challenge questions, auto-assigning sequential
    calendar dates starting from the next available day. Idempotent by
    title — re-running the same content file never creates duplicates, so a
    content author's running list can safely include already-imported
    questions alongside new ones."""
    for item in items:
        _validate_item(item)

    points = int(fq._config_value(conn, "fueliq_daily_challenge_points", 10))
    next_date = _next_available_date(conn, today)
    inserted = []
    for item in items:
        exists = conn.execute(
            "SELECT 1 FROM fueliq_daily_challenges WHERE title = %s", (item["title"],)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO fueliq_daily_challenges "
            "(challenge_date, title, hook, verdict, science_text, source_citation, points) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                next_date.isoformat(),
                item["title"],
                item["hook"],
                item["verdict"],
                item["science_text"],
                item.get("source_citation"),
                points,
            ),
        )
        inserted.append({"title": item["title"], "challenge_date": next_date.isoformat()})
        next_date += timedelta(days=1)
    conn.commit()
    return inserted


def _qualifying_dates(athlete_id: int, conn) -> set:
    rows = conn.execute(
        "SELECT DISTINCT challenge_date AS d FROM fueliq_daily_challenge_answers WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchall()
    return {r["d"] for r in rows}


def _current_streak(qual: set, today: date) -> int:
    """Consecutive qualifying days ending today (or yesterday if today
    hasn't been answered yet — not answering YET today doesn't break the
    streak; only a genuinely missed day does). No freeze-token bridging —
    unlike fueliq_streak.py, a gap always resets to 0."""
    anchor = today if today.isoformat() in qual else today - timedelta(days=1)
    streak = 0
    d = anchor
    while d.isoformat() in qual:
        streak += 1
        d -= timedelta(days=1)
    return streak


def _best_streak(qual: set) -> int:
    if not qual:
        return 0
    dates = sorted(date.fromisoformat(d) for d in qual)
    best = cur = 1
    for i in range(1, len(dates)):
        cur = cur + 1 if (dates[i] - dates[i - 1]).days == 1 else 1
        best = max(best, cur)
    return best


def _register_streak(athlete_id: int, conn, today: date) -> dict:
    qual = _qualifying_dates(athlete_id, conn)
    current = _current_streak(qual, today)
    best = max(_best_streak(qual), current)
    conn.execute(
        "INSERT INTO fueliq_daily_challenge_streak "
        "(athlete_id, current_streak, best_streak, last_completed_date, updated_at) "
        "VALUES (%s, %s, %s, %s, sqlite_now()) "
        "ON CONFLICT(athlete_id) DO UPDATE SET "
        "current_streak = excluded.current_streak, best_streak = excluded.best_streak, "
        "last_completed_date = excluded.last_completed_date, updated_at = sqlite_now()",
        (athlete_id, current, best, today.isoformat()),
    )
    conn.commit()
    return {"current": current, "best": best}


def _streak_for(athlete_id: int, conn) -> dict:
    row = conn.execute(
        "SELECT current_streak, best_streak FROM fueliq_daily_challenge_streak WHERE athlete_id = %s",
        (athlete_id,),
    ).fetchone()
    return {"current": row["current_streak"], "best": row["best_streak"]} if row else {"current": 0, "best": 0}


def get_todays_challenge(athlete_id: int, conn, today: date | None = None) -> dict:
    """Read path for the Hub's Daily Challenge card. Never returns the
    correct verdict or the science-text explanation before the athlete has
    actually answered — same never-leak-the-answer-early design as the
    lesson quiz endpoint. total_completed is a free lifetime counter (not a
    streak) shown alongside it, since "you've done N of these ever" is a
    different, complementary stat from "N in a row right now"."""
    today_d = today or _today_pst()
    today_str = today_d.isoformat()

    streak = _streak_for(athlete_id, conn)
    total_completed = conn.execute(
        "SELECT COUNT(*) AS c FROM fueliq_daily_challenge_answers WHERE athlete_id = %s", (athlete_id,)
    ).fetchone()["c"]

    row = conn.execute(
        "SELECT challenge_date, title, hook FROM fueliq_daily_challenges WHERE challenge_date = %s",
        (today_str,),
    ).fetchone()
    if not row:
        return {"challenge": None, "streak": streak, "total_completed": total_completed}

    answer = conn.execute(
        "SELECT guess, correct FROM fueliq_daily_challenge_answers WHERE athlete_id = %s AND challenge_date = %s",
        (athlete_id, today_str),
    ).fetchone()
    challenge = {
        "challenge_date": row["challenge_date"],
        "title": row["title"],
        "hook": row["hook"],
        "answered": bool(answer),
    }
    if answer:
        challenge["guess"] = answer["guess"]
        challenge["correct"] = bool(answer["correct"])
    return {"challenge": challenge, "streak": streak, "total_completed": total_completed}


def submit_daily_challenge_verdict(athlete_id: int, guess: str, conn, today: date | None = None) -> dict:
    """Write path for a Daily Challenge REAL/MYTH tap. Points are awarded for
    completing it, correct or not (same failure-must-be-cheap principle as
    the old Myth Buster), and only once per athlete per day. Deliberately
    never calls fueliq_service._award_points — the points returned here are
    informational for the reward moment only, not fed into the shared
    Rank/Level score."""
    today_d = today or _today_pst()
    today_str = today_d.isoformat()

    existing = conn.execute(
        "SELECT correct FROM fueliq_daily_challenge_answers WHERE athlete_id = %s AND challenge_date = %s",
        (athlete_id, today_str),
    ).fetchone()
    if existing:
        return {"already_answered": True, "correct": bool(existing["correct"]), "points_earned": 0}

    challenge = conn.execute(
        "SELECT verdict, science_text, points FROM fueliq_daily_challenges WHERE challenge_date = %s",
        (today_str,),
    ).fetchone()
    if not challenge:
        raise ValueError(f"No Daily Challenge scheduled for {today_str}")

    correct = guess == challenge["verdict"]
    conn.execute(
        "INSERT INTO fueliq_daily_challenge_answers (athlete_id, challenge_date, guess, correct) "
        "VALUES (%s, %s, %s, %s)",
        (athlete_id, today_str, guess, int(correct)),
    )
    conn.commit()
    streak = _register_streak(athlete_id, conn, today_d)
    return {
        "already_answered": False,
        "correct": correct,
        "science_text": challenge["science_text"],
        "points_earned": int(challenge["points"]),
        "streak": streak,
    }


def run_daily_challenge_push(conn=None, today: date | None = None) -> dict:
    """APScheduler daily job (registered in api/main.py at 5pm PST) — fires
    the "new Daily Challenge is live" push to every registered athlete
    token, once per day. Broadcast, not personalized (matches the challenge
    itself being global). Athlete tokens only — this is a nudge aimed at the
    athlete, not the parent. Guarded by fueliq_daily_challenges.push_sent_at
    so a scheduler misfire/restart can never double-send; a quiet no-op (not
    an error) if there's no challenge scheduled today or no tokens yet."""
    owns_conn = conn is None
    if owns_conn:
        from api.database import get_conn
        conn = get_conn()
    try:
        today_str = (today or _today_pst()).isoformat()
        challenge = conn.execute(
            "SELECT id, push_sent_at FROM fueliq_daily_challenges WHERE challenge_date = %s",
            (today_str,),
        ).fetchone()
        if not challenge:
            return {"sent": False, "reason": "no_challenge_today"}
        if challenge["push_sent_at"]:
            return {"sent": False, "reason": "already_sent"}

        tokens = [
            r["token"]
            for r in conn.execute(
                "SELECT token FROM expo_push_tokens WHERE athlete_id IS NOT NULL"
            ).fetchall()
        ]
        if not tokens:
            return {"sent": False, "reason": "no_tokens"}

        ok = notification_service.send_expo_push(
            tokens, _PUSH_TITLE, _PUSH_BODY, data={"type": "daily_challenge"}
        )
        conn.execute(
            "UPDATE fueliq_daily_challenges SET push_sent_at = sqlite_now() WHERE id = %s",
            (challenge["id"],),
        )
        conn.commit()
        return {"sent": ok, "recipient_count": len(tokens)}
    finally:
        if owns_conn:
            conn.close()
