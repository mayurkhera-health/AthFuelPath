"""
Tests for db/postgres/004_phase6_provider_auth.sql -- the Phase 6 additive
migration that (1) closes the "multiple identities per owner per provider"
gap on auth_identities via two new partial-unique indexes, and (2) adds
three new small tables: provider_auth_challenges (server-issued nonce
ledger), apple_provider_credentials (encrypted Apple refresh tokens), and
apple_pending_links (short-lived Hide-My-Email linking state).

Mirrors tests/test_auth_identities_migration.py's fixture/helper
conventions exactly (the `db` fixture, _make_parent, _make_athlete_with_login).
This migration has no data-migration/backfill step and no fail-closed
preflight DO $$ block of its own (see A.3/Part E of the Phase 6 plan --
CREATE UNIQUE INDEX itself fails loudly on any pre-existing violation,
which is already fail-closed by construction) -- so, unlike
test_auth_identities_migration.py, there is no _read_preflight_sql()/
_read_backfill_sql() equivalent here. Straightforward direct SQL against
the already-migrated test DB (conftest.py's session-scoped migration
fixture, same as 003's tests use) is the right approach for every test
below.
"""
import os
os.environ["DB_PATH"] = ":memory:"

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
    conn.execute("DELETE FROM apple_pending_links")
    conn.execute("DELETE FROM apple_provider_credentials")
    conn.execute("DELETE FROM provider_auth_challenges")
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


def _make_auth_identity(conn, provider, provider_subject, *, parent_id=None, athlete_id=None,
                         email=None, email_verified=False):
    cur = conn.execute(
        "INSERT INTO auth_identities (provider, provider_subject, parent_id, athlete_id, email, email_verified) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (provider, provider_subject, parent_id, athlete_id, email, email_verified),
    )
    row = cur.fetchone()
    conn.commit()
    return row["id"]


# --- 1. Table/column existence -----------------------------------------

def test_provider_auth_challenges_table_exists_with_expected_columns(db):
    rows = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'provider_auth_challenges'"
    ).fetchall()
    cols = {r["column_name"] for r in rows}
    assert {"id", "challenge_id", "provider", "raw_nonce", "expires_at", "consumed_at", "created_at"} <= cols


def test_apple_provider_credentials_table_exists_with_expected_columns(db):
    rows = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'apple_provider_credentials'"
    ).fetchall()
    cols = {r["column_name"] for r in rows}
    assert {"id", "auth_identity_id", "encrypted_refresh_token", "encryption_nonce", "created_at"} <= cols


def test_apple_pending_links_table_exists_with_expected_columns(db):
    rows = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'apple_pending_links'"
    ).fetchall()
    cols = {r["column_name"] for r in rows}
    assert {
        "id", "pending_link_id", "provider_subject", "email_from_token",
        "email_verified_from_token", "encrypted_refresh_token", "encryption_nonce",
        "expires_at", "consumed_at", "created_at",
    } <= cols


# --- 2. provider_auth_challenges CHECK(provider) -------------------------

def test_provider_auth_challenges_check_rejects_unknown_provider(db):
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO provider_auth_challenges (challenge_id, provider, raw_nonce, expires_at) "
            "VALUES ('chal-1', 'facebook', 'nonce-1', now() + interval '5 minutes')"
        )
        db.commit()
    db.rollback()


def test_provider_auth_challenges_check_accepts_google_and_apple(db):
    db.execute(
        "INSERT INTO provider_auth_challenges (challenge_id, provider, raw_nonce, expires_at) "
        "VALUES ('chal-google', 'google', 'nonce-1', now() + interval '5 minutes')"
    )
    db.execute(
        "INSERT INTO provider_auth_challenges (challenge_id, provider, raw_nonce, expires_at) "
        "VALUES ('chal-apple', 'apple', 'nonce-2', now() + interval '5 minutes')"
    )
    db.commit()
    count = db.execute("SELECT COUNT(*) c FROM provider_auth_challenges").fetchone()["c"]
    assert count == 2


# --- 3. New partial-unique indexes on auth_identities --------------------

def test_one_identity_per_provider_per_parent_rejects_second_google_identity(db):
    pid = _make_parent(db, "parent1@example.com")
    _make_auth_identity(db, "google", "google-sub-1", parent_id=pid)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _make_auth_identity(db, "google", "google-sub-2", parent_id=pid)
    db.rollback()


def test_one_identity_per_provider_per_athlete_rejects_second_google_identity(db):
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "alex@example.com")
    _make_auth_identity(db, "google", "google-sub-athlete-1", athlete_id=aid)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _make_auth_identity(db, "google", "google-sub-athlete-2", athlete_id=aid)
    db.rollback()


def test_same_parent_can_have_one_google_and_one_apple_identity(db):
    """Positive case proving the new indexes are scoped per-provider, not
    "one identity total" -- a parent may legitimately have both a Google
    identity and an Apple identity simultaneously; only a SECOND identity
    for the SAME provider is rejected."""
    pid = _make_parent(db, "parent1@example.com")
    google_id = _make_auth_identity(db, "google", "google-sub-1", parent_id=pid)
    apple_id = _make_auth_identity(db, "apple", "apple-sub-1", parent_id=pid)
    assert google_id != apple_id
    count = db.execute(
        "SELECT COUNT(*) c FROM auth_identities WHERE parent_id = %s", (pid,)
    ).fetchone()["c"]
    assert count == 2


# --- 4. apple_provider_credentials UNIQUE(auth_identity_id) --------------

def test_apple_provider_credentials_unique_auth_identity_id(db):
    pid = _make_parent(db, "parent1@example.com")
    identity_id = _make_auth_identity(db, "apple", "apple-sub-1", parent_id=pid)
    db.execute(
        "INSERT INTO apple_provider_credentials (auth_identity_id, encrypted_refresh_token, encryption_nonce) "
        "VALUES (%s, %s, %s)",
        (identity_id, b"ciphertext-1", b"nonce-1"),
    )
    db.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "INSERT INTO apple_provider_credentials (auth_identity_id, encrypted_refresh_token, encryption_nonce) "
            "VALUES (%s, %s, %s)",
            (identity_id, b"ciphertext-2", b"nonce-2"),
        )
        db.commit()
    db.rollback()


def test_apple_provider_credentials_cascades_on_auth_identity_delete(db):
    pid = _make_parent(db, "parent1@example.com")
    identity_id = _make_auth_identity(db, "apple", "apple-sub-1", parent_id=pid)
    db.execute(
        "INSERT INTO apple_provider_credentials (auth_identity_id, encrypted_refresh_token, encryption_nonce) "
        "VALUES (%s, %s, %s)",
        (identity_id, b"ciphertext-1", b"nonce-1"),
    )
    db.commit()
    db.execute("DELETE FROM auth_identities WHERE id = %s", (identity_id,))
    db.commit()
    remaining = db.execute(
        "SELECT COUNT(*) c FROM apple_provider_credentials WHERE auth_identity_id = %s", (identity_id,)
    ).fetchone()["c"]
    assert remaining == 0


# --- 5. apple_pending_links NOT NULL credential columns -------------------

def test_apple_pending_links_rejects_null_encrypted_refresh_token(db):
    """The single most important test in this file -- schema-level
    enforcement of the Phase 6 plan's round-4 correction (A.8): a pending
    link can only ever be created AFTER a successful, synchronous Apple
    authorization-code exchange, so a credential-less pending link must be
    structurally impossible, not merely avoided by application-layer
    discipline. If this NOT NULL constraint were ever accidentally dropped
    or weakened, this test would be the one that catches it."""
    with pytest.raises(psycopg.errors.NotNullViolation):
        db.execute(
            "INSERT INTO apple_pending_links "
            "(pending_link_id, provider_subject, email_verified_from_token, "
            " encrypted_refresh_token, encryption_nonce, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, now() + interval '15 minutes')",
            ("pending-1", "apple-sub-1", False, None, b"nonce-1"),
        )
        db.commit()
    db.rollback()


def test_apple_pending_links_rejects_null_encryption_nonce(db):
    """Same invariant as above, for the paired encryption_nonce column --
    both credential columns must independently be NOT NULL; a row that has
    ciphertext but no nonce (or vice versa) is just as structurally invalid
    as having neither."""
    with pytest.raises(psycopg.errors.NotNullViolation):
        db.execute(
            "INSERT INTO apple_pending_links "
            "(pending_link_id, provider_subject, email_verified_from_token, "
            " encrypted_refresh_token, encryption_nonce, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, now() + interval '15 minutes')",
            ("pending-2", "apple-sub-1", False, b"ciphertext-1", None),
        )
        db.commit()
    db.rollback()


# --- 6. A full valid apple_pending_links row inserts successfully --------

def test_apple_pending_links_full_valid_row_inserts_successfully(db):
    db.execute(
        "INSERT INTO apple_pending_links "
        "(pending_link_id, provider_subject, email_from_token, email_verified_from_token, "
        " encrypted_refresh_token, encryption_nonce, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, now() + interval '15 minutes')",
        ("pending-valid-1", "apple-sub-1", "hidden@privaterelay.appleid.com", True,
         b"real-ciphertext-bytes", b"real-nonce-bytes"),
    )
    db.commit()
    row = db.execute(
        "SELECT pending_link_id, provider_subject, email_from_token, email_verified_from_token, "
        "encrypted_refresh_token, encryption_nonce, consumed_at "
        "FROM apple_pending_links WHERE pending_link_id = %s",
        ("pending-valid-1",),
    ).fetchone()
    assert row is not None
    assert row["provider_subject"] == "apple-sub-1"
    assert row["email_from_token"] == "hidden@privaterelay.appleid.com"
    assert row["email_verified_from_token"] is True
    assert bytes(row["encrypted_refresh_token"]) == b"real-ciphertext-bytes"
    assert bytes(row["encryption_nonce"]) == b"real-nonce-bytes"
    assert row["consumed_at"] is None


# --- Duplicate-provider-subject reconfirmation (unaffected by new indexes) ---

def test_duplicate_provider_subject_still_rejected_for_new_providers(db):
    """Reconfirms Phase 5's pre-existing UNIQUE(provider, provider_subject)
    constraint still applies for the new 'google'/'apple' provider values --
    the Phase 6 migration adds NEW partial-unique indexes, it does not
    remove or weaken the original one."""
    pid1 = _make_parent(db, "parent1@example.com")
    pid2 = _make_parent(db, "parent2@example.com")
    _make_auth_identity(db, "google", "dup-google-sub", parent_id=pid1)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _make_auth_identity(db, "google", "dup-google-sub", parent_id=pid2)
    db.rollback()
