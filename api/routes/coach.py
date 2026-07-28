import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete
from api.services.email_service import send_email

logger = logging.getLogger(__name__)
router = APIRouter()

_DIETITIAN_RECIPIENT = "purvihshah@gmail.com"
_SESSION_LABELS = {"30min": "30 min quick check-in", "60min": "60 min full review", "package": "3-session pack"}


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


class DietitianBookingRequest(BaseModel):
    athlete_id: int
    session_type: str  # "30min" | "60min" | "package"
    about_athlete: str
    reason: str | None = None


@router.post("/dietitian-booking", status_code=201)
def post_dietitian_booking(body: DietitianBookingRequest, identity=Depends(require_session)):
    """Persist a 'Talk to a Dietitian' request and email the dietitian. Previously
    this request only ever reached on-device AsyncStorage and went nowhere."""
    if body.session_type not in _SESSION_LABELS:
        raise HTTPException(400, f"Invalid session_type: {body.session_type}")
    if len(body.about_athlete.strip()) < 5:
        raise HTTPException(400, "about_athlete must be at least 5 characters.")

    conn = get_conn()
    try:
        assert_owns_athlete(identity, body.athlete_id, conn)
        athlete = conn.execute(
            "SELECT first_name FROM athletes WHERE id = ?", (body.athlete_id,)
        ).fetchone()
        if not athlete:
            raise HTTPException(404, "Athlete not found.")

        cur = conn.execute(
            """INSERT INTO dietitian_bookings (athlete_id, session_type, about_athlete, reason)
               VALUES (?, ?, ?, ?)""",
            (body.athlete_id, body.session_type, body.about_athlete.strip(), (body.reason or "").strip() or None),
        )
        conn.commit()
        booking_id = cur.lastrowid
        created_at_utc = conn.execute(
            "SELECT created_at FROM dietitian_bookings WHERE id = ?", (booking_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    # Best-effort notification — must never block or fail the 201; the booking
    # is already durably saved above regardless of email outcome.
    PST = timezone(timedelta(hours=-8))
    created_at = (
        datetime.fromisoformat(created_at_utc).replace(tzinfo=timezone.utc).astimezone(PST).strftime("%Y-%m-%d %I:%M %p PST")
    )
    subject = f"New Dietitian Session Request — {athlete['first_name']}"
    body_text = (
        "A new 'Talk to a Dietitian' request was submitted via the FuelUp app.\n\n"
        f"Athlete:     {athlete['first_name']} (id {body.athlete_id})\n"
        f"Session:     {_SESSION_LABELS[body.session_type]}\n"
        f"Submitted:   {created_at}\n\n"
        "--- About the athlete ---\n"
        f"{body.about_athlete.strip()}\n\n"
        "--- What they want to cover ---\n"
        f"{(body.reason or '').strip() or 'Not specified.'}"
    )
    try:
        email_sent = send_email(subject, body_text, [_DIETITIAN_RECIPIENT])
    except Exception:
        logger.exception("dietitian-booking notification email failed (non-blocking)")
        email_sent = False

    return {"ok": True, "id": booking_id, "email_sent": email_sent}
