from datetime import date as dt_date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


class WaterLogCreate(BaseModel):
    athlete_id: int
    cups: int
    date: str = None


@router.get("/{athlete_id}/today")
def get_water_today(athlete_id: int, identity=Depends(require_session)):
    today = str(dt_date.today())
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute(
            "SELECT cups FROM water_logs WHERE athlete_id = ? AND log_date = ?",
            (athlete_id, today),
        ).fetchone()
        return {"athlete_id": athlete_id, "date": today, "cups": row["cups"] if row else 0}
    finally:
        conn.close()


@router.post("/")
def log_water(data: WaterLogCreate, identity=Depends(require_session)):
    log_date = data.date or str(dt_date.today())
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = ?", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        conn.execute(
            """INSERT INTO water_logs (athlete_id, log_date, cups, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(athlete_id, log_date)
               DO UPDATE SET cups = excluded.cups, updated_at = CURRENT_TIMESTAMP""",
            (data.athlete_id, log_date, max(0, data.cups)),
        )
        conn.commit()
        return {"athlete_id": data.athlete_id, "date": log_date, "cups": data.cups}
    finally:
        conn.close()
