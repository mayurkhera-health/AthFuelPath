"""
Support / problem reports.

POST /api/support/report — persist a user-submitted problem report (with an
optional screenshot) and email the team. The report is saved to the DB and a
201 is returned REGARDLESS of email outcome: email is best-effort so a delivery
failure never loses the report or fails the request.
"""

import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from api.database import get_conn
from api.services.email_service import send_email
from api.services import email_templates

logger = logging.getLogger(__name__)
router = APIRouter()

# Screenshots are written here — same ephemeral /tmp pattern as meal photos
# (api/routes/today.py). Acceptable: the report row + email carry the content.
_REPORTS_DIR = Path("/tmp/athfuelpath_reports")

_REPORT_RECIPIENTS = ["mayurkhera@gmail.com", "purvihshah@gmail.com"]


async def _store_screenshot(screenshot: UploadFile) -> str | None:
    """Save the uploaded screenshot to disk; return its path, or None on failure."""
    try:
        content = await screenshot.read()
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        raw = screenshot.filename or "screenshot.jpg"
        ext = raw.rsplit(".", 1)[-1] if "." in raw else "jpg"
        path = _REPORTS_DIR / f"report_{uuid.uuid4().hex[:8]}.{ext}"
        path.write_bytes(content)
        return str(path)
    except Exception:
        logger.exception("screenshot store failed")
        return None


@router.post("/report", status_code=201)
async def submit_report(
    description: str = Form(...),
    app_version: str | None = Form(None),
    platform: str | None = Form(None),
    role_hint: str | None = Form(None),
    category: str | None = Form(None),
    reporter_name: str | None = Form(None),
    reporter_email: str | None = Form(None),
    parent_id: int | None = Form(None),
    screenshot: UploadFile | None = File(None),
):
    desc = description.strip()
    if not desc:
        raise HTTPException(400, "Description is required.")

    screenshot_url = await _store_screenshot(screenshot) if screenshot is not None else None

    account_email = None  # resolved from parent_id inside the DB block below
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO problem_reports
                   (description, screenshot_url, app_version, platform, role_hint, category)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (desc, screenshot_url, app_version, platform, role_hint, category),
        )
        conn.commit()
        report_id = cur.lastrowid
        created_at_utc = conn.execute(
            "SELECT created_at FROM problem_reports WHERE id = ?", (report_id,)
        ).fetchone()[0]
        # Convert UTC → PST (UTC-8) / PDT (UTC-7); display as PST for simplicity
        PST = timezone(timedelta(hours=-8))
        created_at = datetime.fromisoformat(created_at_utc).replace(tzinfo=timezone.utc).astimezone(PST).strftime("%Y-%m-%d %I:%M %p PST")
        # Resolve the account holder's email from parent_id when supplied, so the
        # confirmation reaches the logged-in user even if the form email is blank.
        if parent_id is not None:
            try:
                prow = conn.execute(
                    "SELECT email FROM parents WHERE id = ?", (parent_id,)
                ).fetchone()
                account_email = prow["email"] if prow else None
            except Exception:
                logger.exception("parent email lookup failed (non-blocking)")
    finally:
        conn.close()

    # Best-effort notification — must never block or fail the 201.
    subject = f"AthFuelPath — {category or 'Problem Report'} from {role_hint or 'unknown'} (v{app_version or 'unknown'})"
    body = (
        "A new problem report was submitted via the AthFuelPath app.\n\n"
        f"Name:        {reporter_name or 'not provided'}\n"
        f"Email:       {reporter_email or 'not provided'}\n"
        f"Category:    {category or 'not provided'}\n"
        f"App version: {app_version or 'not provided'}\n"
        f"Platform:    {platform or 'not provided'}\n"
        f"Submitted:   {created_at} UTC\n\n"
        "--- What they reported ---\n"
        f"{desc}\n\n"
        "--- Screenshot ---\n"
        f"{'Attached — see image below.' if screenshot_url else 'No screenshot provided.'}"
    )
    email_sent = send_email(subject, body, _REPORT_RECIPIENTS, attachment_path=screenshot_url)

    # Best-effort confirmation to the reporter. Prefer the logged-in account's
    # email (resolved from parent_id); fall back to any email typed on the form.
    confirm_to = account_email or reporter_email
    if confirm_to:
        try:
            text, html = email_templates.problem_report_email(
                athlete_name="your athlete", problem_summary=desc, report_id=report_id,
            )
            send_email(
                "We received your bug report - we're on it!",
                text, [confirm_to], html=html, bcc=["mayurkhera@gmail.com"],
            )
        except Exception:
            logger.exception("problem-report confirmation email failed (non-blocking)")

    return {"ok": True, "id": report_id, "email_sent": email_sent}
