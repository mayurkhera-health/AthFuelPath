from api.database import get_conn
from api.services.today_service import (
    calculate_performance_forecast,
    get_mission_items,
    assign_window_status,
    build_today_view,
    record_window_capture,
    _ensure_window_logs_table,
)


def make_tl(calories=80, carbs=80, protein=80, iron=80, calcium=80, water=80):
    """Build a minimal traffic_light dict for testing."""
    def cell(pct):
        return {"pct_met": pct, "logged": 0, "target": 100, "gap": max(0, 100 - pct), "status": "met" if pct >= 80 else "low" if pct >= 50 else "critical"}
    return {
        "calories":   cell(calories),
        "carbs_g":    cell(carbs),
        "protein_g":  cell(protein),
        "iron_mg":    cell(iron),
        "calcium_mg": cell(calcium),
        "water_oz":   cell(water),
        "daily_fuel_score": 75,
    }


# ── calculate_performance_forecast ───────────────────────────────────────────

def test_forecast_returns_four_keys():
    result = calculate_performance_forecast(make_tl())
    assert set(result.keys()) == {"sprint_capacity", "energy_reserves", "second_half_power", "mental_focus"}


def test_forecast_all_100_gives_100():
    result = calculate_performance_forecast(make_tl(100, 100, 100, 100, 100, 100))
    assert result["sprint_capacity"] == 100
    assert result["energy_reserves"] == 100
    assert result["second_half_power"] == 100
    assert result["mental_focus"] == 100


def test_forecast_all_zero_gives_zero():
    result = calculate_performance_forecast(make_tl(0, 0, 0, 0, 0, 0))
    assert result["sprint_capacity"] == 0
    assert result["energy_reserves"] == 0
    assert result["second_half_power"] == 0
    assert result["mental_focus"] == 0


def test_forecast_sprint_capacity_formula():
    # carbs=100, iron=0, protein=0 → 100*0.40 + 0*0.35 + 0*0.25 = 40
    result = calculate_performance_forecast(make_tl(calories=0, carbs=100, protein=0, iron=0, water=0))
    assert result["sprint_capacity"] == 40


def test_forecast_energy_reserves_formula():
    # calories=100, carbs=0 → 100*0.60 + 0*0.40 = 60
    result = calculate_performance_forecast(make_tl(calories=100, carbs=0, protein=0, iron=0, water=0))
    assert result["energy_reserves"] == 60


def test_forecast_second_half_power_formula():
    # iron=100, carbs=0, water=0 → 100*0.50 = 50
    result = calculate_performance_forecast(make_tl(calories=0, carbs=0, protein=0, iron=100, water=0))
    assert result["second_half_power"] == 50


def test_forecast_mental_focus_formula():
    # calories=0, water=100, protein=0 → 100*0.35 = 35
    result = calculate_performance_forecast(make_tl(calories=0, carbs=0, protein=0, iron=0, water=100))
    assert result["mental_focus"] == 35


def test_forecast_caps_at_100():
    # Each pct_met is capped at 100 before weighting
    tl = make_tl(100, 100, 100, 100, 100, 100)
    for k in tl:
        if isinstance(tl[k], dict):
            tl[k]["pct_met"] = 150  # simulate over-logging
    result = calculate_performance_forecast(tl)
    assert result["sprint_capacity"] == 100
    assert result["energy_reserves"] == 100
    assert result["second_half_power"] == 100
    assert result["mental_focus"] == 100


def test_get_mission_items_stub_returns_list():
    result = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    assert isinstance(result, list)


# ── get_mission_items ─────────────────────────────────────────────────────────

def test_mission_items_always_returns_5():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    assert len(items) == 5


def test_mission_items_all_have_required_keys():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    for item in items:
        assert "label" in item
        assert "sub" in item
        assert "time" in item
        assert "state" in item
        assert "tag" in item
        assert "item_type" in item


def test_mission_items_state_values_are_valid():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    valid_states = {"done", "urgent", "critical", "pending"}
    for item in items:
        assert item["state"] in valid_states, f"Invalid state: {item['state']}"


def test_mission_items_tag_values_are_valid():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    valid_tags = {"DONE", "NOW", "FIX THIS", "UPCOMING"}
    for item in items:
        assert item["tag"] in valid_tags, f"Invalid tag: {item['tag']}"


def test_mission_items_rest_day():
    items = get_mission_items("rest", [], make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "iron_lunch" in types
    assert "calcium" in types
    assert "hydration" in types


def test_mission_items_game_day_has_pregame_snack():
    events = [{"start_time": "14:00", "duration_hours": 1.5, "event_type": "game"}]
    items = get_mission_items("game", events, make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "pregame_snack" in types


def test_mission_items_game_day_has_recovery():
    events = [{"start_time": "14:00", "duration_hours": 1.5, "event_type": "game"}]
    items = get_mission_items("game", events, make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "recovery" in types


def test_mission_items_iron_critical_for_girls():
    tl = make_tl(iron=30)
    items = get_mission_items("rest", [], tl, [], {}, 0, "girl")
    iron_items = [i for i in items if i["item_type"] == "iron_lunch"]
    assert len(iron_items) >= 1
    assert iron_items[0]["state"] == "urgent"


def test_mission_items_iron_not_flagged_for_boys():
    tl = make_tl(iron=30)
    items = get_mission_items("rest", [], tl, [], {}, 0, "boy")
    iron_items = [i for i in items if i.get("state") == "critical"]
    # boys don't get critical iron state
    assert all(i["item_type"] != "iron_lunch" for i in iron_items)


def test_mission_items_hydration_urgent_when_low():
    tl = make_tl(water=30)
    items = get_mission_items("rest", [], tl, [], {"hydration_oz_min": 80}, 1, "girl")
    hydration = next(i for i in items if i["item_type"] == "hydration")
    assert hydration["state"] in ("urgent", "critical")


def test_mission_items_practice_day():
    events = [{"start_time": "16:00", "duration_hours": 1.5, "event_type": "practice"}]
    items = get_mission_items("practice", events, make_tl(), [], {}, 0, "girl")
    types = [i["item_type"] for i in items]
    assert "pre_practice_snack" in types
    assert "protein_recovery" in types


# ── Window status invariant tests ─────────────────────────────────────────────

def test_windows_not_done_by_time():
    """
    INVARIANT: A window is 'done' only if its DB row is logged.
    Time alone never marks a window done — even past-due windows stay
    'next' or 'upcoming' until the athlete actually logs them.
    """
    windows = [
        {"slot_name": "breakfast",         "logged": False, "eat_by_time": "8:30 AM"},
        {"slot_name": "mid-morning-snack", "logged": False, "eat_by_time": "11:00 AM"},
        {"slot_name": "lunch",             "logged": False, "eat_by_time": "1:30 PM"},
        {"slot_name": "afternoon-snack",   "logged": False, "eat_by_time": "4:00 PM"},
        {"slot_name": "dinner",            "logged": False, "eat_by_time": "7:00 PM"},
    ]
    result = assign_window_status(windows)
    done_windows = [w for w in result if w["status"] == "done"]
    next_windows = [w for w in result if w["status"] == "next"]
    upcoming_windows = [w for w in result if w["status"] == "upcoming"]
    assert len(done_windows) == 0, f"Expected 0 done windows, got {[w['slot_name'] for w in done_windows]}"
    assert len(next_windows) == 1
    assert len(upcoming_windows) == 4


def test_windows_done_only_by_logged_flag():
    """Only windows with logged=True are marked done."""
    windows = [
        {"slot_name": "breakfast",         "logged": True,  "eat_by_time": "8:30 AM"},
        {"slot_name": "mid-morning-snack", "logged": False, "eat_by_time": "11:00 AM"},
        {"slot_name": "lunch",             "logged": False, "eat_by_time": "1:30 PM"},
        {"slot_name": "afternoon-snack",   "logged": False, "eat_by_time": "4:00 PM"},
    ]
    result = assign_window_status(windows)
    assert result[0]["status"] == "done"
    assert result[1]["status"] == "next"
    assert result[2]["status"] == "upcoming"
    assert result[3]["status"] == "upcoming"


def _make_test_conn():
    """Real (shared) Postgres connection. window_logs/meal_plans already exist
    via db/postgres/001_baseline.sql (applied once per test session, TRUNCATEd
    once per module by conftest's module-scoped _fresh_db fixture), so unlike
    the old private in-memory SQLite DB, no ad hoc table creation is needed —
    just make sure window_logs is present (a harmless no-op there)."""
    conn = get_conn()
    _ensure_window_logs_table(conn)
    conn.commit()
    return conn


def _make_today_conn():
    """Every table build_today_view + get_streak read from (athletes, events,
    confirmations, report_config, window_logs, meal_plans) already exists via
    the baseline schema — same real connection as _make_test_conn()."""
    return _make_test_conn()


def test_has_schedule_false_with_zero_events():
    """A newly-claimed athlete with no events ever → has_schedule = False
    (distinguishes 'no schedule set up' from a genuine rest day)."""
    conn = _make_today_conn()
    conn.execute("INSERT INTO athletes (id, first_name, gender, weight_lbs, height_ft, height_in, age) VALUES (1, 'Ryan', 'boy', 120, 5, 4, 14)")
    conn.commit()

    view = build_today_view(1, conn, today="2026-06-22")
    assert view is not None
    assert view["has_schedule"] is False
    conn.close()


def test_has_schedule_true_with_one_event():
    """An athlete with at least one event (any date, any type) → has_schedule = True."""
    conn = _make_today_conn()
    conn.execute("INSERT INTO athletes (id, first_name, gender, weight_lbs, height_ft, height_in, age) VALUES (2, 'Ryan', 'boy', 120, 5, 4, 14)")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (2, 'Practice', 'practice', '2026-07-01', '16:00', 1.5)"
    )
    conn.commit()

    view = build_today_view(2, conn, today="2026-06-22")
    assert view is not None
    assert view["has_schedule"] is True
    conn.close()


def test_tappable_windows_carry_open_close_time_24h():
    """Tappable windows expose open_time/close_time in 24h HH:MM so the client
    can gate per-window confirm by now vs open/close. eat_by_time unchanged."""
    import re
    conn = _make_today_conn()
    conn.execute("INSERT INTO athletes (id, first_name, gender, weight_lbs, height_ft, height_in, age) VALUES (3, 'Ana', 'girl', 110, 5, 2, 14)")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (3, 'Practice', 'practice', '2026-06-22', '16:00', 1.5)"
    )
    conn.commit()

    view = build_today_view(3, conn, today="2026-06-22")
    tappable = [w for w in view["windows"] if w.get("status") != "nudge"]
    assert tappable, "expected tappable windows on an event day"
    hhmm = re.compile(r"^\d{2}:\d{2}$")
    for w in tappable:
        assert "open_time" in w and "close_time" in w, w.keys()
        assert hhmm.match(w["open_time"]), w["open_time"]
        assert hhmm.match(w["close_time"]), w["close_time"]
        # display string is untouched
        assert "–" in w["eat_by_time"] or "AM" in w["eat_by_time"] or "PM" in w["eat_by_time"]
    conn.close()


def test_tappable_windows_carry_purpose_load_levels_and_food_ideas():
    """Every tappable window on an event day returns a non-empty purpose
    sentence, a load_levels dict with HIGH/MODERATE/LIGHT per macro, and
    up to 4 deterministic food ideas — the data the redesigned Today
    fueling-window card renders (spec: redesign/simplify-v2)."""
    conn = _make_today_conn()
    conn.execute("INSERT INTO athletes (id, first_name, gender, weight_lbs, height_ft, height_in, age) VALUES (4, 'Sam', 'boy', 130, 5, 6, 15)")
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (4, 'Practice', 'practice', '2026-06-22', '16:00', 1.5)"
    )
    conn.commit()

    view = build_today_view(4, conn, today="2026-06-22")
    tappable = [w for w in view["windows"] if w.get("status") not in ("nudge", "event")]
    assert tappable, "expected tappable windows on an event day"
    for w in tappable:
        assert isinstance(w.get("purpose"), str) and w["purpose"], f"{w['slot_name']} missing purpose"
        levels = w.get("load_levels")
        assert isinstance(levels, dict)
        assert set(levels.keys()) == {"carbs", "protein", "fats"}
        for v in levels.values():
            assert v in ("HIGH", "MODERATE", "LIGHT")
        ideas = w.get("food_ideas")
        assert isinstance(ideas, list)
        assert len(ideas) <= 4
    conn.close()


def test_food_ideas_are_nonempty_and_sourced_from_the_canonical_catalog():
    """food_ideas must never be empty for a real tappable window (proves every
    category/category_key the live engines can emit has an idea_catalog.IDEAS
    entry — a category with no mapping would silently produce []), and every
    idea string returned must be a member of idea_catalog.IDEAS — proves Today
    is reading the same catalog the /meal-plan endpoint uses, not a second,
    independently-hardcoded list. Covers rest, single-session, and
    multi-session day types so every category the engine can produce for a
    tappable window gets exercised."""
    from api.services.idea_catalog import IDEAS

    all_catalog_ideas = {idea for ideas in IDEAS.values() for idea in ideas}

    scenarios = {
        "rest":            [],
        "practice_evening": [("Practice", "practice", "18:00", 1.5)],
        "practice_morning": [("Practice", "practice", "08:00", 1.5)],
        "afternoon_game":   [("Game", "game", "14:00", 1.5)],
        "double_training":  [("AM Practice", "practice", "07:00", 1.0),
                              ("PM Practice", "practice", "18:00", 1.0)],
        "tournament":       [("Game 1", "game", "09:00", 1.0),
                              ("Game 2", "game", "12:30", 1.0)],
    }

    athlete_id = 500
    for i, (label, events) in enumerate(scenarios.items()):
        conn = _make_today_conn()
        conn.execute(
            "INSERT INTO athletes (id, first_name, gender, weight_lbs, height_ft, height_in, age) "
            "VALUES (%s, 'Sam', 'boy', 130, 5, 6, 15)",
            (athlete_id + i,),
        )
        for name, etype, start, dur in events:
            conn.execute(
                "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
                "VALUES (%s, %s, %s, '2026-06-22', %s, %s)",
                (athlete_id + i, name, etype, start, dur),
            )
        conn.commit()

        view = build_today_view(athlete_id + i, conn, today="2026-06-22")
        tappable = [w for w in view["windows"] if w.get("status") not in ("nudge", "event")]
        for w in tappable:
            ideas = w.get("food_ideas")
            assert ideas, f"[{label}] {w['slot_name']} has empty food_ideas — category not mapped in IDEAS"
            for idea in ideas:
                assert idea in all_catalog_ideas, (
                    f"[{label}] {w['slot_name']} idea {idea!r} not found in idea_catalog.IDEAS — "
                    "food_ideas must be sourced from the canonical catalog, not fabricated"
                )
        conn.close()


def test_record_window_capture_uses_log_date():
    """record_window_capture respects client-supplied log_date, not server date."""
    conn = _make_test_conn()
    # Simulate athlete logging at 11 PM PDT (= next-day UTC) but passing their local date
    local_date = "2026-06-14"
    record_window_capture(
        athlete_id=99,
        window_id="breakfast",
        method="text",
        text="oatmeal",
        photo_url=None,
        thumb_url=None,
        conn=conn,
        log_date=local_date,
    )
    row = conn.execute(
        "SELECT log_date FROM window_logs WHERE athlete_id = 99 AND window_id = 'breakfast'"
    ).fetchone()
    assert row is not None
    assert row["log_date"] == local_date, (
        f"Expected log_date={local_date!r} (client local), got {row['log_date']!r} (server UTC)"
    )
    conn.close()
