"""System Health: checks, runner isolation, transitions, alert channels, cooldown,
heartbeat math. All externals mocked."""

import os
os.environ["DB_PATH"] = ":memory:"

from collections import namedtuple
from datetime import datetime, timedelta

import pytest

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import health_service as H
from api.services import health_alerts
from api.services import founder_alerts


def _wipe(conn):
    conn.commit()
    tables = [
        r["table_name"]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name != 'schema_migrations'"
        ).fetchall()
    ]
    if tables:
        conn.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
    conn.commit()


@pytest.fixture
def conn(monkeypatch):
    ka = get_conn()
    init_db()
    run_all()
    _wipe(ka)
    # Re-seed the check rows the migration seeds (wiped above).
    with ka.cursor() as cur:
        cur.executemany(
            "INSERT INTO health_checks (check_name, status) VALUES (%s, 'unknown') "
            "ON CONFLICT (check_name) DO NOTHING",
            [(n,) for n in H.CHECK_ORDER])
    ka.commit()
    # No real external calls in unit tests.
    monkeypatch.delenv("ADMIN_ALERT_PARENT_ID", raising=False)
    monkeypatch.delenv("ADMIN_ALERT_EMAIL", raising=False)
    yield ka
    ka.close()


# ── Runner isolation ──────────────────────────────────────────────────────────
def test_crashing_check_marks_itself_red_others_still_run(conn):
    def boom(c):
        raise RuntimeError("kaboom")
    def ok(c):
        return "green", "fine", None
    H._run_checks(conn, [("db_writable", boom), ("disk_space", ok)])
    rows = {r["check_name"]: r for r in conn.execute("SELECT * FROM health_checks").fetchall()}
    assert rows["db_writable"]["status"] == "red"
    assert "kaboom" in rows["db_writable"]["detail"]
    assert rows["disk_space"]["status"] == "green"


# ── Individual checks ─────────────────────────────────────────────────────────
def test_db_writable_green_and_red(conn):
    assert H.check_db_writable(conn)[0] == "green"      # real writable conn

    class Bad:
        def execute(self, *a, **k):
            raise RuntimeError("readonly database")
        def rollback(self):
            pass
    st, detail, _ = H.check_db_writable(Bad())
    assert st == "red" and "readonly" in detail


def test_disk_thresholds(conn, monkeypatch):
    DU = namedtuple("DU", "total used free")
    monkeypatch.setattr(H.shutil, "disk_usage", lambda p: DU(1000, 850, 150))
    st, detail, metric = H.check_disk_space(conn)
    assert st == "red" and metric == 85.0
    monkeypatch.setattr(H.shutil, "disk_usage", lambda p: DU(1000, 600, 400))
    st2, _, metric2 = H.check_disk_space(conn)
    assert st2 == "green" and metric2 == 60.0


def test_scheduler_freshness(conn):
    # no heartbeat -> unknown
    assert H.check_scheduler_notifications(conn)[0] == "unknown"
    fresh = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    stale = (datetime.utcnow() - timedelta(minutes=45)).isoformat()
    conn.execute("INSERT INTO scheduler_heartbeats (job_name, last_run_at) VALUES ('notifications', %s)", (fresh,))
    conn.commit()
    assert H.check_scheduler_notifications(conn)[0] == "green"
    conn.execute("UPDATE scheduler_heartbeats SET last_run_at=%s WHERE job_name='notifications'", (stale,))
    conn.commit()
    assert H.check_scheduler_notifications(conn)[0] == "red"


def test_calendar_sync_systemic(conn):
    import json
    assert H.check_calendar_sync_systemic(conn)[0] == "unknown"  # no meta
    def setmeta(a, s):
        conn.execute(
            "INSERT INTO scheduler_heartbeats (job_name, meta) VALUES ('calendar_sync', %s) "
            "ON CONFLICT (job_name) DO UPDATE SET meta = EXCLUDED.meta",
            (json.dumps({"attempted": a, "succeeded": s}),))
        conn.commit()
    setmeta(0, 0)
    assert H.check_calendar_sync_systemic(conn)[0] == "unknown"   # 0 attempts
    setmeta(12, 12)
    assert H.check_calendar_sync_systemic(conn)[0] == "green"     # 12/12
    setmeta(12, 11)
    assert H.check_calendar_sync_systemic(conn)[0] == "green"     # 1 failing feed still green
    setmeta(12, 0)
    st, detail, _ = H.check_calendar_sync_systemic(conn)
    assert st == "red" and "0/12" in detail                       # total outage


def test_expo_push_passive(conn):
    assert H.check_expo_push(conn)[0] == "unknown"                # no sends
    for _ in range(10):
        conn.execute("INSERT INTO expo_push_log (success) VALUES (0)")
    conn.commit()
    assert H.check_expo_push(conn)[0] == "red"                    # all failed
    conn.execute("INSERT INTO expo_push_log (success) VALUES (1)")
    conn.commit()
    assert H.check_expo_push(conn)[0] == "green"                  # one recent success


# ── Transitions + alerting ────────────────────────────────────────────────────
def test_transition_creates_incident_and_alerts_once(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(health_alerts, "dispatch", lambda *a, **k: (calls.append(a[1:4]) or "push ✓"))
    # green -> red
    conn.execute("UPDATE health_checks SET status='green' WHERE check_name='gmail_smtp'")
    conn.commit()
    H._run_checks(conn, [("gmail_smtp", lambda c: ("red", "auth failed", None))])
    assert len(calls) == 1
    inc = conn.execute("SELECT from_status,to_status FROM health_incidents WHERE check_name='gmail_smtp'").fetchall()
    assert len(inc) == 1 and inc[0]["from_status"] == "green" and inc[0]["to_status"] == "red"
    # red -> red: no new incident, no alert
    H._run_checks(conn, [("gmail_smtp", lambda c: ("red", "still failing", None))])
    assert len(calls) == 1
    assert conn.execute("SELECT COUNT(*) AS count FROM health_incidents WHERE check_name='gmail_smtp'").fetchone()["count"] == 1
    # red -> green: recovery alert
    H._run_checks(conn, [("gmail_smtp", lambda c: ("green", "login OK", None))])
    assert len(calls) == 2 and calls[1][2] == "green"


def test_push_success_no_email(conn, monkeypatch):
    pushed, emailed = [], []
    monkeypatch.setattr(founder_alerts, "_push", lambda c, t, b: (pushed.append(1) or True))
    monkeypatch.setattr(founder_alerts, "_email", lambda t, b: (emailed.append(1) or True))
    note = health_alerts.dispatch(conn, "gmail_smtp", "green", "red", "auth failed")
    assert note == "push ✓" and pushed and not emailed


def test_push_fail_falls_back_to_email_once(conn, monkeypatch):
    emailed = []
    monkeypatch.setattr(founder_alerts, "_push", lambda c, t, b: False)
    monkeypatch.setattr(founder_alerts, "_email", lambda t, b: (emailed.append(1) or True))
    note = health_alerts.dispatch(conn, "bedrock_ping", "green", "red", "ping failed")
    assert len(emailed) == 1 and "email ✓" in note


def test_expo_push_check_uses_email_directly(conn, monkeypatch):
    pushed, emailed = [], []
    monkeypatch.setattr(founder_alerts, "_push", lambda c, t, b: (pushed.append(1) or True))
    monkeypatch.setattr(founder_alerts, "_email", lambda t, b: (emailed.append(1) or True))
    note = health_alerts.dispatch(conn, "expo_push", "green", "red", "all sends failed")
    assert len(emailed) == 1 and not pushed and "push unavailable" in note


def test_cooldown_suppresses_repeat_down_but_not_recovery(conn, monkeypatch):
    sent = []
    monkeypatch.setattr(founder_alerts, "_push", lambda c, t, b: (sent.append(1) or True))
    monkeypatch.setattr(founder_alerts, "_email", lambda t, b: True)
    # first down fires + stamps last_alerted_at
    assert health_alerts.dispatch(conn, "disk_space", "green", "red", "84%") == "push ✓"
    assert len(sent) == 1
    # second down within cooldown → suppressed
    note = health_alerts.dispatch(conn, "disk_space", "green", "red", "85%")
    assert note == "suppressed (cooldown)" and len(sent) == 1
    # recovery bypasses cooldown
    note2 = health_alerts.dispatch(conn, "disk_space", "red", "green", "62%")
    assert note2 == "push ✓" and len(sent) == 2


def test_unknown_to_green_does_not_alert(conn):
    assert health_alerts._direction("unknown", "green") is None
    assert health_alerts._direction("unknown", "red") == "down"
    assert health_alerts._direction("green", "red") == "down"
    assert health_alerts._direction("red", "green") == "recovery"


# ── Heartbeat instrumentation ─────────────────────────────────────────────────
def test_instrument_job_records_run_and_success(conn):
    H.instrument_job("notifications", lambda: None)()
    row = conn.execute("SELECT last_run_at,last_success_at,last_error FROM scheduler_heartbeats WHERE job_name='notifications'").fetchone()
    assert row["last_run_at"] and row["last_success_at"] and row["last_error"] is None


def test_instrument_job_records_error_and_reraises(conn):
    def bad():
        raise ValueError("job died")
    with pytest.raises(ValueError):
        H.instrument_job("calendar_sync", bad)()
    row = conn.execute("SELECT last_error FROM scheduler_heartbeats WHERE job_name='calendar_sync'").fetchone()
    assert row and "job died" in row["last_error"]
