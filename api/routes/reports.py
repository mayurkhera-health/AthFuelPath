from datetime import date as dt_date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from api.database import get_conn
from api.services import claude_ai
from api.services.report_service import build_weekly_report
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()

SCORE_BADGES = [
    (90, "Elite Fueler", "You're fueling like a D1 athlete! Keep this up for the game!"),
    (75, "Game Ready", "Great fueling today! One more snack and you'll be fully game-ready."),
    (50, "Getting There", "Good start — you're missing some key fuel. Check the suggestions below."),
    (0,  "Needs Fuel",   "Your tank is running low. Eat something now — your body needs it!"),
]


def _badge(score: int):
    for threshold, badge, msg in SCORE_BADGES:
        if score >= threshold:
            return badge, msg
    return "Needs Fuel", "Eat something now!"


@router.get("/{athlete_id}/daily")
def daily_fuel_score(athlete_id: int, date: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
        target_date = date or str(dt_date.today())

        targets_row = conn.execute(
            "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
            (athlete_id, target_date),
        ).fetchone()
        if not targets_row:
            return {"athlete_id": athlete_id, "date": target_date, "message": "No targets set. Add events first."}

        meals = conn.execute(
            "SELECT * FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at::timestamp) = %s",
            (athlete_id, target_date),
        ).fetchall()

        analysis = claude_ai.prompt2_meal_analysis(athlete, dict(targets_row), [dict(m) for m in meals], target_date)
        score = analysis.get("fuel_score", 0)
        badge, message = _badge(score)

        return {
            "athlete_id": athlete_id,
            "date": target_date,
            "fuel_score": score,
            "badge": badge,
            "teen_message": message,
            "gap_fix_suggestions": analysis.get("gap_fix_suggestions", []),
            "traffic_lights": analysis.get("traffic_lights", []),
            "lea_alert": analysis.get("lea_alert"),
            "iron_alert": analysis.get("iron_alert"),
        }
    finally:
        conn.close()


@router.get("/{athlete_id}/weekly")
def weekly_parent_report(athlete_id: int, week_start: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)

        from api.services.nutrition_analysis import get_week_start, get_week_dates
        from api.services.today_service import (
            calc_letter_grade, compute_logged_totals, compute_traffic_light,
        )

        resolved_week_start = week_start or get_week_start()
        week_dates = get_week_dates(resolved_week_start)
        week_data = {"days": []}
        week_scores = []

        for day in week_dates:
            targets_row = conn.execute(
                "SELECT * FROM daily_targets WHERE athlete_id = %s AND target_date = %s",
                (athlete_id, day),
            ).fetchone()
            meals = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at::timestamp) = %s",
                (athlete_id, day),
            ).fetchall()
            meal_list = [dict(m) for m in meals]
            week_data["days"].append({
                "date": day,
                "targets": dict(targets_row) if targets_row else None,
                "meals_logged": len(meal_list),
                "total_calories": sum(m.get("calories") or 0 for m in meal_list),
                "total_carbs_g": sum(m.get("carbs_g") or 0 for m in meal_list),
                "total_protein_g": sum(m.get("protein_g") or 0 for m in meal_list),
                "total_iron_mg": sum(m.get("iron_mg") or 0 for m in meal_list),
                "total_calcium_mg": sum(m.get("calcium_mg") or 0 for m in meal_list),
                "total_water_oz": sum(m.get("water_oz") or 0 for m in meal_list),
            })
            if targets_row and meal_list:
                logged = compute_logged_totals(meal_list)
                tl = compute_traffic_light(dict(targets_row), logged)
                week_scores.append(tl["daily_fuel_score"])

        report = claude_ai.prompt3_weekly_report(athlete, week_data)
        report["athlete_id"] = athlete_id
        report["week_start"] = resolved_week_start
        report["week_end"] = week_dates[-1]
        computed_score = (
            round(sum(week_scores) / len(week_scores))
            if week_scores else report.get("weekly_fuel_score", 0)
        )
        report["letter_grade"] = calc_letter_grade(computed_score)
        return report
    finally:
        conn.close()


@router.get("/{athlete_id}/weekly-report")
def weekly_fuel_report_v2(athlete_id: int, week_start: str = None, identity=Depends(require_session)):
    """
    Full structured weekly report for the Fuel Report tab.
    Returns grade, what_went_well, critical_gap, daily_scores, next_week, summary.
    """
    from datetime import date as _date
    from api.services.nutrition_analysis import get_week_start

    resolved = week_start or get_week_start()
    try:
        _date.fromisoformat(resolved)
    except ValueError:
        # build_weekly_report's own date.fromisoformat() call used to raise
        # this same ValueError, which the except-clause below caught and
        # returned as a 404 with the raw Python exception text as `detail`
        # — indistinguishable from a genuine "athlete not found" 404, and a
        # confusing error to show a client. Validated here instead, as a
        # clean 400 before build_weekly_report ever runs.
        raise HTTPException(status_code=400, detail=f"week_start must be an ISO 8601 date (YYYY-MM-DD), got {resolved!r}")
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        return build_weekly_report(athlete_id, resolved, conn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()


@router.get("/{athlete_id}/tournament-readiness")
def tournament_readiness(athlete_id: int, tournament_date: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)

        today = dt_date.today()
        t_date = tournament_date or str(today + timedelta(days=3))
        two_weeks_ago = str(today - timedelta(days=14))

        meals = conn.execute(
            "SELECT * FROM meal_logs WHERE athlete_id = %s AND DATE(logged_at::timestamp) >= %s",
            (athlete_id, two_weeks_ago),
        ).fetchall()
        avg_cal = sum(m["calories"] or 0 for m in meals) / max(14, 1)

        return {
            "athlete_id": athlete_id,
            "athlete_name": athlete["first_name"],
            "tournament_date": t_date,
            "avg_daily_calories_last_14_days": round(avg_cal),
            "carb_loading_protocol": {
                "day_minus_3": "Increase carbs to 6-8g/kg — pasta dinner tonight",
                "day_minus_2": "Carbs 8-10g/kg — power pasta + Greek yogurt bedtime snack",
                "day_minus_1": "MAXIMUM carb loading — 10-12g/kg — pasta dinner is THE most important meal",
                "tournament_day": "High carb breakfast 2-3hrs before first game + electrolytes MANDATORY between every game",
            },
            "disclaimer": "Fueling2Win provides educational food guidance — not medical nutrition therapy. Consult your child's physician for medical concerns.",
        }
    finally:
        conn.close()
