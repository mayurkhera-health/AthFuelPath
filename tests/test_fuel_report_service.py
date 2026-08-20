"""
Regression tests for Fuel Report v2 — 7 critical spec invariants.

1. Safety flag requires high load (load.is_high = False → no flag ever)
2. Safety flag requires low rate (high load + adequate rates → no flag)
3. Safety flag fires when BOTH conditions are met
4. At most one flag fires per report (priority: pre_fuel > recovery > hydration)
5. hydration rate is always None (fuel_during is never a tappable window)
6. None rate ≠ 0.0 rate (not-applicable week vs applicable-but-missed week)
7. Streak breaks on gap days — consecutive calendar days only
"""

from datetime import date, timedelta

import pytest

from api.database import get_conn
from api.services.fuel_report_service import (
    evaluate_safety_flag,
    compute_rates,
    compute_streak,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg_conn():
    """Real DB connection — report_config defaults (load_high_game_days=3.0,
    prefuel/recovery/hydration_rate_low=0.5, streak_min_confirms_per_day=1.0)
    are already seeded by tests/conftest.py's module-scoped fixture via
    db/postgres_seeds.py::seed_report_config, so no local setup is needed."""
    conn = get_conn()
    yield conn
    conn.close()


@pytest.fixture
def streak_conn():
    """Real DB connection with a dummy athlete row — confirmations.athlete_id
    is a real FK against athletes(id) in the Postgres schema. report_config
    defaults (streak_min_confirms_per_day=1.0) are already seeded by
    tests/conftest.py's module-scoped fixture."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO athletes (id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (1, 'Streak Athlete', 15, 'girl', 100, 5, 5) ON CONFLICT (id) DO NOTHING"
    )
    conn.execute("DELETE FROM confirmations WHERE athlete_id = 1")
    conn.commit()
    yield conn
    conn.close()


def _add_confirmation(conn, athlete_id, log_date, window_key="pre_event_meal", window_type="pre_fuel"):
    conn.execute(
        "INSERT INTO confirmations (athlete_id, log_date, window_key, window_type) VALUES (%s, %s, %s, %s)",
        (athlete_id, log_date, window_key, window_type),
    )
    conn.commit()


# ─── Test 1: Flag requires high load ──────────────────────────────────────────

def test_flag_absent_when_load_is_low(cfg_conn):
    """Safety flag must NOT fire when load.is_high is False, even if rates are zero."""
    load  = {"game_days": 1, "is_high": False}
    rates = {"pre_fuel": 0.0, "recovery": 0.0, "hydration": None}
    assert evaluate_safety_flag(load, rates, cfg_conn) is None


# ─── Test 2: Flag requires low rate ───────────────────────────────────────────

def test_flag_absent_when_rates_are_adequate(cfg_conn):
    """Safety flag must NOT fire when load is high but all rates meet the threshold."""
    load  = {"game_days": 4, "is_high": True}
    rates = {"pre_fuel": 0.8, "recovery": 0.9, "hydration": None}
    assert evaluate_safety_flag(load, rates, cfg_conn) is None


# ─── Test 3: Flag fires when BOTH conditions are met ──────────────────────────

def test_flag_fires_when_load_high_and_rate_low(cfg_conn):
    """Safety flag MUST fire when load is high AND pre_fuel rate is below threshold."""
    load  = {"game_days": 3, "is_high": True}
    rates = {"pre_fuel": 0.2, "recovery": 0.9, "hydration": None}
    result = evaluate_safety_flag(load, rates, cfg_conn)
    assert result is not None
    assert result["flag_key"] == "heat_high_load_low_prefuel"
    assert "message" in result


# ─── Test 4: At most one flag per report ──────────────────────────────────────

def test_flag_fires_at_most_once(cfg_conn):
    """Only the highest-priority flag fires — pre_fuel before recovery before hydration."""
    load  = {"game_days": 3, "is_high": True}
    rates = {"pre_fuel": 0.0, "recovery": 0.0, "hydration": None}
    result = evaluate_safety_flag(load, rates, cfg_conn)
    assert result is not None
    # pre_fuel is first in priority order — recovery must NOT also fire
    assert result["flag_key"] == "heat_high_load_low_prefuel"


# ─── Test 5: Hydration rate always None ───────────────────────────────────────

def test_hydration_rate_always_none(cfg_conn):
    """fuel_during is never a tappable window — hydration rate is always None, never 0.0."""
    # confirmations already exists in the real schema — no local setup needed.
    applicable = {"2026-06-09": [("pre_event_meal", "pre_fuel")]}
    rates = compute_rates(
        athlete_id=1,
        week_dates=["2026-06-09"],
        applicable=applicable,
        conn=cfg_conn,
    )
    assert rates["hydration"] is None, "hydration rate must always be None — fuel_during is never tappable"


# ─── Test 6: None rate ≠ 0.0 rate ────────────────────────────────────────────

def test_none_rate_when_no_applicable_windows(cfg_conn):
    """
    A week with no tappable windows returns None for all rates.
    None means 'not applicable this week', not 'applicable but zero confirmations'.
    """
    # confirmations already exists in the real schema — no local setup needed.
    # All rest days — no tappable windows
    applicable = {
        "2026-06-09": [],
        "2026-06-10": [],
        "2026-06-11": [],
    }
    rates = compute_rates(
        athlete_id=1,
        week_dates=["2026-06-09", "2026-06-10", "2026-06-11"],
        applicable=applicable,
        conn=cfg_conn,
    )
    assert rates["pre_fuel"]  is None, "None means not applicable — not 0.0"
    assert rates["recovery"]  is None, "None means not applicable — not 0.0"


# ─── Test 7: Streak breaks on gap days ────────────────────────────────────────

def test_streak_breaks_when_gap_in_days(streak_conn):
    """
    Streak counts consecutive calendar days working back from today.
    A single gap day (yesterday confirmed but today not) resets streak to 0.
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _add_confirmation(streak_conn, athlete_id=1, log_date=yesterday)
    # today has no confirmation — streak must be 0, not 1
    assert compute_streak(1, streak_conn) == 0


def test_streak_increments_through_consecutive_days(streak_conn):
    """Streak correctly counts N consecutive days working back from today."""
    today = date.today()
    for days_ago in range(3):
        d = (today - timedelta(days=days_ago)).isoformat()
        _add_confirmation(streak_conn, athlete_id=1, log_date=d)
    assert compute_streak(1, streak_conn) == 3
