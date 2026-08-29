from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date, timedelta
from api.models import MealPlanSlotUpdate, MealPlanLogSlot, MealPlanGenerateRequest
from api.database import get_conn
from api.services import recipe_db, claude_ai
from api.services.meal_timing import compute_meal_slots
from api.services.session_auth import require_session, assert_owns_athlete
from api.utils.week import get_week_start

router = APIRouter()

DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _get_week_sunday(date_str: str) -> date:
    return get_week_start(date.fromisoformat(date_str))


def _build_week(athlete_id: int, week_start: date, conn) -> list:
    days = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        date_str = day_date.isoformat()

        # Fetch ALL events for this day to detect double-day
        event_rows = conn.execute(
            "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time",
            (athlete_id, date_str),
        ).fetchall()
        events = [dict(r) for r in event_rows]

        event_type   = events[0]["event_type"] if events else "rest"
        event_name   = events[0]["event_name"] if events else None
        start_time   = events[0]["start_time"] if events else None
        duration_h   = events[0]["duration_hours"] if events else None
        double_day   = len(events) >= 2
        second_start = events[1]["start_time"] if double_day else None

        # Calorie target
        target_row = conn.execute(
            "SELECT total_calories FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
            (athlete_id, date_str),
        ).fetchone()
        calorie_target = dict(target_row)["total_calories"] if target_row else None

        # Filled slots from DB
        rows = conn.execute(
            "SELECT * FROM meal_plans WHERE athlete_id = %s AND plan_date = %s",
            (athlete_id, date_str),
        ).fetchall()
        filled = {dict(r)["slot_name"]: dict(r) for r in rows}

        # Compute dynamic slot list
        slot_defs = compute_meal_slots(
            event_type, start_time, duration_h,
            double_day=double_day, second_start_time=second_start,
        )

        slots = []
        planned_calories = 0
        for sd in slot_defs:
            sname = sd["slot_name"]
            f = filled.get(sname)
            slot = {
                "slot_name":       sname,
                "display_label":   sd["display_label"],
                "eat_by_time":     sd["eat_by_time"],
                "time_note":       sd["time_note"],
                "tags":            sd["tags"],
                "icon":            sd["icon"],
                "is_hydration":    sd["is_hydration"],
                "is_merged":       sd["is_merged"],
                "note":            sd["note"],
                "double_day_alert": sd.get("double_day_alert", False),
                "recipe_category": sd["recipe_category"],
                "recipe_id":       f["recipe_id"]   if f else None,
                "recipe_name":     f["recipe_name"] if f else None,
                "calories":        f["calories"]    if f else None,
                "carbs_g":         f["carbs_g"]     if f else None,
                "protein_g":       f["protein_g"]   if f else None,
                "fat_g":           f["fat_g"]       if f else None,
                "is_ai_generated": bool(f["is_ai_generated"]) if f else False,
                "logged":          bool(f["logged"]) if f else False,
            }
            if f and f["calories"]:
                planned_calories += f["calories"]
            slots.append(slot)

        days.append({
            "date":             date_str,
            "day_label":        DAY_LABELS[i],
            "event_type":       event_type,
            "event_name":       event_name,
            "calorie_target":   calorie_target,
            "planned_calories": round(planned_calories),
            "double_day":       double_day,
            "slots":            slots,
        })
    return days


@router.get("/{athlete_id}")
def get_meal_plan(athlete_id: int, week_start: str = Query(None), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")

        if week_start:
            sunday = _get_week_sunday(week_start)
        else:
            sunday = get_week_start(date.today())

        days = _build_week(athlete_id, sunday, conn)
        return {"athlete_id": athlete_id, "week_start": sunday.isoformat(), "days": days}
    finally:
        conn.close()


@router.put("/{athlete_id}/slot")
def set_slot(athlete_id: int, data: MealPlanSlotUpdate, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")

        recipe = recipe_db.get_recipe_by_id(data.recipe_id)
        if not recipe:
            raise HTTPException(404, f"Recipe {data.recipe_id} not found.")

        m = recipe["macros"]
        conn.execute(
            """INSERT INTO meal_plans
               (athlete_id, plan_date, slot_name, recipe_id, recipe_name,
                calories, carbs_g, protein_g, fat_g, is_ai_generated, logged)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0)
               ON CONFLICT(athlete_id, plan_date, slot_name)
               DO UPDATE SET recipe_id=excluded.recipe_id, recipe_name=excluded.recipe_name,
                 calories=excluded.calories, carbs_g=excluded.carbs_g,
                 protein_g=excluded.protein_g, fat_g=excluded.fat_g,
                 is_ai_generated=0, logged=0""",
            (athlete_id, data.plan_date, data.slot_name, data.recipe_id,
             recipe["name"], m["calories"], m["carbs_g"], m["protein_g"], m["fat_g"]),
        )
        conn.commit()
        return {
            "slot_name": data.slot_name, "recipe_id": data.recipe_id,
            "recipe_name": recipe["name"], "calories": m["calories"],
            "carbs_g": m["carbs_g"], "protein_g": m["protein_g"], "fat_g": m["fat_g"],
            "is_ai_generated": False, "logged": False,
        }
    finally:
        conn.close()


@router.delete("/{athlete_id}/slot")
def clear_slot(athlete_id: int, plan_date: str = Query(...), slot_name: str = Query(...), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        conn.execute(
            "DELETE FROM meal_plans WHERE athlete_id = %s AND plan_date = %s AND slot_name = %s",
            (athlete_id, plan_date, slot_name),
        )
        conn.commit()
        return {"cleared": True}
    finally:
        conn.close()


@router.post("/{athlete_id}/log-slot")
def log_slot(athlete_id: int, data: MealPlanLogSlot, identity=Depends(require_session)):
    """Claiming the slot (UPDATE ... WHERE logged=0 RETURNING) and inserting
    the meal_logs row happen in the SAME uncommitted transaction — Postgres's
    own row-level locking on the UPDATE serializes two concurrent calls for
    the same slot, so only one can ever receive a returned row (Security
    Item 5, F2: the prior SELECT-then-INSERT-then-UPDATE let two concurrent
    requests both read logged=0 and both insert a meal_logs row)."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        exists = conn.execute(
            "SELECT 1 FROM meal_plans WHERE athlete_id = %s AND plan_date = %s AND slot_name = %s",
            (athlete_id, data.plan_date, data.slot_name),
        ).fetchone()
        if not exists:
            raise HTTPException(404, "Planned slot not found.")

        claimed = conn.execute(
            """UPDATE meal_plans SET logged = 1
               WHERE athlete_id = %s AND plan_date = %s AND slot_name = %s AND logged = 0
               RETURNING recipe_name, calories, carbs_g, protein_g, fat_g""",
            (athlete_id, data.plan_date, data.slot_name),
        ).fetchone()
        if not claimed:
            raise HTTPException(400, "This meal has already been logged.")
        r = dict(claimed)

        # If this fails, the transaction is never committed, so the logged=1
        # claim above rolls back with it — closing() without commit()
        # implicitly rolls back, but roll back explicitly so the failure
        # mode doesn't depend on that implicit behavior.
        try:
            inserted = conn.execute(
                """INSERT INTO meal_logs
                   (athlete_id, log_method, description, calories, carbs_g, protein_g, fat_g)
                   VALUES (%s, 'meal-plan', %s, %s, %s, %s, %s)
                   RETURNING id""",
                (athlete_id, r["recipe_name"], r["calories"], r["carbs_g"], r["protein_g"], r["fat_g"]),
            )
            meal_log_id = inserted.fetchone()["id"]
        except Exception:
            conn.rollback()
            raise

        conn.commit()
        return {"logged": True, "meal_log_id": meal_log_id}
    finally:
        conn.close()


@router.post("/generate")
def generate_plan(data: MealPlanGenerateRequest, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        athlete_row = conn.execute("SELECT * FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone()
        if not athlete_row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(athlete_row)

        sunday = _get_week_sunday(data.week_start)

        # Build week schedule context for Claude
        week_schedule = []
        for i in range(7):
            day_date = sunday + timedelta(days=i)
            date_str = day_date.isoformat()
            event = conn.execute(
                "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time LIMIT 1",
                (data.athlete_id, date_str),
            ).fetchone()
            event_type = dict(event)["event_type"] if event else "rest"
            target_row = conn.execute(
                "SELECT total_calories FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
                (data.athlete_id, date_str),
            ).fetchone()
            calorie_target = dict(target_row)["total_calories"] if target_row else 2000

            slot_defs = compute_meal_slots(event_type, None, None)
            slots = [{"slot_name": sd["slot_name"], "recipe_category": sd["recipe_category"]} for sd in slot_defs]

            week_schedule.append({
                "date": date_str,
                "day_label": DAY_LABELS[i],
                "event_type": event_type,
                "slots": slots,
                "calorie_target": calorie_target,
            })

        # Filter recipes by athlete restrictions
        athlete_allergens = [a.strip().lower() for a in (athlete.get("allergies") or "").split(",") if a.strip()]
        athlete_diets = [d.strip().lower() for d in (athlete.get("dietary_restrictions") or "").split(",") if d.strip()]
        safe_recipes = [
            r for r in recipe_db.RECIPES
            if not any(a in [x.lower() for x in r["allergens"]] for a in athlete_allergens)
        ]

        # Call Claude AI
        ai_result = claude_ai.prompt6_weekly_meal_plan(athlete, week_schedule, safe_recipes)
        plan = ai_result.get("plan", {})

        # Bulk upsert
        for date_str, slot_map in plan.items():
            for slot_name, recipe_id in slot_map.items():
                if not recipe_id:
                    continue
                recipe = recipe_db.get_recipe_by_id(recipe_id)
                if not recipe:
                    continue
                # Skip if slot occupied and overwrite_existing=False
                if not data.overwrite_existing:
                    existing = conn.execute(
                        "SELECT id FROM meal_plans WHERE athlete_id = %s AND plan_date = %s AND slot_name = %s",
                        (data.athlete_id, date_str, slot_name),
                    ).fetchone()
                    if existing:
                        continue
                m = recipe["macros"]
                conn.execute(
                    """INSERT INTO meal_plans
                       (athlete_id, plan_date, slot_name, recipe_id, recipe_name,
                        calories, carbs_g, protein_g, fat_g, is_ai_generated, logged)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0)
                       ON CONFLICT(athlete_id, plan_date, slot_name)
                       DO UPDATE SET recipe_id=excluded.recipe_id, recipe_name=excluded.recipe_name,
                         calories=excluded.calories, carbs_g=excluded.carbs_g,
                         protein_g=excluded.protein_g, fat_g=excluded.fat_g,
                         is_ai_generated=1, logged=0""",
                    (data.athlete_id, date_str, slot_name, recipe_id,
                     recipe["name"], m["calories"], m["carbs_g"], m["protein_g"], m["fat_g"]),
                )
        conn.commit()

        # Return full week
        days = _build_week(data.athlete_id, sunday, conn)
        return {
            "athlete_id": data.athlete_id,
            "week_start": sunday.isoformat(),
            "days": days,
            "ai_reasoning": ai_result.get("reasoning", ""),
        }
    finally:
        conn.close()
