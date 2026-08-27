"""Cross-screen consistency: Today (build_today_view) and Meal Plan
(GET .../meal-plan/week -> generate_day_windows) must agree on day_type and
actionable window identity/order/category for the same athlete/date, since
both now derive from the same canonical engine
(window_templates.generate_windows_for_day / window_engine_v2).

Today's windows[] additionally includes informational nudges and event
markers (status in ("nudge", "event")) that generate_day_windows
intentionally excludes (it skips every is_nudge_only window) — that's an
accounted-for, Today-only presentation difference, not a business-logic
disagreement, so these tests exclude those statuses from the Today side
before comparing.
"""
import os
os.environ["DB_PATH"] = ":memory:"
os.environ["EVENT_RELATIVE_WINDOWS"] = "true"

from api.database import get_conn
from api.services.today_service import build_today_view, _ensure_window_logs_table
from api.services.meal_timing import generate_day_windows


def _make_conn():
    conn = get_conn()
    _ensure_window_logs_table(conn)
    conn.commit()
    return conn


_counter = {"n": 0}


def _seed(conn, events):
    _counter["n"] += 1
    aid = 700 + _counter["n"]
    conn.execute(
        "INSERT INTO athletes (id, first_name, gender, weight_lbs, height_ft, height_in, age) "
        "VALUES (%s, 'Sam', 'boy', 130, 5, 6, 15)",
        (aid,),
    )
    for name, etype, start, dur in events:
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
            "VALUES (%s, %s, %s, '2026-06-22', %s, %s)",
            (aid, name, etype, start, dur),
        )
    conn.commit()
    return aid


SCENARIOS = {
    "rest":              [],
    "morning_practice":  [("Practice", "practice", "08:00", 1.5)],
    "evening_practice":  [("Practice", "practice", "18:00", 1.5)],
    "game":              [("Game", "game", "14:00", 1.5)],
    "double_session":    [("AM Practice", "practice", "07:00", 1.0),
                           ("PM Practice", "practice", "18:00", 1.0)],
    "tournament":        [("Game 1", "game", "09:00", 1.0),
                           ("Game 2", "game", "12:30", 1.0)],
}


def _run(scenario_events):
    conn = _make_conn()
    aid = _seed(conn, scenario_events)

    today = build_today_view(aid, conn, today="2026-06-22")
    today_actionable = [w for w in today["windows"] if w.get("status") not in ("nudge", "event")]

    plan = generate_day_windows(aid, "2026-06-22", conn)

    conn.close()
    return today, today_actionable, plan


def test_day_type_agrees_across_all_day_types():
    for label, events in SCENARIOS.items():
        today, _, plan = _run(events)
        assert today["day_type"] == plan["day_type"], (
            f"[{label}] Today day_type={today['day_type']!r} != Meal Plan day_type={plan['day_type']!r}"
        )


def test_actionable_window_keys_and_order_agree_across_all_day_types():
    for label, events in SCENARIOS.items():
        _, today_actionable, plan = _run(events)
        today_keys = [w["slot_name"] for w in today_actionable]
        plan_keys = [w["window_key"] for w in plan["windows"]]
        assert today_keys == plan_keys, (
            f"[{label}] Today actionable keys {today_keys} != Meal Plan keys {plan_keys}"
        )


def test_category_key_agrees_per_window_when_today_provides_one():
    """On current backend main, Today only threads category_key onto a window
    conditionally (via the FUEL_GAUGE_ENABLED-gated fuel_targets block) —
    unconditional threading is a separate, already-approved, not-yet-merged
    fix (fix/today-window-content-contract, explicitly out of scope for this
    task: 'Keep this issue isolated from the approved Today branches'). So
    this only asserts agreement where Today actually provides a value today —
    it must never DISAGREE, even though it may be silently absent."""
    for label, events in SCENARIOS.items():
        _, today_actionable, plan = _run(events)
        plan_by_key = {w["window_key"]: w for w in plan["windows"]}
        for tw in today_actionable:
            pw = plan_by_key.get(tw["slot_name"])
            assert pw is not None, f"[{label}] {tw['slot_name']} on Today but missing from Meal Plan"
            if tw.get("category_key") is None:
                continue
            assert tw["category_key"] == pw["category_key"], (
                f"[{label}] {tw['slot_name']} category_key mismatch: "
                f"Today={tw['category_key']!r} Meal Plan={pw['category_key']!r}"
            )


def test_today_only_nudges_and_event_markers_are_the_sole_accounted_for_difference():
    """Every window generate_day_windows excludes must be exactly a Today-only
    nudge/event marker — never a real actionable window silently dropped."""
    for label, events in SCENARIOS.items():
        today, today_actionable, plan = _run(events)
        plan_keys = {w["window_key"] for w in plan["windows"]}
        today_actionable_keys = {w["slot_name"] for w in today_actionable}
        assert today_actionable_keys == plan_keys, f"[{label}] actionable sets differ"

        today_nudge_or_event_keys = {
            w["slot_name"] for w in today["windows"] if w.get("status") in ("nudge", "event")
        }
        # Nudge/event keys must never overlap with the real actionable set —
        # confirms the exclusion category is well-defined, not overlapping.
        assert not (today_nudge_or_event_keys & plan_keys), (
            f"[{label}] a nudge/event window key also appears as an actionable Meal Plan window"
        )
