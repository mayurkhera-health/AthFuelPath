"""
Tests for db/postgres/003_auth_identities.sql — the auth_identities table
and its backfill from existing parents/athlete_logins rows.
"""
import os
os.environ["DB_PATH"] = ":memory:"

import os
import threading
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app  # noqa: F401 -- ensures app import side effects run once


@pytest.fixture
def db():
    conn = get_conn()
    init_db()
    run_all()
    conn.execute("DELETE FROM auth_identities")
    conn.execute("DELETE FROM athlete_logins")
    conn.execute("DELETE FROM athletes")
    conn.execute("DELETE FROM parents")
    conn.commit()
    yield conn
    conn.close()


def _make_parent(conn, email, full_name="Test Parent"):
    from datetime import datetime
    cur = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (full_name, email, datetime.utcnow().isoformat(), True),
    )
    row = cur.fetchone()
    conn.commit()
    return row["id"]


def _make_athlete_with_login(conn, parent_id, email, first_name="Alex"):
    cur = conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, %s, 14, 'Boy', 120, 5, 6) RETURNING id",
        (parent_id, first_name),
    )
    athlete_id = cur.fetchone()["id"]
    conn.execute(
        "INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)",
        (email, athlete_id),
    )
    conn.commit()
    return athlete_id


def test_auth_identities_table_exists_with_expected_columns(db):
    row = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'auth_identities'"
    ).fetchall()
    cols = {r["column_name"] for r in row}
    assert {"id", "provider", "provider_subject", "parent_id", "athlete_id",
            "email", "email_verified", "created_at", "updated_at"} <= cols


def test_ownership_invariant_rejects_both_parent_and_athlete(db):
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "alex@example.com")
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO auth_identities (provider, provider_subject, parent_id, athlete_id) "
            "VALUES ('email', 'both@example.com', %s, %s)",
            (pid, aid),
        )
        db.commit()
    db.rollback()


def test_ownership_invariant_rejects_neither_parent_nor_athlete(db):
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO auth_identities (provider, provider_subject) VALUES ('email', 'nobody@example.com')"
        )
        db.commit()
    db.rollback()


def test_duplicate_provider_subject_rejected(db):
    pid = _make_parent(db, "parent1@example.com")
    db.execute(
        "INSERT INTO auth_identities (provider, provider_subject, parent_id) VALUES ('email', 'dup@example.com', %s)",
        (pid,),
    )
    db.commit()
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO auth_identities (provider, provider_subject, parent_id) VALUES ('email', 'dup@example.com', %s)",
            (pid,),
        )
        db.commit()
    db.rollback()


def test_backfill_creates_one_identity_row_per_existing_parent(db):
    pid1 = _make_parent(db, "Parent1@Example.com")
    pid2 = _make_parent(db, "  parent2@example.com  ")
    _run_backfill(db)
    rows = db.execute(
        "SELECT provider_subject, parent_id FROM auth_identities WHERE provider = 'email' AND parent_id IS NOT NULL"
    ).fetchall()
    by_parent = {r["parent_id"]: r["provider_subject"] for r in rows}
    assert by_parent[pid1] == "parent1@example.com"
    assert by_parent[pid2] == "parent2@example.com"


def test_backfill_creates_one_identity_row_per_existing_athlete_login(db):
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "Alex@Example.com")
    _run_backfill(db)
    row = db.execute(
        "SELECT provider_subject FROM auth_identities WHERE provider = 'email' AND athlete_id = %s", (aid,)
    ).fetchone()
    assert row["provider_subject"] == "alex@example.com"


def test_backfill_fails_closed_on_unexpected_conflict_instead_of_silently_no_oping(db):
    """Correction (external review, 2026-08-24): the backfill INSERTs no
    longer carry ON CONFLICT (provider, provider_subject) DO NOTHING -- the
    preflight + LOCK TABLE upstream already guarantee collision-free source
    data by the time these run, so a real production run never re-executes
    the backfill for an already-applied migration (schema_migrations skips
    it). But if a conflict occurs anyway (e.g. a bug in that guarantee),
    this must now fail LOUDLY with a real unique-violation rather than
    silently omitting the identity row the way ON CONFLICT DO NOTHING used
    to.

    This test simulates that unexpected-conflict scenario directly: running
    the backfill INSERTs twice in a row is not something a correct migration
    run ever actually does (each migration file only runs once, tracked via
    schema_migrations), but it is the simplest, deterministic way to force
    exactly the conflict shape ON CONFLICT DO NOTHING used to paper over --
    proving the fail-closed property without needing to fabricate a real
    preflight-logic bug.

    Replaces the old test_backfill_is_idempotent, whose core assertion (two
    backfill runs silently produce the same row count) is no longer true and
    would now be actively wrong: with ON CONFLICT DO NOTHING removed, a
    second run raises instead of silently no-op'ing."""
    _make_parent(db, "parent1@example.com")
    _run_backfill(db)
    count_after_first = db.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()["c"]
    assert count_after_first == 1

    with pytest.raises(psycopg.errors.UniqueViolation):
        _run_backfill(db)
    db.rollback()

    # The failed second attempt must not have partially applied -- no new
    # rows, no silent duplicate-swallowing, no corruption of the first run's
    # result.
    count_after_failed_second = db.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()["c"]
    assert count_after_failed_second == 1


def test_migration_preflight_aborts_on_duplicate_normalized_parent_email(db):
    """Simulates production data drifting between planning and execution:
    a duplicate normalized parent email now exists. The migration's own
    execution-time preflight (the DO $$ ... RAISE EXCEPTION block in
    003_auth_identities.sql) must abort rather than guess an owner."""
    _make_parent(db, "Same@Example.com", full_name="Parent A")
    _make_parent(db, "same@example.com", full_name="Parent B")
    with pytest.raises(Exception, match="auth_identities backfill aborted"):
        _run_migration_preflight(db)


def test_migration_preflight_aborts_on_parent_athlete_email_overlap(db):
    pid = _make_parent(db, "shared@example.com")
    other_pid = _make_parent(db, "someone-else@example.com")
    _make_athlete_with_login(db, other_pid, "shared@example.com")
    with pytest.raises(Exception, match="auth_identities backfill aborted"):
        _run_migration_preflight(db)


def test_migration_preflight_passes_with_no_collisions(db):
    _make_parent(db, "parent1@example.com")
    _run_migration_preflight(db)  # must not raise
    db.rollback()


# The migration's actual preflight SQL (LOCK TABLE + the DO $$ ...
# RAISE EXCEPTION block) is read directly out of the real
# migration file rather than hand-retyped here, so these tests always
# exercise the literal production SQL -- editing the block in the .sql file
# can never silently drift out of sync with what the tests check.
_MIGRATION_SQL_PATH = Path(__file__).resolve().parent.parent / "db" / "postgres" / "003_auth_identities.sql"


def _read_preflight_sql() -> str:
    text = _MIGRATION_SQL_PATH.read_text()
    # Split on the actual CREATE TABLE statement, not just the substring
    # "CREATE TABLE" -- the file's own comments mention "CREATE TABLE" in
    # prose (e.g. "aborts the entire file (CREATE TABLE included...)"),
    # which would otherwise truncate the extraction before it ever reaches
    # the SET TRANSACTION / DO $$ block.
    return text[: text.index("CREATE TABLE auth_identities")]


def _run_migration_preflight(conn):
    conn.execute(_read_preflight_sql())


def test_normalize_email_strips_ascii_spaces_and_lowercases(db):
    """Correction (external review, 2026-08-24, round 3): normalize_email()
    is the ONE canonical DB-side normalization function, matching Python's
    .strip().lower() more closely than plain trim()/lower() alone. Ordinary
    leading/trailing ASCII space (0x20), combined with mixed capitalization."""
    row = db.execute("SELECT normalize_email('  Foo@Example.com  ') AS n").fetchone()
    assert row["n"] == "foo@example.com"


def test_normalize_email_strips_tabs():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT normalize_email(chr(9) || 'Foo@Example.com' || chr(9)) AS n"
        ).fetchone()
        assert row["n"] == "foo@example.com"
    finally:
        conn.rollback()
        conn.close()


def test_normalize_email_strips_newlines_and_carriage_returns():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT normalize_email(chr(10) || 'Foo@Example.com' || chr(13) || chr(10)) AS n"
        ).fetchone()
        assert row["n"] == "foo@example.com"
    finally:
        conn.rollback()
        conn.close()


def test_normalize_email_strips_non_breaking_space():
    """Postgres's plain trim() only strips ASCII space (0x20) by default --
    it does NOT strip U+00A0 (non-breaking space). normalize_email() must,
    since Python's str.strip() does."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT normalize_email(chr(160) || 'Foo@Example.com' || chr(160)) AS n"
        ).fetchone()
        assert row["n"] == "foo@example.com"
    finally:
        conn.rollback()
        conn.close()


def test_normalize_email_handles_mixed_whitespace_and_capitalization_together():
    """All required whitespace classes (ASCII space, tab, CR, LF, NBSP)
    combined with mixed capitalization in a single value -- proving the
    character class covers all of them simultaneously, not just in
    isolation."""
    conn = get_conn()
    try:
        mixed = "  " + chr(9) + "FOO@EXAMPLE.COM" + chr(13) + chr(10) + chr(160) + "  "
        row = conn.execute("SELECT normalize_email(%s) AS n", (mixed,)).fetchone()
        assert row["n"] == "foo@example.com"
    finally:
        conn.rollback()
        conn.close()


def test_set_local_lock_timeout_is_transaction_scoped(db):
    """Correction (external review, 2026-08-24): 003_auth_identities.sql now
    runs `SET LOCAL lock_timeout = '10s'` immediately before its
    `LOCK TABLE ... IN SHARE MODE`. SET LOCAL must be genuinely scoped to
    the current transaction only -- reverting automatically when that
    transaction ends -- never leaking out as a session-wide setting the way
    plain SET would. This is specifically why SET LOCAL (not SET) is
    required there. Confirmed directly against real Postgres: set it inside
    a transaction, observe it takes effect, end the transaction, observe it
    is gone again on the SAME connection/session."""
    db.execute("SET LOCAL lock_timeout = '10s'")
    within_txn = db.execute("SHOW lock_timeout").fetchone()
    assert within_txn["lock_timeout"] == "10s"

    db.rollback()  # ends the transaction SET LOCAL was scoped to

    after_txn = db.execute("SHOW lock_timeout").fetchone()
    assert after_txn["lock_timeout"] != "10s", (
        "lock_timeout leaked past the transaction that SET LOCAL it -- "
        "SET LOCAL is supposed to be transaction-local, not session-wide"
    )


def _drop_database_with_retry(maint_conn, db_name: str, *, attempts: int = 3, backoff_seconds: float = 2.0) -> None:
    """Best-effort cleanup for the throwaway database, hardened (external
    review, 2026-08-24, round 4) against a specific race: in the exact
    regression scenario test_migration_rolls_back_and_does_not_record_
    version_3_when_lock_times_out exists to catch (the migration's own SET
    LOCAL lock_timeout removed/broken), the abandoned background thread is
    still parked inside a blocking LOCK TABLE call when this cleanup runs.
    Releasing the blocker's lock (in the caller's finally block, just before
    this runs) lets that abandoned thread resume asynchronously in the
    background -- so DROP DATABASE can race a connection that hasn't
    detached yet and fail with "database is being accessed by other users"
    (psycopg.errors.ObjectInUse, SQLSTATE 55006). A single unretried
    DROP DATABASE attempt wrapped in a bare `except: pass` would then leak a
    real orphaned throwaway database with no error at all -- exactly the
    failure mode this retry exists to close.

    Retries a small bounded number of times with a short backoff on
    ObjectInUse specifically. Any other exception, or exhausting all
    retries, is NOT silently swallowed -- it's printed clearly so a
    maintainer can find and manually clean up the named orphaned database
    rather than it vanishing invisibly."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            maint_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            return
        except psycopg.errors.ObjectInUse as exc:
            last_exc = exc
            if attempt < attempts:
                time.sleep(backoff_seconds)
        except Exception as exc:  # noqa: BLE001 -- must surface, not swallow
            print(
                f"WARNING: failed to drop throwaway test database {db_name!r} "
                f"during cleanup (unexpected error, not retried): {exc!r}. "
                f"This database may be orphaned -- manual cleanup may be required."
            )
            return

    print(
        f"WARNING: could not drop throwaway test database {db_name!r} after "
        f"{attempts} attempts -- still in use by another session (last error: "
        f"{last_exc!r}). This database is likely ORPHANED -- manual cleanup "
        f"(DROP DATABASE {db_name!r}) may be required."
    )


def test_migration_rolls_back_and_does_not_record_version_3_when_lock_times_out():
    """Correction (external review, 2026-08-24), part 2: a real lock timeout
    must cause the ENTIRE migration 003 file to roll back -- no
    auth_identities table, no schema_migrations row for version 3 -- rather
    than partially applying, and it must fail within roughly the configured
    10s rather than hanging indefinitely.

    This is a real, automated test against actual PostgreSQL using two
    genuinely separate connections (mirrors this suite's only other
    multi-connection precedent: there is none in tests/conftest.py, so this
    test manages its own throwaway database and both connections directly,
    matching how psycopg is used everywhere else in this codebase --
    api.database.get_conn() -- rather than inventing a new pattern):

      1. Spin up a throwaway database and apply migrations 001 and 002 only
         (mirrors run_migrations' own per-file loop, stopped short of 003),
         so `parents`/`athlete_logins` exist but 003 has not run yet.
      2. Hold a conflicting ACCESS EXCLUSIVE lock on `parents` from a
         second, separate, uncommitted transaction -- exactly what 003's
         LOCK TABLE ... IN SHARE MODE has to wait behind.
      3. Run the real, unmodified db.postgres_migrate.run_migrations() (the
         actual production migration runner) against that database and
         confirm it raises within ~10s rather than hanging, then confirm
         nothing from migration 003 survived.

    Correction (external review, 2026-08-24, round 3): run_migrations() is
    invoked in a background daemon thread, joined with a generous but
    FINITE timeout (30s -- well above the migration's own 10s lock_timeout,
    but still bounded). If the migration's own SET LOCAL lock_timeout ever
    regresses (removed, or reordered after LOCK TABLE), Postgres itself
    would then impose no timeout and the direct call used previously could
    hang this test indefinitely, since the lock-holding second connection
    never releases within the test. With the bounded join, that regression
    now surfaces as a loud, explicit pytest.fail() instead of a hang -- and
    the thread being a daemon means even that failure case doesn't hang the
    pytest process at exit waiting on a stuck thread."""
    db_name = f"athfuelpath_test_locktimeout_{uuid.uuid4().hex[:8]}"
    maint = psycopg.connect("dbname=postgres", autocommit=True)
    db_created = False
    try:
        try:
            maint.execute(f'CREATE DATABASE "{db_name}"')
            db_created = True
        except psycopg.errors.InsufficientPrivilege as exc:
            # Narrowed (external review, 2026-08-24, round 3): skip ONLY for
            # the specific, expected "role lacks CREATEDB" condition --
            # Postgres SQLSTATE 42501, which psycopg3 maps to
            # psycopg.errors.InsufficientPrivilege. Any other failure here
            # (connectivity, malformed SQL, an unexpected Postgres error, a
            # programming error) must propagate and FAIL the test loudly --
            # it must never be silently swallowed as an environment quirk.
            pytest.skip(f"role lacks CREATEDB privilege in this environment: {exc}")

        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"dbname={db_name}"
        blocker = None
        try:
            from db.postgres_migrate import (
                _discover_migrations,
                _ensure_schema_migrations_table,
                run_migrations,
            )

            # Apply 001 + 002 only, so parents/athlete_logins exist but 003
            # has not run yet.
            setup_conn = get_conn()
            try:
                _ensure_schema_migrations_table(setup_conn)
                for version, path in _discover_migrations():
                    if version >= 3:
                        continue
                    setup_conn.execute(path.read_text())
                    setup_conn.execute(
                        "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s)",
                        (version, path.name),
                    )
                    setup_conn.commit()
            finally:
                setup_conn.close()

            # Hold a conflicting lock on `parents` from a second, separate,
            # uncommitted connection/transaction.
            blocker = get_conn()
            blocker.execute("LOCK TABLE parents IN ACCESS EXCLUSIVE MODE")

            # Thread targets don't propagate exceptions to the joining
            # thread automatically -- stash whatever run_migrations() does
            # (return value or raised exception) in this small mutable
            # container so the main test thread can inspect it after join().
            result_box = []

            def _run():
                try:
                    run_migrations(quiet=True)
                    result_box.append(("ok", None))
                except BaseException as exc:  # noqa: BLE001 -- must capture
                    # any exception shape run_migrations can raise, not
                    # just a chosen subset, since the assertions below
                    # inspect it.
                    result_box.append(("error", exc))

            thread = threading.Thread(target=_run, daemon=True)
            start = time.monotonic()
            thread.start()
            thread.join(timeout=30)
            elapsed = time.monotonic() - start

            if thread.is_alive():
                # The migration hung past a generous 30s bound (well above
                # its own 10s lock_timeout) -- this means the migration's
                # own SET LOCAL lock_timeout has regressed (removed, or
                # reordered after LOCK TABLE), so Postgres itself is no
                # longer bounding the wait. Fail loudly rather than let the
                # test hang further or silently pass; the thread is a
                # daemon so the pytest process itself won't hang at exit
                # waiting on it.
                pytest.fail(
                    "run_migrations() did not return within 30s -- the "
                    "migration's own SET LOCAL lock_timeout appears to have "
                    "regressed (removed, or reordered after LOCK TABLE), so "
                    "Postgres is no longer bounding the LOCK TABLE wait."
                )

            assert result_box, "background thread finished without recording a result"
            outcome, error = result_box[0]
            assert outcome == "error", (
                f"expected run_migrations() to raise a lock-timeout error, but it "
                f"returned normally"
            )
            excinfo = error

            # Bounded wait, not an indefinite hang: raised at roughly the
            # 10s lock_timeout (generous window for CI/machine variance),
            # not immediately and not after minutes.
            assert 5 <= elapsed <= 60, f"expected a ~10s lock_timeout, took {elapsed:.1f}s"
            assert "lock" in str(excinfo).lower(), (
                f"expected a lock-not-available-shaped error, got: {excinfo!r}"
            )

            # Whole-file rollback confirmed: neither the CREATE TABLE nor
            # the schema_migrations bookkeeping for version 3 survived.
            check_conn = get_conn()
            try:
                table_exists = check_conn.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'auth_identities'"
                ).fetchone()
                assert table_exists is None, (
                    "auth_identities must not exist after a rolled-back migration"
                )

                version_row = check_conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = 3"
                ).fetchone()
                assert version_row is None, (
                    "schema_migrations must not record version 3 after rollback"
                )
            finally:
                check_conn.close()
        finally:
            if blocker is not None:
                try:
                    blocker.rollback()
                except Exception:
                    pass
                try:
                    blocker.close()
                except Exception:
                    pass
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url
    finally:
        if db_created:
            _drop_database_with_retry(maint, db_name)
        maint.close()


# The migration's actual backfill SQL (the two INSERT ... SELECT statements)
# is read directly out of the real migration file, exactly like
# _read_preflight_sql() above does for the preflight block -- a hand-copied
# duplicate here previously drifted out of sync with the real file's switch
# to normalize_email() (external review, 2026-08-24, round 4) and stayed
# invisible because every test routing through it only used ASCII-space
# padding, where lower(trim(email)) and normalize_email(email) happen to
# agree. Slicing genuine file content instead of retyping it means this can
# never silently drift again.
_BACKFILL_MARKER = (
    "INSERT INTO auth_identities (provider, provider_subject, parent_id, email, email_verified)"
)


def _read_backfill_sql() -> str:
    text = _MIGRATION_SQL_PATH.read_text()
    return text[text.index(_BACKFILL_MARKER):]


def _run_backfill(conn):
    # No ON CONFLICT DO NOTHING -- kept in sync with the real migration file
    # (external review, 2026-08-24): the preflight + LOCK TABLE already
    # guarantee collision-free source data, so a conflict here should be
    # structurally impossible. If one occurs anyway, it must fail loudly
    # (raise a real UNIQUE-violation error) rather than silently no-op.
    conn.execute(_read_backfill_sql())
    conn.commit()
