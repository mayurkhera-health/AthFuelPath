"""
Regression tests for the window templates engine.
All 8 tests from ATHFUELPATH_WINDOW_TEMPLATES_SPEC.md Section 10 must pass before any deploy
touching window_templates.py.
"""
import pytest
from datetime import datetime, date, time, timedelta
from api.services.window_templates import (
    generate_windows_for_day,
    build_tournament_windows,
    determine_day_type,
    EARLY_MORNING_MESSAGE,
    DAY_TYPE_DISPLAY,
    MAX_TAPS_PER_DAY,
)


# ── HELPERS ───────────────────────────────────────────────────────────────────

TEST_DATE = "2026-07-01"
TEST_BASE = date.fromisoformat(TEST_DATE)


def _event(start: str, end_hours: float = 1.5, event_type: str = "game") -> dict:
    """Build a minimal event dict for the engine."""
    h, m = map(int, start.split(":"))
    return {
        "athlete_id":     1,
        "event_name":     "Test Event",
        "event_type":     event_type,
        "event_date":     TEST_DATE,
        "start_time":     start,
        "duration_hours": end_hours,
    }


def _gen(events: list) -> dict:
    return generate_windows_for_day(1, TEST_DATE, events)


def window_exists(result: dict, key: str, open_hhmm: str | None = None,
                  close_hhmm: str | None = None) -> bool:
    for w in result["windows"]:
        if w["key"] == key or w["key"].startswith(key):
            if open_hhmm:
                exp_open = datetime.combine(TEST_BASE, _parse(open_hhmm))
                if w["open_dt"] != exp_open:
                    continue
            if close_hhmm:
                exp_close = datetime.combine(TEST_BASE, _parse(close_hhmm))
                if w["close_dt"] != exp_close:
                    continue
            return True
    return False


def window_exists_type(result: dict, category: str) -> bool:
    return any(w["category"] == category for w in result["windows"])


def window_exists_label(result: dict, label: str) -> bool:
    return any(w["label"] == label for w in result["windows"])


def no_window_before(hhmm: str, result: dict) -> bool:
    cutoff = _parse(hhmm)
    return all(
        w["open_dt"].time() >= cutoff
        for w in result["windows"]
        if not w.get("is_nudge_only")
    )


def teaching_message_shown(result: dict) -> bool:
    return result.get("early_morning_message") == EARLY_MORNING_MESSAGE


def _parse(hhmm: str) -> time:
    h, m = map(int, hhmm.split(":"))
    return time(h, m)


# ── TEST 1: Evening practice ──────────────────────────────────────────────────

def test_evening_practice_7_30pm():
    """Practice 19:30–21:15. Pre-event meal at 16:30–17:00."""
    result = _gen([_event("19:30", end_hours=1.75, event_type="practice")])
    assert result["day_type"] == "practice_evening"

    # Pre-event meal opens at 19:30 - 3h = 16:30, closes at 19:30 - 2h30m = 17:00
    assert window_exists(result, "pre_event_meal", open_hhmm="16:30", close_hhmm="17:00"), \
        f"pre_event_meal 16:30–17:00 not found; windows: {[(w['key'], w['open_dt'].strftime('%H:%M'), w['close_dt'].strftime('%H:%M')) for w in result['windows']]}"

    # Recovery window opens at 21:15, closes at 21:45
    assert window_exists(result, "fuel_after_primary", open_hhmm="21:15", close_hhmm="21:45"), \
        "fuel_after_primary 21:15–21:45 not found"

    # Practice → no halftime nudge
    assert not window_exists_type(result, "fuel_during"), "fuel_during should NOT appear for practice"

    assert no_window_before("06:30", result), "A window opens before 06:30"


# ── TEST 2: Early morning game ────────────────────────────────────────────────

def test_early_morning_game_6am():
    """Game 06:00. Pre-event − 3h = 03:00 → early morning rule fires."""
    result = _gen([_event("06:00", end_hours=1.5, event_type="game")])
    assert result["day_type"] == "early_game"

    assert not window_exists(result, "pre_event_meal"), \
        "pre_event_meal must NOT exist when early morning rule fires"

    assert window_exists(result, "quick_morning_snack"), \
        "quick_morning_snack must exist for early game"

    # Proper breakfast starts at E_end = 07:30
    assert window_exists(result, "proper_breakfast_after", open_hhmm="07:30"), \
        "proper_breakfast_after must open at E_end (07:30)"

    assert teaching_message_shown(result), "early morning teaching message must be set"

    assert no_window_before("06:30", result), "A window opens before 06:30"


# ── TEST 3: Tournament close gap → merge ──────────────────────────────────────

def test_tournament_close_gap():
    """Games at 10:00 and 12:30. Gap = 12:30 - 11:30 = 1h. Should merge."""
    game1 = _event("10:00", end_hours=1.5, event_type="game")
    game2 = _event("12:30", end_hours=1.5, event_type="game")
    result = _gen([game1, game2])
    assert result["day_type"] == "tournament"

    assert window_exists_type(result, "between_games"), \
        "between_games window must exist for close gap"

    # No separate Recovery Window between 11:30 and 12:30
    between_windows = [
        w for w in result["windows"]
        if not w.get("is_nudge_only")
        and w["open_dt"] > datetime.combine(TEST_BASE, time(11, 30))
        and w["open_dt"] < datetime.combine(TEST_BASE, time(12, 30))
        and w["label"] == "Recovery Window"
    ]
    assert not between_windows, \
        "No separate Recovery Window should appear in the 11:30–12:30 gap"

    # No separate Pre-Event Meal between 11:30 and 12:30
    pre_event_between = [
        w for w in result["windows"]
        if not w.get("is_nudge_only")
        and w["open_dt"] > datetime.combine(TEST_BASE, time(11, 30))
        and w["open_dt"] < datetime.combine(TEST_BASE, time(12, 30))
        and w["label"] == "Pre-Event Meal"
    ]
    assert not pre_event_between, \
        "No Pre-Event Meal should appear in the 11:30–12:30 gap"


# ── TEST 4: Tournament wide gap → separate ────────────────────────────────────

def test_tournament_wide_gap():
    """Games at 09:00 and 14:00. Gap = 14:00 - 10:30 = 3h30m ≥ 3h. Should be separate."""
    game1 = _event("09:00", end_hours=1.5, event_type="game")
    game2 = _event("14:00", end_hours=1.5, event_type="game")
    result = _gen([game1, game2])
    assert result["day_type"] == "tournament"

    assert window_exists_type(result, "fuel_after"), \
        "fuel_after (recovery) window must exist after game 1"

    # Pre-event meal for game 2 (14:00 - 3h = 11:00)
    assert window_exists(result, "pre_event_meal", open_hhmm="11:00"), \
        "pre_event_meal for game 2 must open at 11:00"

    assert not window_exists_type(result, "between_games"), \
        "between_games must NOT appear when gap ≥ 3h"


# ── TEST 5: Adding event recalculates ─────────────────────────────────────────

def test_adding_event_recalculates():
    """Start with rest day. Add a 19:30 practice. Windows must update."""
    rest_result = _gen([])
    assert rest_result["day_type"] == "rest"
    assert not window_exists_type(rest_result, "fuel_before"), \
        "Rest day must have no fuel_before windows"

    # Now with the practice event
    practice_result = _gen([_event("19:30", end_hours=1.75, event_type="practice")])
    assert window_exists_type(practice_result, "fuel_before"), \
        "Adding a practice event must produce pre_event_meal (fuel_before)"

    # Afternoon snack (everyday_snack) should NOT be in practice_evening per DAY_TYPE_DISPLAY
    snack_present = any(
        w["key"] == "everyday_snack" for w in practice_result["windows"]
        if not w.get("is_nudge_only")
    )
    assert not snack_present, \
        "Afternoon snack should not appear on a practice_evening day"


# ── TEST 6: Max taps not exceeded ─────────────────────────────────────────────

def test_max_taps_not_exceeded():
    """No day type should ever show more than 5 confirmation taps."""
    test_cases = [
        ([], "rest"),
        ([_event("19:30", 1.75, "practice")], "practice_evening"),
        ([_event("09:00", 1.5, "practice")], "practice_morning"),
        ([_event("10:00", 1.5, "game")], "morning_game"),
        ([_event("14:00", 1.5, "game")], "afternoon_game"),
        ([_event("19:30", 1.5, "game")], "evening_event"),
        ([_event("06:00", 1.5, "game")], "early_game"),
        ([_event("10:00", 1.5, "game"), _event("12:30", 1.5, "game")], "tournament"),
        ([_event("09:00", 1.5, "game"), _event("14:00", 1.5, "game")], "tournament"),
    ]
    for events, expected_type in test_cases:
        result = _gen(events)
        tap_count = sum(
            1 for w in result["windows"]
            if w.get("tap", True) and not w.get("is_nudge_only")
        )
        assert tap_count <= MAX_TAPS_PER_DAY, \
            f"{result['day_type']} has {tap_count} taps (max {MAX_TAPS_PER_DAY})"


# ── TEST 7: fuel_during never a tap ──────────────────────────────────────────

def test_fuel_during_never_a_tap():
    """fuel_during windows must NEVER have a confirmation tap."""
    test_events = [
        [_event("14:00", 1.5, "game")],
        [_event("10:00", 1.5, "game"), _event("12:30", 1.5, "game")],
    ]
    for events in test_events:
        result = _gen(events)
        fuel_during = [w for w in result["windows"] if w["category"] == "fuel_during"]
        for w in fuel_during:
            assert w.get("tap") == False, \
                f"fuel_during window '{w['key']}' has tap=True — must be False"
            assert w.get("is_nudge_only") == True, \
                f"fuel_during window '{w['key']}' is not marked is_nudge_only"


# ── TEST 8: No window before 06:30 ───────────────────────────────────────────

def test_no_window_before_0630():
    """No tappable window open time may be before 06:30, for any event type."""
    test_cases = [
        [],
        [_event("06:00", 1.5, "game")],
        [_event("07:00", 1.5, "game")],
        [_event("09:00", 1.5, "practice")],
        [_event("19:30", 1.75, "practice")],
        [_event("10:00", 1.5, "game"), _event("12:30", 1.5, "game")],
    ]
    for events in test_cases:
        result = _gen(events)
        for w in result["windows"]:
            if not w.get("is_nudge_only"):
                assert w["open_dt"].time() >= time(6, 30), \
                    f"Window '{w['key']}' opens at {w['open_dt'].strftime('%H:%M')} — before 06:30"
