"""
Tests for db/postgres/005_competition_level_check_constraint.sql — the
database-level guardrail on athletes.competition_level, defense-in-depth
alongside the API-level validation in fix/competition-level-validation
(api/services/competition_level.py).

These exercise the actual Postgres CHECK constraint directly via raw SQL —
NOT the Pydantic validators (see tests/test_competition_level.py and
tests/test_admin_users.py for those). The point is proving a direct SQL/
bulk/admin-console write that bypasses the API entirely — exactly how the
2026-07-22 "Bay Area Surf" incident happened — is now blocked by the
database itself, not just by application code that could again be
skipped or have a gap in it.

db/postgres/005_competition_level_check_constraint.sql originally added the
constraint NOT VALID: at that point 12 real 'Bay Area Surf' rows existed and
were deliberately left untouched, since NOT VALID rejects every NEW
violating write immediately without retroactively scanning existing rows.
Those 12 rows were subsequently corrected to canonical values (a separate,
reviewed data-repair task), and
db/postgres/006_validate_competition_level_constraint.sql then ran
VALIDATE CONSTRAINT — the constraint is now fully validated
(convalidated = true) and enforced against every row in the table, not
just new writes.
"""
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

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
    conn.execute("DELETE FROM athletes")
    conn.execute("DELETE FROM parents")
    conn.commit()
    yield conn
    conn.close()


def _make_parent(conn, email):
    cur = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        ("Test Parent", email, datetime.utcnow().isoformat(), True),
    )
    row = cur.fetchone()
    conn.commit()
    return row["id"]


def _insert_athlete(conn, parent_id, competition_level):
    conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, "
        "competition_level) VALUES (%s, 'A', 14, 'Boy', 120, 5, 6, %s)",
        (parent_id, competition_level),
    )
    conn.commit()


def test_constraint_exists_and_is_validated(db):
    row = db.execute(
        "SELECT convalidated FROM pg_constraint WHERE conname = 'athletes_competition_level_canonical'"
    ).fetchone()
    assert row is not None, "athletes_competition_level_canonical constraint must exist"
    assert row["convalidated"] is True, (
        "constraint must be VALID — migration 006 validated it once the 12 "
        "pre-existing invalid rows were corrected"
    )


@pytest.mark.parametrize("value", ["recreational", "competitive_club", "elite_club"])
def test_canonical_values_insert_successfully(db, value):
    pid = _make_parent(db, f"parent-{value}@example.com")
    _insert_athlete(db, pid, value)  # must not raise
    row = db.execute("SELECT competition_level FROM athletes WHERE parent_id = %s", (pid,)).fetchone()
    assert row["competition_level"] == value


def test_null_insert_succeeds(db):
    pid = _make_parent(db, "parent-null@example.com")
    _insert_athlete(db, pid, None)  # must not raise
    row = db.execute("SELECT competition_level FROM athletes WHERE parent_id = %s", (pid,)).fetchone()
    assert row["competition_level"] is None


@pytest.mark.parametrize("value", ["Bay Area Surf", "Soccer Club", "Competitive Team", "made up nonsense", "Elite Club"])
def test_non_canonical_values_rejected_directly_by_postgres(db, value):
    """Bypasses the API entirely — direct SQL, exactly like the real
    incident. The database itself must refuse the write."""
    pid = _make_parent(db, f"parent-reject-{abs(hash(value))}@example.com")
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_athlete(db, pid, value)
    db.rollback()


def test_new_write_of_the_historical_bad_value_is_still_rejected(db):
    """Historically (migration 005, before 006 validated the constraint),
    the 12 real 'Bay Area Surf' rows were tolerated in-place by NOT VALID
    while any *new* write of that same value was still rejected — NOT
    VALID only skips retroactively scanning rows already in the table, it
    never exempts new writes. Now that migration 006 has fully validated
    the constraint, every row is enforced, so this same write is rejected
    for the simpler reason too. This test just proves 'Bay Area Surf'
    can never be written again, under either constraint state."""
    pid = _make_parent(db, "parent-preexisting@example.com")
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_athlete(db, pid, "Bay Area Surf")
    db.rollback()


def test_update_to_invalid_value_also_rejected(db):
    """The constraint applies to UPDATE, not just INSERT."""
    pid = _make_parent(db, "parent-update@example.com")
    _insert_athlete(db, pid, "recreational")
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "UPDATE athletes SET competition_level = %s WHERE parent_id = %s",
            ("Bay Area Surf", pid),
        )
    db.rollback()
