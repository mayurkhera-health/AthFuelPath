"""
Tests for api/services/identity_resolver.py -- the common auth identity
resolution mechanism (auth v2.1 Phase 5).
"""
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime
from unittest.mock import patch

import psycopg
import pytest
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app  # noqa: F401
from api.services.identity_resolver import (
    resolve_identity,
    NoExistingAccount,
    AmbiguousIdentity,
    OwnerAlreadyLinkedToDifferentSubject,
    _resolve_exactly_one_owner,
    _resolve_exactly_one_parent_owner,
)


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
    """Two differently-cased provider_subject values are DISTINCT identity
    keys -- this function deliberately does not re-normalize (see
    docstring), and the DB constraint is plain case-sensitive TEXT.

    Corrected (Phase 6): uses two different owners rather than the same
    parent twice, since Phase 6's one-identity-per-provider-per-owner
    partial-unique index would otherwise reject a second Google identity
    for the same parent regardless of provider_subject casing -- that
    constraint is orthogonal to what this test is actually proving. Using
    two owners also makes this a strictly stronger test: it proves the
    exact-match lookup for "google-sub-123" does NOT accidentally hit the
    "Google-Sub-123" row just created for a DIFFERENT parent (which is
    exactly what a latent case-insensitive comparison bug would look
    like -- silently misattributing the second owner to the first)."""
    pid1 = _make_parent(db, "parent1@example.com")
    pid2 = _make_parent(db, "parent2@example.com")

    result1 = resolve_identity(
        provider="google", provider_subject="Google-Sub-123",
        email="parent1@example.com", email_verified=True,
    )
    assert result1.parent_id == pid1

    result2 = resolve_identity(
        provider="google", provider_subject="google-sub-123",
        email="parent2@example.com", email_verified=True,
    )
    assert result2.parent_id == pid2
    assert result2.parent_id != result1.parent_id

    count = db.execute(
        "SELECT COUNT(*) c FROM auth_identities WHERE provider = 'google'"
    ).fetchone()["c"]
    assert count == 2


def test_verified_email_auto_links_to_parent_with_whitespace_and_case_in_stored_email(db):
    """Correction (external review, 2026-08-24): the verified-email lookup
    must match the STORED parents.email using the same canonical
    normalize_email() rule the Task 1 migration/backfill uses -- not just
    lower(trim(...)). Real production rows can have surrounding whitespace
    from the FULL Unicode whitespace class Python's .strip() strips (plain
    SQL trim() only strips ASCII space 0x20), so this covers ASCII space,
    tab, newline/CR, and non-breaking space (U+00A0) padding individually,
    each combined with mixed capitalization. Simulates a future Google/Apple
    auto-link (provider="google") whose normalized `email` argument must
    still match a parent row stored with each of these paddings.

    Round-3 correction (2026-08-24): extended beyond plain ASCII-space
    padding specifically because a bare lower(trim(email)) DB-side
    comparison does NOT strip tabs/newlines/NBSP -- these sub-cases would
    FAIL to auto-link against the old lower(trim(email)) code and only PASS
    once the resolver's lookup uses normalize_email()."""
    pid_space = _make_parent(db, "  Parent1@Example.com  ", full_name="Space Parent")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-789",
        email="parent1@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid_space
    assert result.athlete_id is None

    pid_tab = _make_parent(db, "\tParent2@Example.com\t", full_name="Tab Parent")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-791",
        email="parent2@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid_tab

    pid_newline = _make_parent(db, "\nParent3@Example.com\r\n", full_name="Newline Parent")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-792",
        email="parent3@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid_newline

    pid_nbsp = _make_parent(db, " Parent4@Example.com ", full_name="NBSP Parent")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-793",
        email="parent4@example.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == pid_nbsp


def test_verified_email_auto_links_to_athlete_login_with_whitespace_and_case_in_stored_email(db):
    """Equivalent to the parent case above, but for athlete_logins.email --
    ASCII space, tab, newline/CR, and non-breaking space (U+00A0) padding,
    each combined with mixed capitalization."""
    pid = _make_parent(db, "parent1@example.com")

    aid_space = _make_athlete_with_login(db, pid, "  Alex@Example.com  ", first_name="SpaceAlex")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-790",
        email="alex@example.com", email_verified=True,
    )
    assert result.role == "athlete"
    assert result.athlete_id == aid_space
    assert result.parent_id is None

    aid_tab = _make_athlete_with_login(db, pid, "\tAlex2@Example.com\t", first_name="TabAlex")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-794",
        email="alex2@example.com", email_verified=True,
    )
    assert result.role == "athlete"
    assert result.athlete_id == aid_tab

    aid_newline = _make_athlete_with_login(db, pid, "\nAlex3@Example.com\r\n", first_name="NewlineAlex")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-795",
        email="alex3@example.com", email_verified=True,
    )
    assert result.role == "athlete"
    assert result.athlete_id == aid_newline

    aid_nbsp = _make_athlete_with_login(db, pid, " Alex4@Example.com ", first_name="NbspAlex")
    result = resolve_identity(
        provider="google", provider_subject="google-sub-796",
        email="alex4@example.com", email_verified=True,
    )
    assert result.role == "athlete"
    assert result.athlete_id == aid_nbsp


def test_percent_character_in_email_is_handled_safely(db):
    pid = _make_parent(db, "50%off+weird@example.com")
    result = resolve_identity(
        provider="email", provider_subject="50%off+weird@example.com",
        email="50%off+weird@example.com", email_verified=True,
    )
    assert result.parent_id == pid


# -- Phase 6: _resolve_exactly_one_owner / _resolve_exactly_one_parent_owner --
# Read-only building block factored out of resolve_identity()'s auto-link
# step, for Apple's credential-first flow (see Phase 6 plan, Part A.8/F).


def _auth_identities_count(conn):
    return conn.execute("SELECT COUNT(*) c FROM auth_identities").fetchone()["c"]


def test_resolve_exactly_one_owner_matches_a_single_parent_and_does_not_write(db):
    pid = _make_parent(db, "parent1@example.com")
    count_before = _auth_identities_count(db)
    role, parent_id, athlete_id = _resolve_exactly_one_owner(
        "parent1@example.com", email_verified=True
    )
    assert (role, parent_id, athlete_id) == ("parent", pid, None)
    assert _auth_identities_count(db) == count_before


def test_resolve_exactly_one_owner_matches_a_single_athlete_and_does_not_write(db):
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "alex@example.com")
    count_before = _auth_identities_count(db)
    role, parent_id, athlete_id = _resolve_exactly_one_owner(
        "alex@example.com", email_verified=True
    )
    assert (role, parent_id, athlete_id) == ("athlete", None, aid)
    assert _auth_identities_count(db) == count_before


def test_resolve_exactly_one_owner_zero_matches_raises_no_existing_account(db):
    count_before = _auth_identities_count(db)
    with pytest.raises(NoExistingAccount):
        _resolve_exactly_one_owner("nobody@example.com", email_verified=True)
    assert _auth_identities_count(db) == count_before


def test_resolve_exactly_one_owner_ambiguous_match_raises_ambiguous_identity(db):
    pid = _make_parent(db, "shared@example.com")
    other_parent = _make_parent(db, "someone-else@example.com")
    _make_athlete_with_login(db, other_parent, "shared@example.com")
    count_before = _auth_identities_count(db)
    with pytest.raises(AmbiguousIdentity):
        _resolve_exactly_one_owner("shared@example.com", email_verified=True)
    assert _auth_identities_count(db) == count_before


def test_resolve_exactly_one_owner_unverified_email_raises_no_existing_account(db):
    """Even though a matching parent exists, email_verified=False must fail
    closed -- mirrors resolve_identity()'s own gating."""
    _make_parent(db, "parent1@example.com")
    count_before = _auth_identities_count(db)
    with pytest.raises(NoExistingAccount):
        _resolve_exactly_one_owner("parent1@example.com", email_verified=False)
    assert _auth_identities_count(db) == count_before


def test_resolve_exactly_one_parent_owner_returns_parent_id(db):
    pid = _make_parent(db, "parent1@example.com")
    count_before = _auth_identities_count(db)
    result = _resolve_exactly_one_parent_owner("parent1@example.com")
    assert result == pid
    assert _auth_identities_count(db) == count_before


# -- Phase 6 corrective pass (external review): owner already linked to a
# DIFFERENT provider_subject for the same provider must fail closed with a
# typed exception, not let a raw UniqueViolation escape resolve_identity().


def test_owner_already_linked_to_different_google_subject_raises_typed_exception(db):
    """A parent already has a Google auth_identities row for subject_A. A
    NEW verified Google identity for subject_B, resolving by email to that
    SAME parent, must be rejected -- the per-owner-per-provider partial
    UNIQUE index rejects subject_B's insert, and the exact-subject re-fetch
    (which only looks for subject_B) finds nothing, so the resolver must
    raise the typed exception instead of letting the raw UniqueViolation
    propagate."""
    pid = _make_parent(db, "parent1@example.com")
    resolve_identity(
        provider="google", provider_subject="google-subject-A",
        email="parent1@example.com", email_verified=True,
    )
    count_before = _auth_identities_count(db)

    with pytest.raises(OwnerAlreadyLinkedToDifferentSubject):
        resolve_identity(
            provider="google", provider_subject="google-subject-B",
            email="parent1@example.com", email_verified=True,
        )

    # No new row created -- the conflicting insert was rolled back, and
    # nothing else was written in its place.
    assert _auth_identities_count(db) == count_before
    row = db.execute(
        "SELECT 1 FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-subject-B'"
    ).fetchone()
    assert row is None
    # The original mapping is untouched.
    original = db.execute(
        "SELECT parent_id FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-subject-A'"
    ).fetchone()
    assert original["parent_id"] == pid


def test_athlete_owner_already_linked_to_different_google_subject_raises_typed_exception(db):
    """Same conflict as above, but for an athlete owner."""
    pid = _make_parent(db, "parent1@example.com")
    aid = _make_athlete_with_login(db, pid, "alex@example.com")
    resolve_identity(
        provider="google", provider_subject="google-athlete-subject-A",
        email="alex@example.com", email_verified=True,
    )
    count_before = _auth_identities_count(db)

    with pytest.raises(OwnerAlreadyLinkedToDifferentSubject):
        resolve_identity(
            provider="google", provider_subject="google-athlete-subject-B",
            email="alex@example.com", email_verified=True,
        )

    assert _auth_identities_count(db) == count_before
    row = db.execute(
        "SELECT 1 FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-athlete-subject-B'"
    ).fetchone()
    assert row is None
    original = db.execute(
        "SELECT athlete_id FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-athlete-subject-A'"
    ).fetchone()
    assert original["athlete_id"] == aid


def test_concurrent_identical_resolve_exact_same_subject_race_remains_benign(db):
    """The pre-existing benign race this except block was originally built
    for (Phase 5): two concurrent resolve_identity() calls for the EXACT
    SAME (provider, provider_subject) both attempt the auto-link insert; one
    wins, the other hits UniqueViolation. The loser's exact-subject re-fetch
    DOES find a row (the winner's), so it must return that result normally
    -- never raise OwnerAlreadyLinkedToDifferentSubject, never raise at all.
    This corrective pass must not weaken this existing behavior."""
    pid = _make_parent(db, "parent1@example.com")

    real_execute = psycopg.Connection.execute

    def flaky_execute(self, query, *args, **kwargs):
        text = str(query)
        if "INSERT INTO auth_identities" in text:
            # Simulate a concurrent identical request winning the race
            # first -- on a SEPARATE connection/transaction, so it commits
            # independently and survives this connection's own rollback --
            # then this connection's own insert collides with it.
            winner_conn = get_conn()
            try:
                real_execute(
                    winner_conn,
                    "INSERT INTO auth_identities "
                    "(provider, provider_subject, parent_id, athlete_id, email, email_verified) "
                    "VALUES ('google', 'google-subject-shared', %s, NULL, %s, TRUE)",
                    (pid, "parent1@example.com"),
                )
                winner_conn.commit()
            finally:
                winner_conn.close()
            raise psycopg.errors.UniqueViolation("simulated concurrent identical insert")
        return real_execute(self, query, *args, **kwargs)

    with patch.object(psycopg.Connection, "execute", flaky_execute):
        result = resolve_identity(
            provider="google", provider_subject="google-subject-shared",
            email="parent1@example.com", email_verified=True,
        )

    assert result.role == "parent"
    assert result.parent_id == pid
    count = db.execute(
        "SELECT COUNT(*) c FROM auth_identities WHERE provider = 'google' AND provider_subject = 'google-subject-shared'"
    ).fetchone()["c"]
    assert count == 1


def test_resolve_exactly_one_parent_owner_rejects_an_athlete_match(db):
    """This flow (Hide-My-Email linking) is explicitly parent-scoped --
    an athlete-only match has no use here and must raise NoExistingAccount,
    per the function's docstring."""
    pid = _make_parent(db, "parent1@example.com")
    _make_athlete_with_login(db, pid, "alex@example.com")
    count_before = _auth_identities_count(db)
    with pytest.raises(NoExistingAccount):
        _resolve_exactly_one_parent_owner("alex@example.com")
    assert _auth_identities_count(db) == count_before
