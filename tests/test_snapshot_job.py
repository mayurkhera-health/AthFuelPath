import pytest
from api.database import get_conn
from db.setup import init_db
from api.services.snapshot_job import generate_snapshot, generate_all_snapshots
from api.services.window_templates import scheduled_tap_window_keys

WEEK_DATES = [f"2026-07-{20 + i}" for i in range(7)]  # 20..26


@pytest.fixture(autouse=True)
def seed():
    init_db()
    conn = get_conn()
    conn.execute("DELETE FROM confirmations WHERE athlete_id IN (1,2)")
    conn.execute("DELETE FROM events WHERE athlete_id IN (1,2)")
    conn.execute("INSERT OR IGNORE INTO parents (id,full_name,email,consent_timestamp) VALUES (1,'P','p@e.com','2026-01-01')")
    conn.execute("INSERT OR IGNORE INTO athletes (id,parent_id,first_name,age,gender,weight_lbs,height_ft,height_in) VALUES (1,1,'Alice',15,'female',130,5,4)")
    conn.execute("INSERT OR IGNORE INTO athletes (id,parent_id,first_name,age,gender,weight_lbs,height_ft,height_in) VALUES (2,1,'Bob',14,'male',140,5,6)")
    conn.execute("INSERT OR IGNORE INTO teams (id,name,season,threshold_pct) VALUES (1,'U16','S',80)")
    conn.execute("INSERT OR IGNORE INTO roster_membership (athlete_id,team_id,parent_consent_flag) VALUES (1,1,1)")
    conn.execute("INSERT OR IGNORE INTO roster_membership (athlete_id,team_id,parent_consent_flag) VALUES (2,1,1)")
    conn.commit()
    conn.close()


def _confirm(athlete_id: int, log_date: str, window_key: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO confirmations (athlete_id, log_date, window_key, window_type) "
        "VALUES (?,?,?,'pre_fuel')",
        (athlete_id, log_date, window_key),
    )
    conn.commit()
    conn.close()


def _scheduled_keys(athlete_id: int, date_str: str) -> list[str]:
    conn = get_conn()
    keys = scheduled_tap_window_keys(athlete_id, date_str, conn)
    conn.close()
    return keys


def _confirm_everything_scheduled(athlete_id: int, dates: list[str]):
    for d in dates:
        for key in _scheduled_keys(athlete_id, d):
            _confirm(athlete_id, d, key)


def test_empty_confirmations_zero_above_threshold():
    result = generate_snapshot(1, week_start="2026-07-20")
    assert result["roster_count"] == 2
    assert result["players_above_threshold"] == 0


def test_athlete_above_threshold_counted():
    # Alice confirms every window the engine actually scheduled all week — 100%.
    # Under the old (unpatched) code this scores 0%: fueling_window_log never
    # gets a production write, so completed is always 0 regardless of
    # confirmations rows — this is the core regression this fix addresses.
    _confirm_everything_scheduled(1, WEEK_DATES)
    result = generate_snapshot(1, week_start="2026-07-20")
    assert result["players_above_threshold"] == 1


def test_athlete_below_threshold_not_counted():
    # Bob confirms a single window across the week — well under 80%.
    _confirm(2, WEEK_DATES[0], "everyday_breakfast")
    result = generate_snapshot(1, week_start="2026-07-20")
    assert result["players_above_threshold"] == 0


def test_completion_uses_real_per_day_scheduled_window_count():
    """A game day produces a different window shape than a rest day — the
    denominator is NOT a fixed 6-slot constant. Confirming exactly what the
    engine scheduled for a week that mixes a game day and rest days must
    still score 100%, proving the per-day engine call drives the math."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (1, 'Game', 'game', '2026-07-22', '15:00', 2)"
    )
    conn.commit()
    conn.close()

    game_day_keys = _scheduled_keys(1, "2026-07-22")
    assert game_day_keys != _scheduled_keys(1, "2026-07-20")  # shape actually differs

    _confirm_everything_scheduled(1, WEEK_DATES)
    result = generate_snapshot(1, week_start="2026-07-20")
    assert result["players_above_threshold"] == 1


def test_snapshot_upserted_to_db():
    generate_snapshot(1, week_start="2026-07-20")
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM team_engagement_snapshot WHERE team_id=1 AND week_start='2026-07-20'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["roster_count"] == 2


def test_snapshot_upsert_updates_existing():
    generate_snapshot(1, week_start="2026-07-20")
    _confirm_everything_scheduled(1, WEEK_DATES)
    generate_snapshot(1, week_start="2026-07-20")
    conn = get_conn()
    row = conn.execute(
        "SELECT players_above_threshold FROM team_engagement_snapshot "
        "WHERE team_id=1 AND week_start='2026-07-20'"
    ).fetchone()
    conn.close()
    assert row["players_above_threshold"] == 1


def test_generate_all_snapshots_no_error():
    generate_all_snapshots()


def test_unknown_team_returns_not_found():
    result = generate_snapshot(9999, week_start="2026-07-21")
    assert result["status"] == "team_not_found"
