"""
Feature requests ("What's Coming" → Suggest a Feature).

POST /api/feedback/feature-request — persist a user-submitted feature suggestion
and email the team. The row is saved and a 200 is returned REGARDLESS of email
outcome: email is best-effort so a delivery failure never loses the suggestion
or fails the request (same pattern as routes/support.py).
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.database import get_conn
from api.services.email_service import send_email
from api.services import email_templates

logger = logging.getLogger(__name__)
router = APIRouter()

_RECIPIENTS = ["purvihshah@gmail.com", "mayurkhera@gmail.com"]


class FeatureRequest(BaseModel):
    suggestion: str
    reason: str | None = None
    email: str | None = None
    athlete_id: int | None = None
    submitted_at: str | None = None


@router.post("/feature-request")
def submit_feature_request(payload: FeatureRequest):
    suggestion = (payload.suggestion or "").strip()
    if not suggestion:
        raise HTTPException(400, "Suggestion is required.")

    reason = (payload.reason or "").strip() or None

    account_email = None  # resolved from athlete_id inside the DB block below
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO feature_requests
                   (email, athlete_id, suggestion, reason, submitted_at)
               VALUES (%s, %s, %s, %s, COALESCE(%s, sqlite_now()))
               RETURNING id, submitted_at""",
            (payload.email, payload.athlete_id, suggestion, reason, payload.submitted_at),
        )
        conn.commit()
        inserted = cur.fetchone()
        request_id = inserted["id"]
        submitted_at = inserted["submitted_at"]
        # Resolve the account holder's email from athlete_id when supplied, so the
        # confirmation reaches the logged-in user even if the payload email is blank.
        if payload.athlete_id is not None:
            try:
                prow = conn.execute(
                    "SELECT p.email FROM athletes a JOIN parents p ON a.parent_id = p.id WHERE a.id = %s",
                    (payload.athlete_id,),
                ).fetchone()
                account_email = prow["email"] if prow else None
            except Exception:
                logger.exception("parent email lookup failed (non-blocking)")
    finally:
        conn.close()

    # Best-effort notification — must never block or fail the 200.
    subject = "AthFuelPath — New Feature Suggestion"
    body = (
        "A new feature suggestion was submitted via the AthFuelPath app.\n\n"
        f"From:        {payload.email or 'not provided'}\n"
        f"Athlete ID:  {payload.athlete_id if payload.athlete_id is not None else 'not provided'}\n"
        f"Submitted:   {submitted_at}\n\n"
        "--- What would you like to see? ---\n"
        f"{suggestion}\n\n"
        "--- Why would this help your athlete? ---\n"
        f"{reason or 'Not provided.'}"
    )
    email_sent = send_email(subject, body, _RECIPIENTS)

    # Best-effort confirmation to the submitter. Prefer the logged-in account's
    # email (resolved from athlete_id); fall back to any email in the payload.
    confirm_to = account_email or payload.email
    if confirm_to:
        try:
            try:
                submitted_date = datetime.fromisoformat(
                    str(submitted_at).replace("Z", "+00:00")
                ).strftime("%B %d, %Y")
            except Exception:
                submitted_date = str(submitted_at)
            text, html = email_templates.feature_idea_email(
                parent_name="there", feature_idea_summary=suggestion,
                idea_id=request_id, submitted_date=submitted_date,
            )
            send_email(
                "Your feature idea is in our backlog! 💡",
                text, [confirm_to], html=html, bcc=["mayurkhera@gmail.com"],
            )
        except Exception:
            logger.exception("feature-idea confirmation email failed (non-blocking)")

    return {"ok": True, "id": request_id, "email_sent": email_sent}
