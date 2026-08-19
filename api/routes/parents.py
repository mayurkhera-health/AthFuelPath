import hashlib
import logging
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from api.models import ParentCreate, ParentResponse, ParentProfileUpdate, OTPRequest, OTPVerify
from api.database import get_conn
from api.services.email import send_otp_email
from api.services.email_service import send_email
from api.services.session_auth import mint_session_token, require_session, assert_owns_parent, assert_owns_athlete

_DELETION_RECIPIENT = "purvihshah@gmail.com"

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=ParentResponse, status_code=201)
def create_parent(data: ParentCreate):
    if not data.consent_confirmed:
        raise HTTPException(400, "Parental consent must be confirmed before creating an account.")
    conn = get_conn()
    try:
        ts = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (?, ?, ?, ?)",
            (data.full_name, data.email, ts, data.consent_confirmed),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM parents WHERE email = ?", (data.email,)).fetchone()
        return dict(row)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "A parent account with this email already exists.")
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.post("/{parent_id}/confirm")
def confirm_consent(parent_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM parents WHERE id = ?", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        conn.execute("UPDATE parents SET consent_confirmed = TRUE WHERE id = ?", (parent_id,))
        conn.commit()
        return {"message": "Consent confirmed. Welcome to Fueling2Win!", "parent_id": parent_id}
    finally:
        conn.close()


@router.post("/login")
def login(data: OTPRequest, request: Request):
    # Temporary — 2026-08-19, remove after ~7 days once we have real client-split
    # data. See docs/age-audit.md Part 14/16: legacy web sends a browser Origin +
    # UA, mobile sends none/an Expo-RN UA — this is a cleaner signal than any
    # existing DB column for "does legacy web still have real login traffic."
    log.info("parents_login_client origin=%r user_agent=%r",
              request.headers.get("origin"), request.headers.get("user-agent"))
    email = data.email.strip().lower()
    conn = get_conn()
    try:
        parent = conn.execute("SELECT * FROM parents WHERE lower(email) = lower(?)", (email,)).fetchone()
        if not parent:
            raise HTTPException(404, "No account found with that email address.")
        parent_id = dict(parent)["id"]
        athletes = conn.execute("SELECT * FROM athletes WHERE parent_id = ?", (parent_id,)).fetchall()
        token = mint_session_token(role="parent", parent_id=parent_id)
        return {"parent": dict(parent), "athletes": [dict(a) for a in athletes], "session_token": token}
    finally:
        conn.close()


@router.post("/request-otp")
def request_otp(data: OTPRequest):
    email = data.email.strip().lower()
    conn = get_conn()
    try:
        parent = conn.execute("SELECT * FROM parents WHERE lower(email) = lower(?)", (email,)).fetchone()
        if not parent:
            raise HTTPException(404, "No account found with that email address.")
        parent_id = dict(parent)["id"]

        # Rate limit: block if a code was issued in the last 60 seconds
        cutoff = (datetime.utcnow() - timedelta(seconds=60)).isoformat()
        recent = conn.execute(
            "SELECT id FROM otp_codes WHERE parent_id = ? AND created_at > ? AND used = 0",
            (parent_id, cutoff),
        ).fetchone()
        if recent:
            raise HTTPException(429, "A code was already sent. Please wait 60 seconds before requesting another.")

        code = f"{random.randint(0, 999999):06d}"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        conn.execute(
            "INSERT INTO otp_codes (parent_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (parent_id, code_hash, expires_at),
        )
        conn.commit()

        send_otp_email(email, code)
        return {"message": "A 6-digit code has been sent to your email."}
    finally:
        conn.close()


@router.post("/verify-otp")
def verify_otp(data: OTPVerify):
    email = data.email.strip().lower()
    code_hash = hashlib.sha256(data.code.strip().encode()).hexdigest()
    now = datetime.utcnow().isoformat()

    conn = get_conn()
    try:
        parent = conn.execute("SELECT * FROM parents WHERE lower(email) = lower(?)", (email,)).fetchone()
        if not parent:
            raise HTTPException(404, "No account found with that email address.")
        parent_id = dict(parent)["id"]

        row = conn.execute(
            """SELECT id FROM otp_codes
               WHERE parent_id = ? AND code_hash = ? AND used = 0 AND expires_at > ?
               ORDER BY created_at DESC LIMIT 1""",
            (parent_id, code_hash, now),
        ).fetchone()

        if not row:
            raise HTTPException(401, "Invalid or expired code. Please request a new one.")

        conn.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (dict(row)["id"],))
        conn.commit()

        athletes = conn.execute(
            "SELECT * FROM athletes WHERE parent_id = ?", (parent_id,)
        ).fetchall()
        return {"parent": dict(parent), "athletes": [dict(a) for a in athletes]}
    finally:
        conn.close()


@router.delete("/test-reset")
def test_reset(email: str):
    """Delete all data for a test email — only permitted for test@gmail.com."""
    if email.strip().lower() != "test@gmail.com":
        raise HTTPException(403, "Test reset is only permitted for test@gmail.com.")
    conn = get_conn()
    try:
        parent = conn.execute("SELECT id FROM parents WHERE email = ?", (email.strip().lower(),)).fetchone()
        if parent:
            parent_id = dict(parent)["id"]
            athletes = conn.execute("SELECT id FROM athletes WHERE parent_id = ?", (parent_id,)).fetchall()
            for a in athletes:
                athlete_id = dict(a)["id"]
                conn.execute("DELETE FROM meal_logs WHERE athlete_id = ?", (athlete_id,))
                conn.execute("DELETE FROM events WHERE athlete_id = ?", (athlete_id,))
                conn.execute("DELETE FROM daily_targets WHERE athlete_id = ?", (athlete_id,))
            conn.execute("DELETE FROM athletes WHERE parent_id = ?", (parent_id,))
            conn.execute("DELETE FROM parents WHERE id = ?", (parent_id,))
            conn.commit()
        return {"message": "Test data cleared."}
    finally:
        conn.close()


@router.delete("/{parent_id}")
def delete_parent_account(parent_id: int, identity=Depends(require_session)):
    """Record an account-deletion request and notify the team — the actual
    deletion happens manually, out of the app, not here. (Product decision,
    2026-07-27: the in-app cascade delete had a real bug — see the removed
    version's history — and the team wants a human to handle every deletion
    rather than an automated in-app cascade.) Required for Apple App Store
    Guideline 5.1.1(v): the app must let the user INITIATE deletion without
    leaving the app; it does not require the deletion itself be automatic."""
    assert_owns_parent(identity, parent_id)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT full_name, email FROM parents WHERE id = ?", (parent_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        parent = dict(row)
        athlete_rows = conn.execute(
            "SELECT first_name FROM athletes WHERE parent_id = ?", (parent_id,)
        ).fetchall()
        athlete_names = ", ".join(dict(a)["first_name"] for a in athlete_rows) or "(no athletes on file)"

        cur = conn.execute(
            """INSERT INTO account_deletion_requests (parent_id, parent_name, parent_email, athlete_names)
               VALUES (?, ?, ?, ?)""",
            (parent_id, parent["full_name"], parent["email"], athlete_names),
        )
        conn.commit()
        request_id = cur.lastrowid
    finally:
        conn.close()

    # Best-effort notification — the request is already durably saved above
    # regardless of email outcome.
    subject = f"Account Deletion Request — {parent['full_name']}"
    body = (
        "A parent requested account deletion via the AthFuelPath app.\n\n"
        f"Parent:       {parent['full_name']} <{parent['email']}> (id {parent_id})\n"
        f"Athlete(s):   {athlete_names}\n\n"
        "This account has NOT been deleted automatically. Please process the "
        "deletion manually and confirm with the family once complete."
    )
    try:
        email_sent = send_email(subject, body, [_DELETION_RECIPIENT])
    except Exception:
        logger.exception("account-deletion notification email failed (non-blocking)")
        email_sent = False

    return {"received": True, "id": request_id, "email_sent": email_sent}


@router.patch("/{parent_id}/dismiss-schedule-reminder")
def dismiss_schedule_reminder(parent_id: int, identity=Depends(require_session)):
    assert_owns_parent(identity, parent_id)
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM parents WHERE id = ?", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        conn.execute(
            "UPDATE parents SET schedule_reminder_dismissed = 1 WHERE id = ?",
            (parent_id,),
        )
        conn.commit()
        return {"schedule_reminder_dismissed": True}
    finally:
        conn.close()


@router.get("/exists")
def email_exists(email: str):
    """Read-only: does a parent with this email exist? Creates nothing."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM parents WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return {"exists": row is not None}
    finally:
        conn.close()


@router.patch("/{parent_id}/profile", response_model=ParentResponse)
def update_parent_profile(parent_id: int, data: ParentProfileUpdate, identity=Depends(require_session)):
    assert_owns_parent(identity, parent_id)
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM parents WHERE id = ?", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        conn.execute(
            "UPDATE parents SET full_name = ?, phone = ? WHERE id = ?",
            (data.full_name.strip(), data.phone, parent_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM parents WHERE id = ?", (parent_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/{parent_id}", response_model=ParentResponse)
def get_parent(parent_id: int, identity=Depends(require_session)):
    assert_owns_parent(identity, parent_id)
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM parents WHERE id = ?", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        return dict(row)
    finally:
        conn.close()


@router.post("/{parent_id}/blueprint-viewed")
def blueprint_viewed(parent_id: int, background_tasks: BackgroundTasks, identity=Depends(require_session)):
    """Called once when a parent first opens the Blueprint screen.
    Idempotent: stamps blueprint_first_viewed_at only on the first call,
    then sends a one-time onboarding summary email to the founder."""
    assert_owns_parent(identity, parent_id)
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM parents WHERE id = ?", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        parent = dict(row)

        # Already recorded — no-op
        if parent.get("blueprint_first_viewed_at"):
            return {"ok": True, "first_view": False}

        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE parents SET blueprint_first_viewed_at = ? WHERE id = ?",
            (now, parent_id),
        )
        conn.commit()

        athletes = [dict(a) for a in conn.execute(
            "SELECT * FROM athletes WHERE parent_id = ? ORDER BY id", (parent_id,)
        ).fetchall()]

        background_tasks.add_task(_send_blueprint_summary, parent, athletes, now)
        return {"ok": True, "first_view": True}
    finally:
        conn.close()


def _send_blueprint_summary(parent: dict, athletes: list, viewed_at: str) -> None:
    """Assemble and email the onboarding summary to the founder. Best-effort."""
    try:
        from api.services.email_service import send_email

        first = (parent.get("full_name") or "Someone").split()[0]
        email = parent.get("email", "—")
        signed_up = parent.get("created_at", "—")

        lines = [
            f"🎯 Blueprint First View — {first}",
            "",
            f"Parent:     {parent.get('full_name', '—')}",
            f"Email:      {email}",
            f"Signed up:  {signed_up}",
            f"Blueprint:  {viewed_at}",
            "",
        ]

        if not athletes:
            lines.append("Athletes:   (none linked yet)")
        else:
            for a in athletes:
                name = a.get("first_name", "—")
                age = a.get("age", "—")
                gender = a.get("gender", "—")
                comp = a.get("competition_level") or "—"
                phase = a.get("season_phase") or "—"
                sport = a.get("sport") or "—"
                lines.append(f"Athlete:    {name}, age {age}, {gender}")
                lines.append(f"            Sport: {sport} | Level: {comp} | Phase: {phase}")

                # Event stats
                conn = get_conn()
                try:
                    stats = conn.execute(
                        "SELECT COUNT(*) as total, "
                        "MIN(event_date) as first_date, MAX(event_date) as last_date, "
                        "source FROM events WHERE athlete_id = ? GROUP BY source",
                        (a["id"],),
                    ).fetchall()
                    total_events = sum(s[0] for s in stats)
                    if total_events == 0:
                        lines.append("            Calendar: No events imported yet")
                    else:
                        for s in stats:
                            sd = dict(s)
                            src = sd.get("source") or "manual"
                            cnt = sd["total"]
                            d1, d2 = sd.get("first_date", "?"), sd.get("last_date", "?")
                            platform = "BYGA" if src == "byga" else "PlayMetrics" if src == "playmetrics" else src.title()
                            lines.append(f"            {platform}: {cnt} events ({d1} → {d2})")
                finally:
                    conn.close()
                lines.append("")

        body = "\n".join(lines)
        send_email(
            subject=f"🎯 AthFuelPath Blueprint View — {first} ({email})",
            body=body,
            to=["mayurkhera@gmail.com"],
        )
    except Exception:
        log.warning("blueprint summary email failed", exc_info=True)
