"""Startup catch-up for the in-memory calendar_sync scheduler (Option B).

Simulates deploy/restart at different staleness: a mid-cycle restart resets the
in-memory 6-h timer, so on startup we either run one catch-up (stale/initial) or
re-anchor the interval's first run to last_success + 6h (fresh). Notifications is
untouched. All the scheduler I/O is captured via a fake scheduler; the tick runs
against an in-memory DB with no athletes."""

import os
os.environ["DB_PATH"] = ":memory:"

import logging
from datetime import datetime, timedelta, timezone

import pytest

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import health_service as hs
from api.services import ics_sync


CADENCE_H = 6  # calendar_sync cadence


class FakeScheduler:
    """Records modify_job / add_job calls instead of scheduling anything."""
    def __init__(self):
        self.modified = []   # [(job_id, kwargs)]
        self.added = []      # [{"func":..., "trigger":..., "kwargs": {...}}]

    def modify_job(self, job_id, **kwargs):
        self.modified.append((job_id, kwargs))

    def add_job(self, func, trigger=None, **kwargs):
        self.added.append({"func": func, "trigger": trigger, "kwargs": kwargs})


def _iso_ago(minutes):
    return (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()


def _seed_heartbeat(conn, last_success_iso):
    """Seed calendar_sync with matching last_run/last_success (a clean prior run)."""
    conn.execute(
        "INSERT INTO scheduler_heartbeats (job_name, last_run_at, last_success_at) "
        "VALUES ('calendar_sync', %s, %s) "
        "ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at, "
        "last_success_at = EXCLUDED.last_success_at",
        (last_success_iso, last_success_iso))
    conn.commit()


def _read_success(conn):
    row = conn.execute(
        "SELECT last_success_at FROM scheduler_heartbeats WHERE job_name='calendar_sync'").fetchone()
    return row["last_success_at"] if row else None


@pytest.fixture
def conn():
    ka = get_conn()
    init_db()
    run_all()
    # start each test from a clean calendar_sync heartbeat
    ka.execute("DELETE FROM scheduler_heartbeats WHERE job_name='calendar_sync'")
    ka.commit()
    yield ka
    ka.close()


# ── restart after 4h → fresh → re-anchor, NO catch-up ────────────────────────
def test_restart_after_4h_reanchors_and_does_not_run(conn, caplog):
    seed = _iso_ago(4 * 60)
    _seed_heartbeat(conn, seed)
    sched = FakeScheduler()

    with caplog.at_level(logging.INFO, logger="api.services.ics_sync"):
        ics_sync.configure_calendar_sync_startup(sched)

    # No catch-up job scheduled…
    assert sched.added == []
    # …instead the interval's next run is re-anchored to last_success + 6h.
    assert len(sched.modified) == 1
    job_id, kwargs = sched.modified[0]
    assert job_id == "calendar_sync"
    expected = datetime.fromisoformat(seed).replace(tzinfo=timezone.utc) + timedelta(hours=CADENCE_H)
    assert kwargs["next_run_time"] == expected
    # Anchor is in the future (never a past date → no immediate interval fire).
    assert kwargs["next_run_time"] > datetime.now(timezone.utc)
    assert "fresh" in caplog.text and "anchored" in caplog.text
    # Heartbeat untouched.
    assert _read_success(conn) == seed


# ── restart after 7h → stale → ONE catch-up run ──────────────────────────────
def test_restart_after_7h_runs_one_catchup(conn, caplog):
    seed = _iso_ago(7 * 60)
    _seed_heartbeat(conn, seed)
    sched = FakeScheduler()

    with caplog.at_level(logging.INFO, logger="api.services.ics_sync"):
        ics_sync.configure_calendar_sync_startup(sched)

    assert sched.modified == []                       # no re-anchor when stale
    assert len(sched.added) == 1                       # exactly one catch-up
    job = sched.added[0]
    assert job["trigger"] == "date"
    assert job["kwargs"]["id"] == "calendar_sync_catchup"
    assert "stale" in caplog.text and "running catch-up now" in caplog.text

    # Run the scheduled catch-up → heartbeat is refreshed to ~now.
    job["func"]()
    after = _read_success(conn)
    assert after is not None
    assert datetime.fromisoformat(after) > datetime.fromisoformat(seed)


# ── no prior run (NULL heartbeat) → initial sync, heartbeat created ──────────
def test_null_heartbeat_runs_initial_sync_and_creates_row(conn, caplog):
    assert _read_success(conn) is None                 # nothing seeded
    sched = FakeScheduler()

    with caplog.at_level(logging.INFO, logger="api.services.ics_sync"):
        ics_sync.configure_calendar_sync_startup(sched)

    assert sched.modified == []
    assert len(sched.added) == 1
    assert sched.added[0]["kwargs"]["id"] == "calendar_sync_catchup"
    # The initial-run log line — NOT the 'stale' one.
    assert "no prior run — running initial sync" in caplog.text
    assert "stale" not in caplog.text

    # Running it creates the heartbeat row with a success timestamp.
    sched.added[0]["func"]()
    assert _read_success(conn) is not None


# ── concurrency: a second instance starting together does not double-run ─────
def test_claim_is_single_winner(conn):
    _seed_heartbeat(conn, _iso_ago(7 * 60))            # stale
    assert hs.claim_calendar_sync_catchup(conn) is True    # first instance wins
    assert hs.claim_calendar_sync_catchup(conn) is False   # second sees the claim
