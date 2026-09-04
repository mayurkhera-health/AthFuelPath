"""
Module-scoped DB isolation for the backend test suite (migration/postgres-cloud-run).

Real PostgreSQL — the migration's own instructions are explicit that tests
must never be faked against SQLite. DATABASE_URL must point at a dedicated
test database (see _assert_test_db() below for the hard safety backstop).

Each test module gets a freshly-truncated + freshly-seeded database — the
closest Postgres equivalent to the old SQLite conftest's "fresh named
in-memory DB per module" isolation. Migrations run once per test session
(idempotent — db/postgres_migrate.py no-ops if already applied); seeds
(report_config defaults + fueling_foods catalog) are re-applied after every
per-module truncate, matching the old behavior where db.setup.init_db()
(which always seeded) ran fresh for every module.

test_notification_service.py and test_fueliq_service.py previously used
sqlite3.connect(":memory:") directly — this fixture runs for them too, but
any file still doing that will now fail loudly (no more SQLite anywhere) —
see the migration report's Phase 10 test-conversion notes for which files
needed direct updates.
"""
import itertools
import os
from unittest.mock import MagicMock

import pytest

# Needed by every test that logs in or calls a session-protected route (see
# api/services/session_auth.py).
os.environ.setdefault("APP_SESSION_SECRET", "test-session-secret-do-not-use-in-prod")

# Real PostgreSQL only. The database name MUST unmistakably signal "test" —
# see _assert_test_db() — this is not just a convention, it's enforced.
os.environ.setdefault("DATABASE_URL", "postgresql:///athfuelpath_test")

from api import database as _dbmod
from api.services import email_service
from api.services import email as _otp_email_module
from api.services import weather as _weathermod
from db.postgres_migrate import run_migrations
from db.postgres_seeds import seed_report_config, seed_health_checks, seed_fueling_foods


def _assert_test_db(conn) -> str:
    """Hard safety backstop: refuse to run destructive fixture logic (TRUNCATE)
    against anything whose database name doesn't unmistakably say 'test'.
    This is what stands between a misconfigured DATABASE_URL and truncating
    a real (staging/production/Cloud SQL) database."""
    dbname = conn.execute("SELECT current_database() AS n").fetchone()["n"]
    if "test" not in dbname.lower():
        raise RuntimeError(
            f"Refusing to run destructive test fixtures against database {dbname!r} — "
            "its name doesn't contain 'test'. Point DATABASE_URL at a dedicated test "
            "database (e.g. postgresql:///athfuelpath_test) before running the suite."
        )
    return dbname


@pytest.fixture(autouse=True)
def _clean_weather_caches():
    """
    get_weather() and reverse_geocode_city() cache results in module-level dicts
    (correct for prod — a single process, TTL-bounded). In tests that's a silent
    cross-test/cross-file pollution risk: several test files use the same sample
    coordinates (e.g. San Jose, 37.33/-121.89), so a test earlier in the run can
    populate the cache and a later test's mocked _fetch_weather never gets called
    at all — it just serves the earlier test's cached result instead, passing or
    failing based on execution order rather than what it actually asserts.
    """
    _weathermod._weather_cache.clear()
    _weathermod._geocode_cache.clear()
    yield


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """
    Hard block on real outbound email for the entire suite. email_service.send_email
    reads real GMAIL_USER/GMAIL_APP_PASSWORD from the environment — with no guard
    here, any test exercising a route that sends a transactional email would send a
    REAL message via smtplib.

    api.services.email (send_otp_email) imports send_email via `from
    api.services.email_service import send_email` — a separate bound name in
    its own module namespace, which patching email_service.send_email alone
    does NOT affect. Patch it there too, or any test hitting /request-otp
    without its own explicit mock would attempt a real Gmail send.
    """
    monkeypatch.setattr(email_service, "send_email", lambda *a, **k: True)
    monkeypatch.setattr(_otp_email_module, "send_email", lambda *a, **k: True)


@pytest.fixture(autouse=True, scope="session")
def _disable_scheduler_thread():
    """Prevent APScheduler's background daemon thread from starting during the
    test suite — add_job/modify_job still work (in-memory job store), but no
    jobs ever execute because the daemon thread never starts."""
    import api.main as _main
    _main._scheduler.start = MagicMock(return_value=None)


@pytest.fixture(scope="session", autouse=True)
def _migrate_once():
    """Apply db/postgres/*.sql once per test session. Idempotent — no-ops on
    every run after the first (schema_migrations already has 001 applied)."""
    conn = _dbmod.get_conn()
    try:
        _assert_test_db(conn)
    finally:
        conn.close()
    run_migrations(quiet=True)
    yield


def _truncate_all(conn) -> None:
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


_counter = itertools.count(1)


@pytest.fixture(autouse=True, scope="module")
def _fresh_db():
    conn = _dbmod.get_conn()
    try:
        _assert_test_db(conn)
        _truncate_all(conn)
        seed_report_config(conn)
        seed_health_checks(conn)
    finally:
        conn.close()
    seed_fueling_foods()  # opens/closes its own connection, matches db/setup.py's original signature
    next(_counter)
    yield


def auth_headers(role, parent_id=None, athlete_id=None):
    """Shared helper: mint a valid session token for a test caller and return
    it as a ready-to-use requests/TestClient headers dict. role is 'parent' or
    'athlete'. Import as `from tests.conftest import auth_headers`.

    For role='athlete', also guarantees an athlete_logins row exists for
    athlete_id (idempotent — ON CONFLICT DO NOTHING). A real athlete token
    can never be minted without one (see api/routes/auth.py's
    athlete-create-login), and assert_owns_athlete now re-checks this row
    is still live on every self-access call (docs/planning/
    parent-initiated-athlete-unlink.md) — so a test minting a bare token
    without it was testing a state production can't produce. Skipped
    silently if athlete_id doesn't exist at all (some tests intentionally
    use a fabricated id to exercise a 404 path)."""
    from api.services.session_auth import mint_session_token
    if role == "athlete" and athlete_id is not None:
        conn = _dbmod.get_conn()
        try:
            conn.execute(
                "INSERT INTO athlete_logins (email, athlete_id) "
                "SELECT %s, %s WHERE EXISTS (SELECT 1 FROM athletes WHERE id = %s) "
                "ON CONFLICT (athlete_id) DO NOTHING",
                (f"test-auth-headers-athlete-{athlete_id}@example.com", athlete_id, athlete_id),
            )
            conn.commit()
        finally:
            conn.close()
    token = mint_session_token(role=role, parent_id=parent_id, athlete_id=athlete_id)
    return {"Authorization": f"Bearer {token}"}
