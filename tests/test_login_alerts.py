"""Beta login alerts — founder gets pinged on every parent login/signup, with
new-vs-returning wording, no throttling, best-effort isolation, and an env
toggle. Alerts are scheduled as BackgroundTasks (TestClient runs them
synchronously before the response returns, so we can assert right after)."""

import os
os.environ["DB_PATH"] = ":memory:"

import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import founder_alerts
from api.main import app

# The genuine delivery fn, captured before any fixture swaps it for a recorder.
_REAL_NOTIFY = founder_alerts.notify_founder


def _wipe(conn):
    conn.commit()
    tables = [r["table_name"] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name != 'schema_migrations'"
    ).fetchall()]
    if tables:
        conn.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
    conn.commit()


def _insert_parent(conn, name, email, *, last_login=None):
    return conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed, created_at, last_login_at) "
        "VALUES (%s, %s, 't', TRUE, '2026-01-01T00:00:00', %s) RETURNING id",
        (name, email, last_login),
    ).fetchone()["id"]


ONBOARD_BODY = {
    "parent": {"full_name": "Pat Parent", "email": "pat@example.com", "consent_confirmed": True},
    "athlete": {"first_name": "Ari", "age": 14, "gender": "girl",
                "weight_lbs": 110, "height_ft": 5, "height_in": 6},
}


@pytest.fixture
def ctx(monkeypatch):
    ka = get_conn()
    init_db()
    run_all()
    _wipe(ka)
    monkeypatch.delenv("LOGIN_ALERTS_MODE", raising=False)
    # Capture every founder alert instead of actually sending it.
    sent = []
    monkeypatch.setattr(founder_alerts, "notify_founder",
                        lambda title, body, *a, **k: sent.append((title, body)) or "push ✓")
    with TestClient(app) as c:
        yield c, ka, sent
    ka.close()


def _login(c, email):
    """Drives a real parent login through the secure OTP path (auth v2.1
    Phase 4) instead of the now-deleted /api/auth/login. Inserts a
    known-plaintext OTP row directly (bypassing Gmail) so the test can
    submit it, mirroring the pattern used in tests/test_email_auth_flow.py.
    """
    from datetime import datetime
    from api.database import get_conn
    code = "123456"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO otp_codes (email, code_hash, expires_at) VALUES (%s, %s, %s)",
            (email.lower(), code_hash, expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    return c.post("/api/auth/email/verify", json={"email": email, "code": code})


# ── new vs. returning wording ────────────────────────────────────────────────
def test_new_signup_via_onboarding_alerts(ctx):
    c, _, sent = ctx
    r = c.post("/api/onboarding/complete", json=ONBOARD_BODY)
    assert r.status_code == 201
    assert len(sent) == 1
    title, body = sent[0]
    assert title == "🎉 New AthFuelPath signup"
    assert "Pat" in body and "Ari" in body      # first name + athlete hint


def test_returning_login_alerts_with_wave(ctx):
    c, ka, sent = ctx
    _insert_parent(ka, "Sarah Smith", "sarah@example.com", last_login="2026-02-01T00:00:00")
    ka.commit()
    assert _login(c, "sarah@example.com").status_code == 200
    assert sent == [("👋 AthFuelPath login", "Sarah logged in")]


def test_first_ever_explicit_login_reads_as_new(ctx):
    c, ka, sent = ctx
    _insert_parent(ka, "New Nate", "nate@example.com", last_login=None)  # never stamped
    ka.commit()
    assert _login(c, "nate@example.com").status_code == 200
    assert sent[0][0] == "🎉 New AthFuelPath signup"
    # and the login stamps last_login_at so a NEXT login would be a returning one
    row = ka.execute("SELECT last_login_at FROM parents WHERE email='nate@example.com'").fetchone()
    assert row["last_login_at"] is not None


# ── no throttling by design ──────────────────────────────────────────────────
def test_rapid_repeated_logins_are_not_throttled(ctx):
    c, ka, sent = ctx
    _insert_parent(ka, "Rapid Rita", "rita@example.com", last_login="2026-02-01T00:00:00")
    ka.commit()
    for _ in range(3):
        assert _login(c, "rita@example.com").status_code == 200
    assert len(sent) == 3       # one alert per login, no dedup/cooldown


# ── failure isolation ────────────────────────────────────────────────────────
def test_alert_failure_never_breaks_login(ctx, monkeypatch):
    c, ka, _ = ctx
    _insert_parent(ka, "Ok Otto", "otto@example.com", last_login="2026-02-01T00:00:00")
    ka.commit()

    def boom(*a, **k):
        raise RuntimeError("alert pipeline exploded")
    monkeypatch.setattr(founder_alerts, "notify_founder", boom)

    assert _login(c, "otto@example.com").status_code == 200   # login still succeeds


def test_push_failure_falls_back_to_email(ctx, monkeypatch):
    c, ka, _ = ctx
    _insert_parent(ka, "Fran Faller", "fb@example.com", last_login="2026-02-01T00:00:00")
    ka.commit()

    # Restore the REAL notify_founder (the fixture swapped it for a recorder),
    # then force push to fail and capture the email fallback.
    monkeypatch.setattr(founder_alerts, "notify_founder", _REAL_NOTIFY)
    monkeypatch.setattr(founder_alerts, "_push", lambda conn, t, b: False)
    emailed = []
    monkeypatch.setattr(founder_alerts, "_email", lambda t, b: emailed.append((t, b)) or True)

    assert _login(c, "fb@example.com").status_code == 200
    assert emailed == [("👋 AthFuelPath login", "Fran logged in")]


# ── env toggle ───────────────────────────────────────────────────────────────
def test_mode_off_fires_nothing(ctx, monkeypatch):
    c, ka, sent = ctx
    monkeypatch.setenv("LOGIN_ALERTS_MODE", "off")
    _insert_parent(ka, "Quiet Quinn", "quinn@example.com", last_login="2026-02-01T00:00:00")
    ka.commit()
    assert _login(c, "quinn@example.com").status_code == 200
    assert sent == []


def test_mode_new_signups_only(ctx, monkeypatch):
    c, ka, sent = ctx
    monkeypatch.setenv("LOGIN_ALERTS_MODE", "new_signups_only")
    _insert_parent(ka, "Return Ray", "ray@example.com", last_login="2026-02-01T00:00:00")
    ka.commit()

    assert _login(c, "ray@example.com").status_code == 200   # returning → suppressed
    assert sent == []

    r = c.post("/api/onboarding/complete", json=ONBOARD_BODY)  # new signup → fires
    assert r.status_code == 201
    assert len(sent) == 1 and sent[0][0] == "🎉 New AthFuelPath signup"
