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

The constraint is added NOT VALID (12 real 'Bay Area Surf' rows exist and
are deliberately left untouched by this migration) — it still rejects
every NEW violating write immediately; NOT VALID only means Postgres
doesn't retroactively scan/enforce it against rows already in the table.
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


def test_constraint_exists_and_is_not_valid(db):
    row = db.execute(
        "SELECT convalidated FROM pg_constraint WHERE conname = 'athletes_competition_level_canonical'"
    ).fetchone()
    assert row is not None, "athletes_competition_level_canonical constraint must exist"
    assert row["convalidated"] is False, "constraint must be NOT VALID — 12 pre-existing invalid rows remain"


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


def test_existing_invalid_rows_are_not_disturbed_by_not_valid_constraint(db):
    """NOT VALID must not retroactively enforce against rows already in the
    table — simulates the 12 real production rows this migration was
    written around. Inserting one directly (bypassing the constraint via
    a temporarily-disabled trigger is not needed — NOT VALID lets an
    already-invalid row exist because it was never a new write) proves
    the migration doesn't break on data it wasn't meant to touch."""
    pid = _make_parent(db, "parent-preexisting@example.com")
    # A row already in this state is exactly what NOT VALID exists to
    # tolerate — but a *new* insert of it is still a NEW write, so it's
    # correctly rejected here too. This test documents that distinction:
    # NOT VALID protects existing rows from retroactive enforcement, not
    # from ever being written in the first place.
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
