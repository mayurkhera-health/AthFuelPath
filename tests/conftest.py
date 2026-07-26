"""
Module-scoped DB isolation for the backend test suite.

Each test module (file) gets its own named in-memory SQLite database so that
state written by one module's tests cannot bleed into another module's tests.
The fixture is autouse so no test file needs to import or request it.

test_notification_service.py and test_fueliq_service.py use sqlite3.connect(":memory:")
directly and are already isolated — the fixture runs for them too but they ignore
the named DB, which is harmless.
"""
import itertools
import os
from unittest.mock import MagicMock

import pytest

# Needed by every test that logs in or calls a session-protected route (see
# api/services/session_auth.py). Set once here rather than per-file since it's
# now a broad dependency, unlike the narrower TEAM_COACH_SESSION_SECRET.
os.environ.setdefault("APP_SESSION_SECRET", "test-session-secret-do-not-use-in-prod")

from api import database as _dbmod
from api.services import email_service
from api.services import weather as _weathermod
from api.services.db_migrations import run_all
from db.setup import init_db  # opens _persistent_memory_conn as the module-DB keepalive


@pytest.fixture(autouse=True)
def _clean_weather_caches():
    """
    get_weather() and reverse_geocode_city() cache results in module-level dicts
    (correct for prod — a single process, TTL-bounded). In tests that's a silent
    cross-test/cross-file pollution risk: several test files use the same sample
    coordinates (e.g. San Jose, 37.33/-121.89), so a test earlier in the run can
    populate the cache and a later test's mocked _fetch_weather never gets called
    at all — it just serves the earlier test's cached result instead, passing or
    failing based on execution order rather than what it actually asserts. Caught
    this exact failure mode while adding weather tests: a test worked in isolation
    but failed inside the full suite.
    """
    _weathermod._weather_cache.clear()
    _weathermod._geocode_cache.clear()
    yield


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """
    Hard block on real outbound email for the entire suite. email_service.send_email
    reads real GMAIL_USER/GMAIL_APP_PASSWORD from the environment (e.g. a local .env
    used for manual dev testing) — with no guard here, any test that exercises a
    route sending a transactional email (onboarding welcome, calendar-sync digest,
    founder alerts' email fallback, etc.) sends a REAL message via smtplib. This
    already happened in production: dozens of real "Welcome to FuelUp" emails went
    out to the test fixture address (tests/test_login_alerts.py's pat@example.com)
    from every full test-suite run on a machine with real Gmail creds configured.

    autouse + function-scoped so it applies to every test with zero opt-in, and a
    test that wants to assert on send_email's own args can still monkeypatch.setattr
    it again locally — that call runs after this one and simply wins for that test.
    No test currently does (grep confirms zero references to email_service in
    tests/), so this is a pure safety net, not a behavior change for any test today.
    """
    monkeypatch.setattr(email_service, "send_email", lambda *a, **k: True)


@pytest.fixture(autouse=True, scope="session")
def _disable_scheduler_thread():
    """
    Prevent APScheduler's background daemon thread from starting during the
    test suite.  The scheduler's add_job/modify_job still work (in-memory job
    store), but no jobs ever execute because the daemon thread never starts.

    Without this, configure_calendar_sync_startup() fires an immediate
    calendar-sync catchup job via a background thread every time a test module
    creates a fresh TestClient with an empty DB.  That background write races
    with the main-thread test writes on the shared-cache named in-memory DB
    and causes intermittent SQLITE_LOCKED errors.

    Some test fixtures call _wipe() which deletes every table row (including
    scheduler_heartbeats), so pre-seeding the heartbeat row is not enough —
    the only reliable fix is to prevent the scheduler thread from ever running.
    """
    import api.main as _main
    _main._scheduler.start = MagicMock(return_value=None)


_counter = itertools.count(1)


@pytest.fixture(autouse=True, scope="module")
def _fresh_db():
    n = next(_counter)
    _dbmod._test_db_uri = f"file:testdb_{n}?mode=memory&cache=shared"
    # init_db() opens _persistent_memory_conn to this URI, which is the
    # keepalive that prevents the named in-memory DB from being destroyed.
    # No separate keepalive connection is needed here — a 3rd idle connection
    # on the same shared-cache DB triggers SQLITE_LOCKED under test writes.
    init_db()
    run_all()
    yield
    _dbmod._test_db_uri = None
    # _persistent_memory_conn stays open; the next module's init_db() will
    # detect the URI change and recycle it onto a fresh testdb.


def auth_headers(role, parent_id=None, athlete_id=None):
    """Shared helper: mint a valid session token for a test caller and return
    it as a ready-to-use requests/TestClient headers dict. role is 'parent' or
    'athlete'. Import as `from tests.conftest import auth_headers`."""
    from api.services.session_auth import mint_session_token
    token = mint_session_token(role=role, parent_id=parent_id, athlete_id=athlete_id)
    return {"Authorization": f"Bearer {token}"}
