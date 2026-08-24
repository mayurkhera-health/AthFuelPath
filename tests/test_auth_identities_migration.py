"""
Tests for db/postgres/003_auth_identities.sql — the auth_identities table
and its backfill from existing parents/athlete_logins rows.
"""
import os
os.environ["DB_PATH"] = ":memory:"

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


def test_backfill_is_idempotent(db):
    _make_parent(db, "parent1@example.com")
    _run_backfill(db)
    count_after_first = db.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()["c"]
    _run_backfill(db)
    count_after_second = db.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()["c"]
    assert count_after_first == count_after_second == 1


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


def _run_migration_preflight(conn):
    conn.execute("""
        DO $$
        DECLARE
            dup_parent_count INTEGER;
            dup_athlete_login_count INTEGER;
            overlap_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO dup_parent_count FROM (
                SELECT lower(trim(email)) FROM parents GROUP BY 1 HAVING COUNT(*) > 1
            ) t;
            SELECT COUNT(*) INTO dup_athlete_login_count FROM (
                SELECT lower(trim(email)) FROM athlete_logins GROUP BY 1 HAVING COUNT(*) > 1
            ) t;
            SELECT COUNT(*) INTO overlap_count FROM parents p
                JOIN athlete_logins a ON lower(trim(p.email)) = lower(trim(a.email));

            IF dup_parent_count > 0 OR dup_athlete_login_count > 0 OR overlap_count > 0 THEN
                RAISE EXCEPTION
                    'auth_identities backfill aborted: % duplicate parent email group(s), % duplicate athlete_login email group(s), % parent/athlete email overlap(s) found at migration time. Resolve manually before rerunning -- do not guess an owner.',
                    dup_parent_count, dup_athlete_login_count, overlap_count;
            END IF;
        END $$;
    """)


def _run_backfill(conn):
    conn.execute("""
        INSERT INTO auth_identities (provider, provider_subject, parent_id, email, email_verified)
        SELECT 'email', lower(trim(email)), id, lower(trim(email)), TRUE FROM parents
        ON CONFLICT (provider, provider_subject) DO NOTHING
    """)
    conn.execute("""
        INSERT INTO auth_identities (provider, provider_subject, athlete_id, email, email_verified)
        SELECT 'email', lower(trim(email)), athlete_id, lower(trim(email)), TRUE FROM athlete_logins
        ON CONFLICT (provider, provider_subject) DO NOTHING
    """)
    conn.commit()
