"""
Instacart grocery-handoff MVP feedback (Return & Feedback step).

POST /api/instacart/feedback — persist the two quick-tap answers ("How did it
go?" / "Would you use this again?"). High-volume, no email — same pattern as
api/routes/coach.py's thumbs up/down telemetry (POST /api/coach/feedback).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_OUTCOMES = {"worked_great", "some_issues", "didnt_work"}
_VALID_WOULD_USE_AGAIN = {"yes", "maybe", "no"}


class InstacartFeedback(BaseModel):
    athlete_id: int | None = None
    outcome: str
    would_use_again: str
    comment: str | None = None


@router.post("/feedback", status_code=201)
def submit_instacart_feedback(payload: InstacartFeedback, identity=Depends(require_session)):
    if payload.outcome not in _VALID_OUTCOMES:
        raise HTTPException(400, f"outcome must be one of {sorted(_VALID_OUTCOMES)}")
    if payload.would_use_again not in _VALID_WOULD_USE_AGAIN:
        raise HTTPException(400, f"would_use_again must be one of {sorted(_VALID_WOULD_USE_AGAIN)}")

    conn = get_conn()
    try:
        if payload.athlete_id is not None:
            assert_owns_athlete(identity, payload.athlete_id, conn)
        cur = conn.execute(
            """INSERT INTO instacart_handoff_feedback
                   (athlete_id, outcome, would_use_again, comment)
               VALUES (?, ?, ?, ?)""",
            (payload.athlete_id, payload.outcome, payload.would_use_again, payload.comment),
        )
        conn.commit()
        feedback_id = cur.lastrowid
    finally:
        conn.close()

    return {"ok": True, "id": feedback_id}
