from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from api.models import MealLogCreate, MealLogResponse, PhotoMealAnalyzeRequest, VoiceMealAnalyzeRequest
from api.database import get_conn
from api.services import photo_meal_analyzer, voice_meal_analyzer
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


def _parse_allergies(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return [a.strip() for a in raw if a and str(a).strip().lower() != "none"]
    return [a.strip() for a in str(raw).split(",") if a.strip().lower() != "none"]


@router.post("/analyze-photo")
def analyze_photo_meal(data: PhotoMealAnalyzeRequest, identity=Depends(require_session)):
    if not data.image_base64 or len(data.image_base64) < 100:
        raise HTTPException(400, "Please provide a valid base64-encoded image.")
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
    finally:
        conn.close()

    allergies = data.allergies or _parse_allergies(athlete.get("allergies"))
    media_type = data.image_media_type or "image/jpeg"
    if media_type not in ("image/jpeg", "image/png"):
        media_type = "image/jpeg"

    try:
        analysis = photo_meal_analyzer.analyze_photo(
            data.image_base64,
            media_type=media_type,
            allergies=allergies,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Photo analysis failed: {e}")

    return {"analysis": analysis}


@router.post("/analyze-voice")
def analyze_voice_meal(data: VoiceMealAnalyzeRequest, identity=Depends(require_session)):
    transcription = (data.transcription or "").strip()
    if len(transcription) < 3:
        raise HTTPException(400, "Please provide a meal description (at least 3 characters).")
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
    finally:
        conn.close()

    allergies = data.allergies or _parse_allergies(athlete.get("allergies"))

    try:
        analysis = voice_meal_analyzer.analyze_voice(transcription, allergies=allergies)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Voice analysis failed: {e}")

    return {"analysis": analysis}


@router.post("/", response_model=MealLogResponse, status_code=201)
def log_meal(data: MealLogCreate, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        cur = conn.execute(
            """INSERT INTO meal_logs
               (athlete_id, log_method, description, calories, carbs_g, protein_g,
                fat_g, iron_mg, calcium_mg, water_oz, edamam_raw)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (data.athlete_id, data.log_method, data.description, data.calories,
             data.carbs_g, data.protein_g, data.fat_g, data.iron_mg,
             data.calcium_mg, data.water_oz, data.edamam_raw),
        )
        conn.commit()
        row = cur.fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/athlete/{athlete_id}", response_model=List[MealLogResponse])
def get_meals(athlete_id: int, date: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if date:
            rows = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at) = %s ORDER BY logged_at",
                (athlete_id, date),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = %s ORDER BY logged_at DESC LIMIT 50",
                (athlete_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.delete("/{meal_id}")
def delete_meal(meal_id: int, identity=Depends(require_session)):
    conn = get_conn()
    try:
        # No athlete_id on the request — resolve it from the meal record itself
        # before any ownership check is possible.
        row = conn.execute("SELECT athlete_id FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal log not found.")
        assert_owns_athlete(identity, row["athlete_id"], conn)
        conn.execute("DELETE FROM meal_logs WHERE id = %s", (meal_id,))
        conn.commit()
        return {"message": "Meal log deleted.", "meal_id": meal_id}
    finally:
        conn.close()
