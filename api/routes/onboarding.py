import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.models import OnboardingComplete
from api.database import get_conn
from api.services.fueling_targets import normalize_season_phase
from api.services.email_service import send_email
from api.services import email_templates
from api.services import login_alerts
from api.routes.athletes import generate_blueprint_bg

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/complete", status_code=201)
def complete_onboarding(data: OnboardingComplete, background_tasks: BackgroundTasks):
    """Create parent + athlete atomically. Either both exist or neither does."""
    p = data.parent
    a = data.athlete
    if not p.consent_confirmed:
        raise HTTPException(400, "Parental consent must be confirmed before creating an account.")
    if not (13 <= a.age <= 17):
        raise HTTPException(400, "FuelUp Youth is designed for athletes ages 13-17.")

    conn = get_conn()
    try:
        ts = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (?, ?, ?, ?)",
            (p.full_name, p.email, ts, p.consent_confirmed),
        )
        parent_row = conn.execute("SELECT * FROM parents WHERE email = ?", (p.email,)).fetchone()
        parent_id = parent_row["id"]
        # Stamp last_login_at now so a later explicit sign-in reads as a returning
        # login (👋), not another new-signup alert (🎉).
        conn.execute("UPDATE parents SET last_login_at = ? WHERE id = ?", (ts, parent_id))
        conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in,
                position, competition_level, sweat_profile, allergies, dietary_restrictions, supplement_use,
                season_phase, food_preferences, date_of_birth, lifestyle_activity, diet_pref, phone)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (parent_id, a.first_name, a.age, a.gender, a.weight_lbs, a.height_ft, a.height_in,
             a.position, a.competition_level, a.sweat_profile, a.allergies, a.dietary_restrictions,
             a.supplement_use, normalize_season_phase(a.season_phase), a.food_preferences,
             a.date_of_birth, a.lifestyle_activity or "light", a.diet_pref or "omnivore", a.phone),
        )
        athlete_row = conn.execute("SELECT * FROM athletes WHERE rowid = last_insert_rowid()").fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        if "UNIQUE" in str(e):
            raise HTTPException(409, "A parent account with this email already exists.")
        raise HTTPException(500, str(e))
    conn.close()

    parent = dict(parent_row)
    athlete = dict(athlete_row)
    background_tasks.add_task(generate_blueprint_bg, athlete["id"])

    # Beta founder alert: a brand-new signup (🎉). Backgrounded + best-effort so
    # it never blocks or slows the 201. is_new is always True — this IS the signup.
    background_tasks.add_task(
        login_alerts.notify_login, parent,
        is_new=True, athlete_hint=login_alerts.athlete_hint([athlete]),
    )

    # Best-effort welcome email — must never block or fail the 201.
    try:
        name_parts = (parent.get("full_name") or "").split()
        parent_first = name_parts[0] if name_parts else "there"
        athlete_name = athlete.get("first_name") or "your athlete"
        text, html = email_templates.welcome_email(parent_first, athlete_name)
        send_email(
            f"Welcome to FuelUp! Let's fuel {athlete_name} 🏃",
            text, [parent["email"]], html=html, bcc=["mayurkhera@gmail.com"],
        )
    except Exception:
        logger.exception("welcome email failed (non-blocking)")

    return {"parent": parent, "athlete": athlete}
