import io
import json
import uuid
import base64
from datetime import date as dt_date, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete
from api.services import nutrition_calc
from api.services.today_service import (
    compute_logged_totals,
    compute_traffic_light,
    calc_letter_grade,
    get_positive_rows,
    get_gap_rows,
    get_athlete_streak,
    get_urgent_action,
    calculate_performance_forecast,
    build_mission_items_from_slots,
    build_today_view,
    record_window_capture,
    remove_window_capture,
)
from api.services.nutrient_resolver import queue_nutrient_resolution
from api.services.meal_timing import compute_meal_slots, generate_day_windows
from api.services.idea_catalog import IDEAS
from api.services.activity_engine import get_activity_profile

router = APIRouter()

_PHOTOS_DIR = Path("/tmp/athfuelpath_photos")
_AUDIO_DIR  = Path("/tmp/athfuelpath_audio")


async def _store_meal_photo(photo: UploadFile, athlete_id: int, slot_name: str):
    """Save full image to disk; return (photo_url, thumb_data_uri)."""
    try:
        from PIL import Image as PILImage
        content = await photo.read()
        _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{athlete_id}_{slot_name}_{uuid.uuid4().hex[:8]}.jpg"
        photo_path = _PHOTOS_DIR / filename
        photo_path.write_bytes(content)
        img = PILImage.open(io.BytesIO(content)).convert("RGB")
        img.thumbnail((120, 120))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode()
        return str(photo_path), f"data:image/jpeg;base64,{thumb_b64}"
    except Exception:
        return None, None


async def _store_meal_audio(audio: UploadFile, athlete_id: int, slot_name: str) -> str | None:
    """Save voice clip to disk; return path string."""
    try:
        content = await audio.read()
        _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        raw_name = audio.filename or "clip.webm"
        ext = raw_name.rsplit(".", 1)[-1] if "." in raw_name else "webm"
        filename = f"{athlete_id}_{slot_name}_{uuid.uuid4().hex[:8]}.{ext}"
        audio_path = _AUDIO_DIR / filename
        audio_path.write_bytes(content)
        return str(audio_path)
    except Exception:
        return None


@router.get("/{athlete_id}/meal-plan")
def get_day_timeline(athlete_id: int, date: str = None, v2: bool = False, identity=Depends(require_session)):
    """Day Timeline for the Meal Plan tab. Single engine: wraps compute_meal_slots."""
    plan_date = date or str(dt_date.today())
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found")

        skeleton = generate_day_windows(athlete_id, plan_date, conn, force_v2=v2)

        rows = conn.execute(
            "SELECT id, window_key, item_text, added_by, recipe_json "
            "FROM meal_plan_selections WHERE athlete_id = %s AND plan_date = %s",
            (athlete_id, plan_date),
        ).fetchall()
        by_key: dict = {}
        for row in rows:
            r = dict(row)
            item = {"id": r["id"], "text": r["item_text"], "added_by": r["added_by"]}
            if r.get("recipe_json"):
                try:
                    item["recipe"] = json.loads(r["recipe_json"])
                except json.JSONDecodeError:
                    pass
            by_key.setdefault(r["window_key"], []).append(item)

        enriched = [
            {
                **w,
                "items": by_key.get(w["window_key"], []),
                "ideas": IDEAS.get(w.get("category", ""), IDEAS.get(w["category_key"], [])),
            }
            for w in skeleton["windows"]
        ]
        return {**skeleton, "windows": enriched}
    finally:
        conn.close()


@router.get("/{athlete_id}/today")
def get_today_view(
    athlete_id: int, date: str = Query(None), v2: bool = False, now: str = Query(None),
    identity=Depends(require_session),
):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        from datetime import datetime as _dt
        client_now = None
        if now:
            try:
                client_now = _dt.fromisoformat(now)
            except ValueError:
                client_now = None
        data = build_today_view(athlete_id, conn, today=date, force_v2=v2, now=client_now)
        if data is None:
            raise HTTPException(404, "Athlete not found.")
        return data
    finally:
        conn.close()


@router.patch("/{athlete_id}/dismiss-wind-down")
def dismiss_wind_down(athlete_id: int, identity=Depends(require_session)):
    """Permanently suppress the Evening Wind-Down card (day_layout.py, behind
    DAY_LAYOUT_V2) for this athlete — mobile's 'Skip forever' action. Mobile has
    called this route since it shipped the Wind-Down card UI, but the route
    never existed server-side; the dismissal silently never persisted."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        conn.execute("UPDATE athletes SET wind_down_dismissed = 1 WHERE id = %s", (athlete_id,))
        conn.commit()
        return {"wind_down_dismissed": True}
    finally:
        conn.close()


@router.post("/{athlete_id}/windows/{slot_name}/capture")
async def capture_window(
    athlete_id: int,
    slot_name: str,
    method: str = Form(...),
    text: str | None = Form(None),
    photo: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    log_date: str | None = Form(None),
    identity=Depends(require_session),
):
    """
    Completes a fuel window — photo, voice, or text.
    All three paths: instant done, background nutrient resolution.
    """
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        photo_url = thumb_url = audio_url = None
        if method == "photo" and photo is not None:
            photo_url, thumb_url = await _store_meal_photo(photo, athlete_id, slot_name)
        if method == "voice" and audio is not None:
            audio_url = await _store_meal_audio(audio, athlete_id, slot_name)

        log_id = record_window_capture(
            athlete_id=athlete_id,
            window_id=slot_name,
            method=method,
            text=text,
            photo_url=photo_url,
            thumb_url=thumb_url,
            audio_url=audio_url,
            conn=conn,
            log_date=log_date,
        )
        queue_nutrient_resolution(log_id, conn)

        data = build_today_view(athlete_id, conn, today=log_date)
        if data is None:
            raise HTTPException(404, "Athlete not found.")
        return data
    finally:
        conn.close()


@router.delete("/{athlete_id}/windows/{slot_name}/capture")
def uncapture_window(
    athlete_id: int,
    slot_name: str,
    log_date: str | None = Query(None),
    identity=Depends(require_session),
):
    """Un-confirm a fuel window (reverse a mis-tap). Mirrors the capture endpoint:
    removes the confirmation for (athlete, slot, local date) and returns the
    refreshed Today view so the gauges decrement in one round-trip. Idempotent —
    un-confirming an already-unconfirmed window is a no-op, not an error."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        remove_window_capture(
            athlete_id=athlete_id,
            window_id=slot_name,
            conn=conn,
            log_date=log_date,
        )
        data = build_today_view(athlete_id, conn, today=log_date)
        if data is None:
            raise HTTPException(404, "Athlete not found.")
        return data
    finally:
        conn.close()


@router.get("/{athlete_id}/daily-summary")
def get_daily_summary(athlete_id: int, date: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
        target_date = date or str(dt_date.today())

        events = [dict(e) for e in conn.execute(
            "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time",
            (athlete_id, target_date),
        ).fetchall()]
        event_type = events[0]["event_type"] if events else "rest"

        targets_row = conn.execute(
            "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
            (athlete_id, target_date),
        ).fetchone()
        targets = dict(targets_row) if targets_row else nutrition_calc.calc_daily_targets(athlete, event_type)

        meal_rows = conn.execute(
            "SELECT * FROM meal_logs WHERE athlete_id = %s AND logged_at::date = %s ORDER BY logged_at",
            (athlete_id, target_date),
        ).fetchall()
        meal_logs = [dict(m) for m in meal_rows]

        water_row = conn.execute(
            "SELECT cups FROM water_logs WHERE athlete_id = %s AND log_date = %s",
            (athlete_id, target_date),
        ).fetchone()
        water_cups = water_row["cups"] if water_row else 0

        logged = compute_logged_totals(meal_logs)
        logged["water_oz"] = round((logged.get("water_oz") or 0) + water_cups * 8, 1)

        tl = compute_traffic_light(targets, logged)
        score = tl["daily_fuel_score"]
        gender = athlete.get("gender", "boy")

        tomorrow = (dt_date.fromisoformat(target_date) + timedelta(days=1)).isoformat()
        tomorrow_row = conn.execute(
            "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time LIMIT 1",
            (athlete_id, tomorrow),
        ).fetchone()

        # Build mission items from the same slot definitions used by the Meal Plan tab
        start_time     = events[0]["start_time"]     if events else None
        duration_hours = events[0]["duration_hours"] if events else None
        slot_defs = compute_meal_slots(event_type, start_time, duration_hours)
        plan_rows = conn.execute(
            "SELECT slot_name, logged FROM meal_plans WHERE athlete_id = %s AND plan_date = %s",
            (athlete_id, target_date),
        ).fetchall()
        logged_slots = {r["slot_name"]: bool(r["logged"]) for r in plan_rows}

        wt_kg     = nutrition_calc.lbs_to_kg(athlete["weight_lbs"]) if athlete.get("weight_lbs") else None
        # Derive is_sc_day via the same normalization chain calc_daily_targets uses,
        # so the window-distribution protein floor matches the computed targets.
        # (Raw string match misses the "strength/conditioning" alias → wrong floor.)
        _sc_norm = nutrition_calc.normalize_event_type(event_type) if event_type else "rest"
        is_sc_day = get_activity_profile(nutrition_calc._to_activity_type(_sc_norm), None, 0)["is_sc_day"]
        duration_min = round((duration_hours or 0) * 60)
        mission_items = build_mission_items_from_slots(
            slot_defs, logged_slots, targets,
            wt_kg=wt_kg, is_sc_day=is_sc_day, duration_min=duration_min,
        )

        # Parent-only: collect any per-window ratio flags (never shown to athlete UI)
        window_ratio_flags = [
            {"slot": m["meal_type"], "flag": m["ratio_flag"]}
            for m in mission_items
            if m.get("ratio_flag")
        ]

        return {
            "athlete": {
                "first_name":        athlete["first_name"],
                "last_name":         athlete.get("last_name"),
                "gender":            gender,
                "position":          athlete.get("position"),
                "competition_level": athlete.get("competition_level"),
                "jersey_number":     athlete.get("jersey_number"),
                "team_name":         athlete.get("team_name"),
                "dietary_restrictions": athlete.get("dietary_restrictions"),
                "allergies":         athlete.get("allergies"),
            },
            "date": target_date,
            "event_type": event_type,
            "events": events,
            "targets": targets,
            "logged": logged,
            "traffic_light": tl,
            "meal_logs": meal_logs,
            "letter_grade": calc_letter_grade(score),
            "positive_rows": get_positive_rows(tl, event_type, gender),
            "gap_rows": get_gap_rows(tl, gender, event_type),
            "urgent_action": get_urgent_action(events, tl, meal_logs),
            "streak": get_athlete_streak(athlete_id, conn),
            "tomorrow_event": dict(tomorrow_row) if tomorrow_row else None,
            "water_cups": water_cups,
            "lea_alert": targets.get("lea_alert", False),
            "performance_forecast": calculate_performance_forecast(tl),
            "mission_items": mission_items,
            "window_ratio_flags": window_ratio_flags,
        }
    finally:
        conn.close()


@router.get("/{athlete_id}/weekly-summary")
def get_weekly_summary(athlete_id: int, week_start: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
        gender = athlete.get("gender", "boy")

        from api.services.nutrition_analysis import (
            get_week_start, get_week_dates, build_heatmap,
            calculate_weekly_traffic_light, rank_weekly_gaps, build_wins_list,
        )

        resolved_week_start = week_start or get_week_start()
        week_dates = get_week_dates(resolved_week_start)
        today_str = str(dt_date.today())
        DAY_ABBR = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

        week = []
        for i, date_str in enumerate(week_dates):
            targets_row = conn.execute(
                "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
                (athlete_id, date_str),
            ).fetchone()
            event_row = conn.execute(
                "SELECT event_type FROM events WHERE athlete_id = %s AND event_date = %s LIMIT 1",
                (athlete_id, date_str),
            ).fetchone()
            meal_rows = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = %s AND logged_at::date = %s",
                (athlete_id, date_str),
            ).fetchall()
            meal_logs = [dict(m) for m in meal_rows]

            score = None
            if targets_row and meal_logs:
                water_row = conn.execute(
                    "SELECT cups FROM water_logs WHERE athlete_id = %s AND log_date = %s",
                    (athlete_id, date_str),
                ).fetchone()
                water_cups = water_row["cups"] if water_row else 0
                logged = compute_logged_totals(meal_logs)
                logged["water_oz"] = round((logged.get("water_oz") or 0) + water_cups * 8, 1)
                tl = compute_traffic_light(dict(targets_row), logged)
                score = tl["daily_fuel_score"]

            week.append({
                "date": date_str,
                "day_abbr": DAY_ABBR[i],
                "day_num": dt_date.fromisoformat(date_str).day,
                "score": score,
                "event_type": event_row["event_type"] if event_row else None,
                "is_today": date_str == today_str,
            })

        scores = [d["score"] for d in week if d["score"] is not None]
        week_fuel_score = round(sum(scores) / len(scores)) if scores else 0
        days_logged = len(scores)

        heatmap = build_heatmap(athlete_id, week_dates, conn)
        weekly_tl = calculate_weekly_traffic_light(athlete_id, week_dates, conn)
        ranked_gaps = rank_weekly_gaps(weekly_tl, gender)
        streak = get_athlete_streak(athlete_id, conn)
        wins = build_wins_list(weekly_tl, streak, athlete["first_name"])

        prev_start_date = dt_date.fromisoformat(resolved_week_start) - timedelta(days=7)
        prev_dates = [(prev_start_date + timedelta(days=i)).isoformat() for i in range(7)]
        prev_scores = []
        for date_str in prev_dates:
            t_row = conn.execute(
                "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
                (athlete_id, date_str),
            ).fetchone()
            m_rows = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = %s AND logged_at::date = %s",
                (athlete_id, date_str),
            ).fetchall()
            if t_row and m_rows:
                lg = compute_logged_totals([dict(m) for m in m_rows])
                tl = compute_traffic_light(dict(t_row), lg)
                prev_scores.append(tl["daily_fuel_score"])
        prev_week_score = round(sum(prev_scores) / len(prev_scores)) if prev_scores else None

        return {
            "week_start": resolved_week_start,
            "week_end": week_dates[-1],
            "days_logged": days_logged,
            "week_fuel_score": week_fuel_score,
            "prev_week_score": prev_week_score,
            "days": week,
            "heatmap": heatmap,
            "weekly_traffic_light": weekly_tl,
            "ranked_gaps": ranked_gaps,
            "wins": wins,
            "streak": streak,
            "letter_grade": calc_letter_grade(week_fuel_score),
        }
    finally:
        conn.close()
