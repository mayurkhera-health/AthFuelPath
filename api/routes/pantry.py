# api/routes/pantry.py
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from api.database import get_conn
from api.services import claude_ai
from api.services.nutrition_calc import calc_daily_targets
from api.services.pantry_service import (
    safe_foods_for_athlete,
    build_pantry_items,
    get_pantry_list,
    group_pantry_items,
    cue_label_for,
)
from api.services.food_db import get_food_by_id
from api.services.pantry_plan import compute_slot_plan, fallback_select, fallback_replacement
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


class PantryExclude(BaseModel):
    athlete_id: int
    food_id: str
    food_name: str


class PantryCheckPatch(BaseModel):
    athlete_id: int
    checked: bool


def _require_athlete(athlete_id: int, conn):
    """Fetch all athlete columns needed across pantry endpoints in one query.

    Must include diet_pref and date_of_birth — calc_daily_targets() silently
    defaults diet_pref to "omnivore" and falls back from a precise DOB-based
    age to the coarse integer `age` field when either is missing from this
    dict, understating protein targets and the vegan iron-risk flag for
    vegetarian/vegan athletes, and using less precise age-based RMR math for
    every athlete regardless of diet."""
    row = conn.execute(
        """SELECT id, first_name, allergies, dietary_restrictions,
                  weight_lbs, height_ft, height_in, gender, age,
                  lifestyle_activity, season_phase, food_preferences,
                  diet_pref, date_of_birth
           FROM athletes WHERE id = ?""",
        (athlete_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Athlete not found.")
    return dict(row)


def _week_nutrition(athlete: dict, week_start: str, week_events: list[dict]) -> dict:
    """Compute avg daily nutrition targets for the week — called once per request."""
    monday = date.fromisoformat(week_start)
    event_by_date = {e.get("event_date") or e.get("date"): e for e in week_events}
    daily_totals = {"calories": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0, "hydration_oz": 0}
    for i in range(7):
        d = (monday + timedelta(days=i)).isoformat()
        ev = event_by_date.get(d)
        event_type = ev["event_type"] if ev else "rest"
        targets = calc_daily_targets(athlete, event_type=event_type)
        daily_totals["calories"]  += targets.get("total_calories", 0)
        daily_totals["carbs_g"]   += targets.get("carbs_g", 0)
        daily_totals["protein_g"] += targets.get("protein_g", 0)
        daily_totals["fat_g"]     += targets.get("fat_g", 0)
        daily_totals["hydration_oz"] += targets.get("hydration_oz", 0)
    return {
        "calories":  round(daily_totals["calories"] / 7),
        "carbs_g":   round(daily_totals["carbs_g"] / 7),
        "protein_g": round(daily_totals["protein_g"] / 7),
        "fat_g":     round(daily_totals["fat_g"] / 7),
        "hydration_oz": round(daily_totals["hydration_oz"] / 7),
    }


@router.get("/list")
def get_list(athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        athlete = _require_athlete(athlete_id, conn)

        event_rows = conn.execute(
            """SELECT event_date, event_type, event_name, start_time
               FROM events
               WHERE athlete_id = ? AND event_date >= ? AND event_date < date(?, '+7 days')
               ORDER BY event_date""",
            (athlete_id, week_start, week_start),
        ).fetchall()
        week_events = [dict(r) for r in event_rows]

        items = get_pantry_list(athlete_id, week_start, conn)
        groups = group_pantry_items(items)
        return {
            "athlete_id":     athlete_id,
            "week_start":     week_start,
            "generated":      len(items) > 0,
            "item_count":     len(items),
            "checked_count":  sum(1 for i in items if i["checked"]),
            "groups":         groups,
            "week_events":    week_events,
            "week_nutrition": _week_nutrition(athlete, week_start, week_events),
        }
    finally:
        conn.close()


@router.post("/generate")
def generate_list(athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        athlete = _require_athlete(athlete_id, conn)

        # Single events fetch — reused for both AI prompt and response
        event_rows = conn.execute(
            """SELECT event_date, event_type, event_name, start_time, duration_hours
               FROM events
               WHERE athlete_id = ? AND event_date >= ? AND event_date < date(?, '+7 days')
               ORDER BY event_date""",
            (athlete_id, week_start, week_start),
        ).fetchall()
        week_events = [dict(r) for r in event_rows]

        # Build schedule summary for AI prompt
        monday = date.fromisoformat(week_start)
        event_by_date = {e["event_date"]: e for e in week_events}
        week_schedule = []
        for i in range(7):
            d = (monday + timedelta(days=i)).isoformat()
            ev = event_by_date.get(d)
            week_schedule.append({
                "date":         d,
                "event_type":   ev["event_type"] if ev else "rest",
                "duration_min": int((ev.get("duration_hours") or 0) * 60) if ev else 0,
            })

        excluded_rows = conn.execute(
            "SELECT food_name FROM athlete_food_prefs WHERE athlete_id = ? AND preference = 'disliked'",
            (athlete_id,),
        ).fetchall()
        excluded_names = {r["food_name"] for r in excluded_rows}

        safe = [f for f in safe_foods_for_athlete(athlete) if f["name"] not in excluded_names]

        targets_by_day = [calc_daily_targets(athlete, event_type=d["event_type"]) for d in week_schedule]
        slot_plan = compute_slot_plan(week_schedule, targets_by_day, athlete)

        safe_ids = {f["food_id"] for f in safe}
        ai_result = claude_ai.prompt8_pantry_plan(athlete, week_schedule, slot_plan, safe)
        raw_items = [it for it in ai_result.get("items", [])
                     if isinstance(it, dict) and it.get("food_id") in safe_ids]
        if not raw_items:
            raw_items = fallback_select(slot_plan, safe, athlete)

        food_item_map = {
            it["food_id"]: {"meal_context": it.get("meal_context", "snacks_everyday"),
                            "must_have": bool(it.get("must_have", False))}
            for it in raw_items if it.get("food_id")
        }
        if not food_item_map:                      # truly nothing safe to pick (extreme allergies)
            raise HTTPException(422, "No suitable foods available for this athlete's restrictions.")

        items  = build_pantry_items(athlete_id, week_start, food_item_map, conn)
        groups = group_pantry_items(items)

        return {
            "athlete_id":     athlete_id,
            "week_start":     week_start,
            "generated":      len(items) > 0,
            "item_count":     len(items),
            "checked_count":  0,
            "groups":         groups,
            "reasoning":      ai_result.get("reasoning", ""),
            "week_events":    week_events,
            "week_nutrition": _week_nutrition(athlete, week_start, week_events),
        }
    finally:
        conn.close()


@router.patch("/items/{item_id}")
def patch_item(item_id: int, data: PantryCheckPatch, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        row = conn.execute(
            "SELECT id FROM pantry_list_items WHERE id = ? AND athlete_id = ?", (item_id, data.athlete_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found.")
        conn.execute(
            "UPDATE pantry_list_items SET checked = ? WHERE id = ?",
            (1 if data.checked else 0, item_id),
        )
        conn.commit()
        return {"id": item_id, "checked": data.checked}
    finally:
        conn.close()


@router.delete("/items/{item_id}")
def delete_item(item_id: int, athlete_id: int = Query(...), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute(
            "SELECT id FROM pantry_list_items WHERE id = ? AND athlete_id = ?",
            (item_id, athlete_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found.")
        conn.execute("DELETE FROM pantry_list_items WHERE id = ?", (item_id,))
        conn.commit()
        return {"status": "removed", "id": item_id}
    finally:
        conn.close()


class PantrySuggestReplacement(BaseModel):
    athlete_id: int
    week_start: str
    food_id: str
    food_name: str
    meal_context: str


class PantryAddItem(BaseModel):
    athlete_id: int
    week_start: str
    food_id: str
    meal_context: str


@router.post("/exclude")
def exclude_food(data: PantryExclude, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        _require_athlete(data.athlete_id, conn)
        conn.execute(
            """INSERT OR REPLACE INTO athlete_food_prefs (athlete_id, food_name, preference, category)
               VALUES (?, ?, 'disliked', NULL)""",
            (data.athlete_id, data.food_name),
        )
        # Also remove it from the current stored list(s) so it can't resurface on a
        # swap or refetch. Allergy => all weeks; food_id is the exact key.
        conn.execute(
            "DELETE FROM pantry_list_items WHERE athlete_id = ? AND food_id = ?",
            (data.athlete_id, data.food_id),
        )
        conn.commit()
        return {"status": "excluded", "food_name": data.food_name}
    finally:
        conn.close()


@router.post("/suggest-replacement")
def suggest_replacement(data: PantrySuggestReplacement, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        athlete = _require_athlete(data.athlete_id, conn)

        # 1. Get current list food_ids (to avoid duplicates)
        current_rows = conn.execute(
            "SELECT food_id FROM pantry_list_items WHERE athlete_id = ? AND week_start = ?",
            (data.athlete_id, data.week_start),
        ).fetchall()
        current_food_ids = {r["food_id"] for r in current_rows}

        # 2. Remove the excluded item from the list
        conn.execute(
            "DELETE FROM pantry_list_items WHERE athlete_id = ? AND week_start = ? AND food_id = ?",
            (data.athlete_id, data.week_start, data.food_id),
        )

        # 3. Get safe foods for athlete
        safe = safe_foods_for_athlete(athlete)

        # 4. Ask AI for one replacement
        result = claude_ai.prompt_suggest_replacement(
            athlete=athlete,
            excluded_food_name=data.food_name,
            meal_context=data.meal_context,
            safe_foods=safe,
            current_food_ids=list(current_food_ids - {data.food_id}),
        )

        new_food_id = result.get("food_id")
        if not new_food_id or not get_food_by_id(new_food_id):
            removed = get_food_by_id(data.food_id)
            new_food_id = fallback_replacement(
                removed["role"] if removed else "carb",
                removed.get("gi_tier") if (removed and data.meal_context == "pre_training_fuel") else None,
                safe,
                list(current_food_ids),
            )
        if new_food_id:
            food = get_food_by_id(new_food_id)
            if food:
                cue = cue_label_for(food)
                conn.execute(
                    """INSERT OR IGNORE INTO pantry_list_items
                       (athlete_id, week_start, food_id, name, cue_label, purchase_unit, role, meal_context, must_have)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (data.athlete_id, data.week_start, food["food_id"], food["name"],
                     cue, food["purchase_unit"], food["role"], data.meal_context),
                )

        conn.commit()

        # 5. Build response — reuse already-fetched athlete row
        event_rows = conn.execute(
            """SELECT event_date, event_type, event_name, start_time
               FROM events
               WHERE athlete_id = ? AND event_date >= ? AND event_date < date(?, '+7 days')
               ORDER BY event_date""",
            (data.athlete_id, data.week_start, data.week_start),
        ).fetchall()
        week_events = [dict(r) for r in event_rows]
        week_nutrition = _week_nutrition(athlete, data.week_start, week_events)

        # 6. Return full updated list
        items = get_pantry_list(data.athlete_id, data.week_start, conn)
        groups = group_pantry_items(items)
        return {
            "athlete_id":     data.athlete_id,
            "week_start":     data.week_start,
            "generated":      True,
            "item_count":     len(items),
            "checked_count":  sum(1 for i in items if i["checked"]),
            "groups":         groups,
            "week_events":    week_events,
            "week_nutrition": week_nutrition,
        }
    finally:
        conn.close()


@router.get("/gap-suggestions")
def gap_suggestions(
    athlete_id: int = Query(...),
    week_start: str = Query(...),
    gap_type: str = Query(...),
    identity=Depends(require_session),
):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        athlete = _require_athlete(athlete_id, conn)

        # Get current pantry list food_ids to exclude
        current_rows = conn.execute(
            "SELECT food_id FROM pantry_list_items WHERE athlete_id = ? AND week_start = ?",
            (athlete_id, week_start),
        ).fetchall()
        current_food_ids = {r["food_id"] for r in current_rows}

        # Filter safe foods for athlete
        safe = safe_foods_for_athlete(athlete)

        # Filter by gap_type
        if gap_type == "fast_carb":
            candidates = [f for f in safe if f.get("role") == "carb" and f.get("gi_tier") == "fast"]
        elif gap_type == "protein":
            candidates = [f for f in safe if f.get("role") in ("protein", "dairy")]
        elif gap_type == "produce":
            candidates = [f for f in safe if f.get("role") == "produce"]
        else:
            raise HTTPException(400, f"Unknown gap_type: {gap_type}")

        # Exclude already-listed foods
        candidates = [f for f in candidates if f["food_id"] not in current_food_ids]

        # Return up to 3, stripping internal gi_tier field
        suggestions = [
            {
                "food_id":       f["food_id"],
                "name":          f["name"],
                "purchase_unit": f["purchase_unit"],
                "cue_label":     cue_label_for(f),
            }
            for f in candidates[:3]
        ]
        return {"suggestions": suggestions}
    finally:
        conn.close()


def _build_list_response(athlete_id: int, week_start: str, conn):
    """Helper: build the full GET /list response shape from existing data."""
    athlete = _require_athlete(athlete_id, conn)
    event_rows = conn.execute(
        """SELECT event_date, event_type, event_name, start_time
           FROM events
           WHERE athlete_id = ? AND event_date >= ? AND event_date < date(?, '+7 days')
           ORDER BY event_date""",
        (athlete_id, week_start, week_start),
    ).fetchall()
    week_events = [dict(r) for r in event_rows]
    items  = get_pantry_list(athlete_id, week_start, conn)
    groups = group_pantry_items(items)
    return {
        "athlete_id":     athlete_id,
        "week_start":     week_start,
        "generated":      len(items) > 0,
        "item_count":     len(items),
        "checked_count":  sum(1 for i in items if i["checked"]),
        "groups":         groups,
        "week_events":    week_events,
        "week_nutrition": _week_nutrition(athlete, week_start, week_events),
    }


@router.post("/regenerate-unchecked")
def regenerate_unchecked(
    athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session),
):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        athlete = _require_athlete(athlete_id, conn)

        # 1. Get checked food_ids (keep these, exclude from AI)
        checked_rows = conn.execute(
            "SELECT food_id FROM pantry_list_items WHERE athlete_id = ? AND week_start = ? AND checked = 1",
            (athlete_id, week_start),
        ).fetchall()
        checked_food_ids = {r["food_id"] for r in checked_rows}

        # 2. Delete only unchecked items
        conn.execute(
            "DELETE FROM pantry_list_items WHERE athlete_id = ? AND week_start = ? AND checked = 0",
            (athlete_id, week_start),
        )

        # 3. Build week schedule (same as /generate)
        rows = conn.execute(
            """SELECT event_date as date, event_type, duration_hours
               FROM events
               WHERE athlete_id = ? AND event_date >= ? AND event_date < date(?, '+7 days')
               ORDER BY event_date""",
            (athlete_id, week_start, week_start),
        ).fetchall()
        week_events_raw = [dict(r) for r in rows]
        monday = date.fromisoformat(week_start)
        event_by_date = {e["date"]: e for e in week_events_raw}
        week_schedule = []
        for i in range(7):
            d = (monday + timedelta(days=i)).isoformat()
            event = event_by_date.get(d)
            week_schedule.append({
                "date": d,
                "event_type": event["event_type"] if event else "rest",
                "duration_min": int((event.get("duration_hours") or 0) * 60) if event else 0,
            })

        # 4. Load excluded food names
        excluded_rows = conn.execute(
            "SELECT food_name FROM athlete_food_prefs WHERE athlete_id = ? AND preference = 'disliked'",
            (athlete_id,),
        ).fetchall()
        excluded_names = {r["food_name"] for r in excluded_rows}

        # 5. Filter safe foods — exclude already-checked items AND disliked foods
        safe = [
            f for f in safe_foods_for_athlete(athlete)
            if f["name"] not in excluded_names and f["food_id"] not in checked_food_ids
        ]

        # 6. Ask AI (hybrid: slot plan + AI + deterministic fallback)
        targets_by_day = [calc_daily_targets(athlete, event_type=d["event_type"]) for d in week_schedule]
        slot_plan = compute_slot_plan(week_schedule, targets_by_day, athlete)

        safe_ids = {f["food_id"] for f in safe}
        ai_result = claude_ai.prompt8_pantry_plan(athlete, week_schedule, slot_plan, safe)
        raw_items = [it for it in ai_result.get("items", [])
                     if isinstance(it, dict) and it.get("food_id") in safe_ids]
        if not raw_items:
            raw_items = fallback_select(slot_plan, safe, athlete)

        food_item_map = {
            it["food_id"]: {"meal_context": it.get("meal_context", "snacks_everyday"),
                            "must_have": bool(it.get("must_have", False))}
            for it in raw_items if it.get("food_id")
        }
        if not food_item_map:                      # truly nothing safe to pick (extreme allergies)
            raise HTTPException(422, "No suitable foods available for this athlete's restrictions.")

        # 7. Insert new items only (INSERT OR IGNORE won't touch checked items)
        for food_id, meta in food_item_map.items():
            food = get_food_by_id(food_id)
            if not food:
                continue
            cue = cue_label_for(food)
            conn.execute(
                """INSERT OR IGNORE INTO pantry_list_items
                   (athlete_id, week_start, food_id, name, cue_label, purchase_unit, role, meal_context, must_have)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (athlete_id, week_start, food_id, food["name"], cue,
                 food["purchase_unit"], food["role"],
                 meta["meal_context"], 1 if meta["must_have"] else 0),
            )
        conn.commit()

        # 8. Return full updated list
        return _build_list_response(athlete_id, week_start, conn)
    finally:
        conn.close()


@router.post("/add-item")
def add_item(data: PantryAddItem, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        _require_athlete(data.athlete_id, conn)

        food = get_food_by_id(data.food_id)
        if not food:
            raise HTTPException(404, f"Food not found: {data.food_id}")

        cue = cue_label_for(food)
        conn.execute(
            """INSERT OR IGNORE INTO pantry_list_items
               (athlete_id, week_start, food_id, name, cue_label, purchase_unit, role, meal_context, must_have)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (data.athlete_id, data.week_start, food["food_id"], food["name"],
             cue, food["purchase_unit"], food["role"], data.meal_context),
        )
        conn.commit()

        return _build_list_response(data.athlete_id, data.week_start, conn)
    finally:
        conn.close()
