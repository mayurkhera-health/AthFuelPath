from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.database import get_conn

router = APIRouter()


class CoachFeedbackRequest(BaseModel):
    rating: str  # "up" | "down"
    question: str | None = None
    answer_excerpt: str | None = None
    window_key: str | None = None
    recipe_intent: int | None = None
    role_hint: str | None = None
    reason: str | None = None  # nullable now; preset reason chips are a later frontend add


@router.post("/feedback", status_code=201)
def post_feedback(body: CoachFeedbackRequest):
    """Log a thumbs up/down on a coach answer. High-volume telemetry — no email."""
    if body.rating not in ("up", "down"):
        raise HTTPException(400, "rating must be 'up' or 'down'.")
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO coach_feedback
                   (rating, question, answer_excerpt, window_key, recipe_intent, role_hint, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.rating, body.question, body.answer_excerpt, body.window_key,
             body.recipe_intent, body.role_hint, body.reason),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()
