"""
Tests for api/services/identity_resolver.py -- the common auth identity
resolution mechanism (auth v2.1 Phase 5).
"""
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

import pytest
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app  # noqa: F401
from api.services.identity_resolver import resolve_identity, NoExistingAccount, AmbiguousIdentity


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
    conn.execute("INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)", (email, athlete_id))
    conn.commit()
    return athlete_id


def test_verified_email_auto_links_to_the_one_matching_parent(db):
    pid = _make_parent(db, "parent1@example.com")
    result = resolve_identity(
        provider="email", provider_subject="parent1@example.com",
        email="parent1@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid
    assert result.athlete_id is None


def test_verified_email_auto_links_to_the_one_matching_athlete(db):
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "alex@example.com")
    result = resolve_identity(
        provider="email", provider_subject="alex@example.com",
        email="alex@example.com", email_verified=True,
    )
    assert result.role == "athlete"
    assert result.athlete_id == aid
    assert result.parent_id is None


def test_auto_link_creates_an_auth_identities_row_for_next_time(db):
    pid = _make_parent(db, "parent1@example.com")
    resolve_identity(
        provider="email", provider_subject="parent1@example.com",
        email="parent1@example.com", email_verified=True,
    )
    row = db.execute(
        "SELECT parent_id FROM auth_identities WHERE provider = 'email' AND provider_subject = 'parent1@example.com'"
    ).fetchone()
    assert row["parent_id"] == pid


def test_exact_provider_identity_match_is_authoritative_and_skips_email_lookup(db):
    pid = _make_parent(db, "parent1@example.com")
    db.execute(
        "INSERT INTO auth_identities (provider, provider_subject, parent_id, email, email_verified) "
        "VALUES ('email', 'parent1@example.com', %s, 'parent1@example.com', TRUE)", (pid,),
    )
    db.commit()
    result = resolve_identity(
        provider="email", provider_subject="parent1@example.com",
        email="parent1@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid


def test_existing_provider_identity_wins_over_a_changed_email_metadata(db):
    """Simulates a future Google/Apple case: the provider_subject already
    has a linked owner, but the email argument passed this time differs
    from what's stored. The existing mapping must win -- no relink."""
    pid = _make_parent(db, "parent1@example.com")
    db.execute(
        "INSERT INTO auth_identities (provider, provider_subject, parent_id, email, email_verified) "
        "VALUES ('google', 'google-sub-123', %s, 'old-email@example.com', TRUE)", (pid,),
    )
    db.commit()
    result = resolve_identity(
        provider="google", provider_subject="google-sub-123",
        email="brand-new-email@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid
    # The stored mapping's email metadata is untouched -- no relink, no update.
    row = db.execute(
        "SELECT email FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-sub-123'"
    ).fetchone()
    assert row["email"] == "old-email@example.com"


def test_unverified_email_cannot_auto_link(db):
    _make_parent(db, "parent1@example.com")
    with pytest.raises(NoExistingAccount):
        resolve_identity(
            provider="google", provider_subject="google-sub-456",
            email="parent1@example.com", email_verified=False,
        )
    row = db.execute(
        "SELECT 1 FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-sub-456'"
    ).fetchone()
    assert row is None


def test_no_matching_owner_raises_no_existing_account_and_creates_nothing(db):
    with pytest.raises(NoExistingAccount):
        resolve_identity(
            provider="email", provider_subject="nobody@example.com",
            email="nobody@example.com", email_verified=True,
        )
    row = db.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()
    assert row["c"] == 0


def test_ambiguous_email_match_fails_closed_and_creates_nothing(db):
    """Same normalized email exists as both a parent and an athlete login --
    structurally possible even though a 2026-08-24 production preflight
    found zero such cases today."""
    pid = _make_parent(db, "shared@example.com")
    other_parent = _make_parent(db, "someone-else@example.com")
    _make_athlete_with_login(db, other_parent, "shared@example.com")
    with pytest.raises(AmbiguousIdentity):
        resolve_identity(
            provider="email", provider_subject="shared@example.com",
            email="shared@example.com", email_verified=True,
        )
    row = db.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()
    assert row["c"] == 0


def test_an_identity_cannot_belong_to_both_parent_and_athlete_at_the_db_layer(db):
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "alex@example.com")
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO auth_identities (provider, provider_subject, parent_id, athlete_id) "
            "VALUES ('email', 'weird@example.com', %s, %s)", (pid, aid),
        )
        db.commit()
    db.rollback()


def test_duplicate_provider_and_provider_subject_is_prevented(db):
    pid = _make_parent(db, "parent1@example.com")
    resolve_identity(
        provider="email", provider_subject="parent1@example.com",
        email="parent1@example.com", email_verified=True,
    )
    # Second resolve for the exact same identity must hit the exact-match
    # path (step 1), not attempt a second insert.
    result = resolve_identity(
        provider="email", provider_subject="parent1@example.com",
        email="parent1@example.com", email_verified=True,
    )
    assert result.parent_id == pid
    count = db.execute(
        "SELECT COUNT(*) c FROM auth_identities WHERE provider = 'email' AND provider_subject = 'parent1@example.com'"
    ).fetchone()["c"]
    assert count == 1


def test_provider_subject_is_case_sensitive(db):
    """Two differently-cased provider_subject values for the same provider
    are DISTINCT identities -- this function deliberately does not
    re-normalize (see docstring), and the DB constraint is plain
    case-sensitive TEXT."""
    pid = _make_parent(db, "parent1@example.com")
    result1 = resolve_identity(
        provider="google", provider_subject="Google-Sub-123",
        email="parent1@example.com", email_verified=True,
    )
    result2 = resolve_identity(
        provider="google", provider_subject="google-sub-123",
        email="parent1@example.com", email_verified=True,
    )
    assert result1.parent_id == pid
    assert result2.parent_id == pid
    count = db.execute(
        "SELECT COUNT(*) c FROM auth_identities WHERE provider = 'google'"
    ).fetchone()["c"]
    assert count == 2


def test_verified_email_auto_links_to_parent_with_whitespace_and_case_in_stored_email(db):
    """Correction (external review, 2026-08-24): the verified-email lookup
    must match the STORED parents.email using the same lower(trim(...))
    normalization rule the Task 1 migration/backfill uses -- not just
    lower(...). Real production rows have surrounding whitespace that
    lower() alone doesn't strip. Simulates a future Google/Apple auto-link
    (provider="google") whose normalized `email` argument must still match a
    parent row stored with extra capitalization AND surrounding whitespace."""
    pid = _make_parent(db, "  Parent1@Example.com  ")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-789",
        email="parent1@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid
    assert result.athlete_id is None


def test_verified_email_auto_links_to_athlete_login_with_whitespace_and_case_in_stored_email(db):
    """Equivalent to the parent case above, but for athlete_logins.email."""
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "  Alex@Example.com  ")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-790",
        email="alex@example.com", email_verified=True,
    )
    assert result.role == "athlete"
    assert result.athlete_id == aid
    assert result.parent_id is None


def test_percent_character_in_email_is_handled_safely(db):
    pid = _make_parent(db, "50%off+weird@example.com")
    result = resolve_identity(
        provider="email", provider_subject="50%off+weird@example.com",
        email="50%off+weird@example.com", email_verified=True,
    )
    assert result.parent_id == pid
