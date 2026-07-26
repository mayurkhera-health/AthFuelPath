"""Performance Plate — per-window plate shape + allergy-filtered food options.

GET /api/plate/window?athlete_id=&window_key=
  → { window_key, profile_key | null, plate | null, options[] }

Options are 4–8 recipe combos ({id, short_label, plate_sections}) drawn from the
recipe library, filtered by the athlete's allergies (safety) + dietary prefs.
`profile_key` is the recipe-catalog window vocabulary (e.g. "breakfast") that
`window_key` (e.g. "everyday_breakfast") maps to — the same vocabulary the
recipes/grocery-list endpoints use, so a client can fetch/select the full
recipe behind an option via /api/recipes/{id} and /api/recipes/selections
using this profile_key as fueling_window_key.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_conn
from api.services import recipe_db
from api.services.plate_config import (
    performance_plate_enabled,
    plate_for_window,
    recipe_profile_for_window,
    parse_restrictions,
    normalize_allergens,
    select_options,
)
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


@router.get("/window")
def get_window_plate(
    athlete_id: int = Query(...),
    window_key: str = Query(...),
    identity=Depends(require_session),
):
    # Feature flag — ships dark. When off, no DB work: return an empty payload so
    # the client renders nothing (and does no per-window plate fetch overhead).
    if not performance_plate_enabled():
        return {"window_key": window_key, "profile_key": None, "plate": None, "options": []}

    plate = plate_for_window(window_key)
    if plate is None:
        # Nudge/hydration window — no plate, no options.
        return {"window_key": window_key, "profile_key": None, "plate": None, "options": []}

    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute(
            "SELECT allergies, dietary_restrictions FROM athletes WHERE id = ?",
            (athlete_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, f"Athlete {athlete_id} not found")
    row = dict(row)

    allergens = normalize_allergens(parse_restrictions(row.get("allergies")))
    dietary = parse_restrictions(row.get("dietary_restrictions"))
    profile = recipe_profile_for_window(window_key)

    recipes = recipe_db.get_valid_recipes(
        profile, allergies=allergens, dietary_restrictions=dietary
    )
    options = select_options(recipes, n=8)

    return {"window_key": window_key, "profile_key": profile, "plate": plate, "options": options}
