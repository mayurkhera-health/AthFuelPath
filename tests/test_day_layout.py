from datetime import datetime
from api.services.day_layout import build_day_layout


def _athlete():
    return {"id": 1, "weight_lbs": 120, "height_ft": 5, "height_in": 4,
            "gender": "boy", "age": 14}


def test_rest_day_three_meals_3334():
    # No events -> rest day -> breakfast/lunch/dinner
    res = build_day_layout([], _athlete(), now=datetime(2026, 6, 27, 7, 0))
    assert res["day_type"] == "rest"
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["breakfast", "lunch", "dinner"]
    assert all(c["is_tappable"] for c in res["cards"])


def test_active_recovery_uses_rest_style_three_meals():
    ev = {"id": 9, "event_type": "practice", "activity_type": "active_recovery",
          "event_date": "2026-06-27", "start_time": "10:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert res["day_type"] == "active_recovery"
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["breakfast", "lunch", "dinner"]


def test_morning_event_order_everyday_last():
    # Practice starting 09:00 (<11:00) -> fuel_before -> top_up -> event -> recharge -> rebuild -> everyday_meal
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["fuel_before", "top_up", "event", "recharge", "rebuild", "everyday_meal"]
    # event marker is visible, non-tappable
    event_card = next(c for c in res["cards"] if c["card"] == "event")
    assert event_card["is_event"] is True and event_card["is_tappable"] is False


def test_afternoon_event_order_everyday_first():
    # Practice starting 15:00 (>=11:00) -> everyday_meal -> fuel_before -> top_up -> event -> recharge -> rebuild
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    kinds = [c["card"] for c in res["cards"]]
    assert kinds == ["everyday_meal", "fuel_before", "top_up", "event", "recharge", "rebuild"]


def test_keep_going_appears_only_over_75min():
    long_ev = {"id": 1, "event_type": "game", "activity_type": "game",
               "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.5}  # 90 min
    res = build_day_layout([long_ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "keep_going" in [c["card"] for c in res["cards"]]

    short_ev = {**long_ev, "duration_hours": 1.0}  # 60 min
    res2 = build_day_layout([short_ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "keep_going" not in [c["card"] for c in res2["cards"]]


def test_morning_everyday_sorts_last_by_sort_time():
    # On a morning event, everyday_meal must ALSO sort last by sort_time (not just list order)
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    by_sort = sorted(res["cards"], key=lambda c: c["sort_time"])
    assert by_sort[-1]["card"] == "everyday_meal"


def test_afternoon_everyday_sorts_first_by_sort_time():
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    by_sort = sorted(res["cards"], key=lambda c: c["sort_time"])
    assert by_sort[0]["card"] == "everyday_meal"


def test_keep_going_boundary_exactly_75_excluded():
    # 75 min exactly -> no keep_going (condition is strictly > 75)
    ev = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.25}  # 75 min
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "keep_going" not in [c["card"] for c in res["cards"]]


def test_evening_training_appends_wind_down():
    # Practice 19:00 for 2h -> ends 21:00 (>20:00) -> wind_down appended at the end
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "19:00", "duration_hours": 2.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    kinds = [c["card"] for c in res["cards"]]
    assert kinds[-1] == "wind_down"
    wd = res["cards"][-1]
    assert wd["is_tappable"] is True


def test_no_wind_down_when_athlete_dismissed_it_forever():
    """Regression: mobile's 'Skip forever' had no backend route to persist to,
    so the dismissal never stuck — wind_down_dismissed on the athlete row
    (set by PATCH /athletes/:id/dismiss-wind-down) must suppress the card."""
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "19:00", "duration_hours": 2.0}
    athlete = {**_athlete(), "wind_down_dismissed": 1}
    res = build_day_layout([ev], athlete, now=datetime(2026, 6, 27, 6, 0))
    assert "wind_down" not in [c["card"] for c in res["cards"]]


def test_no_wind_down_when_event_ends_before_8pm():
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}  # ends 16:00
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert "wind_down" not in [c["card"] for c in res["cards"]]


def test_wind_down_sorts_last_by_sort_time():
    # wind_down is appended last AND must sort last (after rebuild at end+1h)
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "19:00", "duration_hours": 2.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    by_sort = sorted(res["cards"], key=lambda c: c["sort_time"])
    assert by_sort[-1]["card"] == "wind_down"


def test_tournament_activity_type_uses_template():
    ev = {"id": 1, "event_type": "tournament", "activity_type": "tournament",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.5}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert res["day_type"] == "tournament"
    # tournament template emits final recharge + rebuild
    labels = [c.get("label", "") for c in res["cards"]]
    assert any("After Final Game" in l for l in labels)


def test_two_games_same_day_is_tournament():
    g1 = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.5}
    g2 = {"id": 2, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "13:00", "duration_hours": 1.5}
    res = build_day_layout([g1, g2], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    assert res["day_type"] == "tournament"
    # between-games recharge present (gap 13:00 - 10:30 = 150 min >= 90 -> recharge + rebuild)
    labels = [c.get("label", "") for c in res["cards"]]
    assert any("Between Games 1 & 2" in l for l in labels)
    assert any("Pre-Game 2 Meal" in l for l in labels)


def test_tournament_day_with_strength_session_excludes_non_game_from_schedule():
    # Morning lift + two games -> tournament, but the lift must NOT become a game slot.
    lift = {"id": 1, "event_type": "strength", "activity_type": "strength_cond",
            "event_date": "2026-06-27", "start_time": "07:00", "duration_hours": 1.0}
    g1 = {"id": 2, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "10:00", "duration_hours": 1.5}
    g2 = {"id": 3, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "14:00", "duration_hours": 1.5}
    res = build_day_layout([lift, g1, g2], _athlete(), now=datetime(2026, 6, 27, 5, 0))
    assert res["day_type"] == "tournament"
    # Exactly two game markers (game 1 and game 2), no third from the lift.
    event_cards = [c for c in res["cards"] if c["card"] == "event"]
    assert len(event_cards) == 2


def test_single_tournament_event_has_no_between_games():
    ev = {"id": 1, "event_type": "tournament", "activity_type": "tournament",
          "event_date": "2026-06-27", "start_time": "09:00", "duration_hours": 1.5}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    labels = [c.get("label", "") for c in res["cards"]]
    assert not any("Between Games" in l for l in labels)


def test_guardrail_floor_no_card_before_0630():
    # Early game 07:00 -> fuel_before would be 04:00 -> must be floored to 06:30
    ev = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "07:00", "duration_hours": 1.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 5, 0))
    for c in res["cards"]:
        assert c["sort_time"] >= "06:30", f"{c['card']} at {c['sort_time']}"


def test_guardrail_caps_tappable_windows_at_6():
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 2.0}
    res = build_day_layout([ev], _athlete(), now=datetime(2026, 6, 27, 6, 0))
    tappable = [c for c in res["cards"] if c["is_tappable"]]
    assert len(tappable) <= 6


def test_tournament_not_capped_keeps_recovery_cards():
    # 3-game tournament must retain post-tournament recharge + rebuild (cap must not drop them)
    g = [{"id": i, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": st, "duration_hours": 1.5}
         for i, st in [(1, "08:00"), (2, "11:00"), (3, "14:00")]]
    res = build_day_layout(g, _athlete(), now=datetime(2026, 6, 27, 5, 0))
    labels = [c.get("label", "") for c in res["cards"]]
    assert any("After Final Game" in l for l in labels)
    assert any("Tournament Recovery Meal" in l for l in labels)
