from datetime import date as dt_date
from fastapi import APIRouter, Depends, HTTPException
from api.database import get_conn
from api.services import claude_ai
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


@router.get("/{athlete_id}")
def get_gap_analysis(athlete_id: int, date: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
        target_date = date or str(dt_date.today())

        targets_row = conn.execute(
            "SELECT * FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
            (athlete_id, target_date),
        ).fetchone()
        if not targets_row:
            raise HTTPException(
                404,
                f"No targets for {target_date}. Call GET /api/nutrition/targets/{athlete_id}?date={target_date} first.",
            )
        targets = dict(targets_row)

        meals = conn.execute(
            "SELECT * FROM meal_logs WHERE athlete_id = ? AND DATE(logged_at) = ?",
            (athlete_id, target_date),
        ).fetchall()
        meal_list = [dict(m) for m in meals]

        result = claude_ai.prompt2_meal_analysis(athlete, targets, meal_list, target_date)
        result["athlete_id"] = athlete_id
        result["date"] = target_date
        result["meals_logged"] = len(meal_list)
        result["disclaimer"] = "Fueling2Win provides educational food guidance — not medical nutrition therapy."
        return result
    finally:
        conn.close()
