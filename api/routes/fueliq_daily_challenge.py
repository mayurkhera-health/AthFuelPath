"""
Fuel IQ Daily Challenge — a single global myth-style challenge published per
calendar day (PST), replacing the old per-athlete Myth Buster pool.

GET  /api/{athlete_id}/daily-challenge
POST /api/{athlete_id}/daily-challenge/verdict

Deliberately a separate route module from api/routes/fueliq.py: no shared
score, no shared streak — see api/services/fueliq_daily_challenge_service.py
for why. Still gated by the same FUELIQ_ENABLED flag, ships dark like the
rest of Fuel IQ.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.database import get_conn
from api.models import FuelIQDailyChallengeVerdict
from api.services import fueliq_service as fq
from api.services import fueliq_daily_challenge_service as fdc
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


@router.get("/{athlete_id}/daily-challenge")
def get_daily_challenge(athlete_id: int, identity=Depends(require_session)):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        result = fdc.get_todays_challenge(athlete_id, conn)
    finally:
        conn.close()

    return {"enabled": True, **result}


@router.post("/{athlete_id}/daily-challenge/verdict")
def submit_daily_challenge_verdict(
    athlete_id: int, body: FuelIQDailyChallengeVerdict, identity=Depends(require_session),
):
    if not fq.fueliq_enabled():
        return {"enabled": False}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        try:
            result = fdc.submit_daily_challenge_verdict(athlete_id, body.guess, conn)
        except ValueError as e:
            raise HTTPException(404, str(e))
    finally:
        conn.close()

    return {"enabled": True, **result}
