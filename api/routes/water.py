from datetime import date as dt_date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()

# A hydration bottle is a few cups; even an all-day tournament wouldn't put a
# real reading anywhere near this — it exists to reject fat-fingered/garbage
# input (e.g. a stray extra digit), not to model a plausible daily max.
_MAX_PLAUSIBLE_CUPS = 50


class WaterLogCreate(BaseModel):
    athlete_id: int
    cups: int = Field(ge=0, le=_MAX_PLAUSIBLE_CUPS)
    date: str | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        # A malformed date used to be stored as-is: log_water's own
        # ON CONFLICT key is (athlete_id, log_date), so it saved successfully,
        # but get_water_today() always queries with a real ISO date string —
        # the row could never match, so it silently vanished from every GET.
        if v is None:
            return v
        try:
            dt_date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"date must be an ISO 8601 date (YYYY-MM-DD), got {v!r}")
        return v


@router.get("/{athlete_id}/today")
def get_water_today(athlete_id: int, date: str | None = None, identity=Depends(require_session)):
    if date is not None:
        try:
            dt_date.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, f"date must be an ISO 8601 date (YYYY-MM-DD), got {date!r}")
    today = date or str(dt_date.today())
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        row = conn.execute(
            "SELECT cups FROM water_logs WHERE athlete_id = %s AND log_date = %s",
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
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        conn.execute(
            """INSERT INTO water_logs (athlete_id, log_date, cups, updated_at)
               VALUES (%s, %s, %s, sqlite_now())
               ON CONFLICT(athlete_id, log_date)
               DO UPDATE SET cups = excluded.cups, updated_at = sqlite_now()""",
            (data.athlete_id, log_date, data.cups),
        )
        conn.commit()
        return {"athlete_id": data.athlete_id, "date": log_date, "cups": data.cups}
    finally:
        conn.close()
