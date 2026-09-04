"""Tests for db/postgres/005_athlete_unlink.sql -- athlete_unlink_log, the
audit trail for parent-initiated athlete unlink (docs/planning/
parent-initiated-athlete-unlink.md). Mirrors tests/test_phase6_migration.py's
fixture conventions."""
import os
os.environ["DB_PATH"] = ":memory:"

import psycopg
import pytest
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app  # noqa: F401


@pytest.fixture
def db():
    conn = get_conn()
    init_db()
    run_all()
    conn.execute("DELETE FROM athlete_unlink_log")
    conn.execute("DELETE FROM athletes")
    conn.execute("DELETE FROM parents")
    conn.commit()
    yield conn
    conn.close()


def _make_parent(conn, email="p@example.com"):
    return conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES ('P', %s, sqlite_now(), TRUE) RETURNING id", (email,)
    ).fetchone()["id"]


def _make_athlete(conn, parent_id, first_name="A"):
    return conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, %s, 15, 'girl', 110, 5, 6) RETURNING id", (parent_id, first_name)
    ).fetchone()["id"]


def test_athlete_unlink_log_table_exists_with_expected_columns(db):
    rows = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'athlete_unlink_log'"
    ).fetchall()
    cols = {dict(r)["column_name"] for r in rows}
    assert cols == {"id", "athlete_id", "actor_parent_id", "created_at"}


def test_athlete_unlink_log_requires_athlete_and_actor(db):
    with pytest.raises(psycopg.errors.NotNullViolation):
        db.execute("INSERT INTO athlete_unlink_log (actor_parent_id) VALUES (1)")
    db.rollback()
    with pytest.raises(psycopg.errors.NotNullViolation):
        db.execute("INSERT INTO athlete_unlink_log (athlete_id) VALUES (1)")
    db.rollback()


def test_athlete_unlink_log_rejects_unknown_athlete_or_parent(db):
    parent_id = _make_parent(db, "fk1@example.com")
    db.commit()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute(
            "INSERT INTO athlete_unlink_log (athlete_id, actor_parent_id) VALUES (999999, %s)",
            (parent_id,),
        )
    db.rollback()
    athlete_id = _make_athlete(db, parent_id)
    db.commit()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute(
            "INSERT INTO athlete_unlink_log (athlete_id, actor_parent_id) VALUES (%s, 999999)",
            (athlete_id,),
        )
    db.rollback()


def test_athlete_unlink_log_cascades_on_athlete_delete(db):
    parent_id = _make_parent(db, "fk2@example.com")
    athlete_id = _make_athlete(db, parent_id)
    db.commit()
    db.execute(
        "INSERT INTO athlete_unlink_log (athlete_id, actor_parent_id) VALUES (%s, %s)",
        (athlete_id, parent_id),
    )
    db.commit()
    db.execute("DELETE FROM athletes WHERE id = %s", (athlete_id,))
    db.commit()
    row = db.execute(
        "SELECT COUNT(*) c FROM athlete_unlink_log WHERE athlete_id = %s", (athlete_id,)
    ).fetchone()
    assert dict(row)["c"] == 0
