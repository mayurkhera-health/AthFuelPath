"""Unit tests for api/services/session_auth.py — the HMAC session-token
mint/verify core, and the ownership-assertion helpers used across routes."""
import os
os.environ["DB_PATH"] = ":memory:"
os.environ.setdefault("APP_SESSION_SECRET", "test-secret-do-not-use-in-prod")

import time

import pytest
from fastapi import HTTPException

from api.services import session_auth as sa
from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn


@pytest.fixture
def db():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    yield keepalive
    keepalive.close()


def test_mint_and_verify_round_trip_parent():
    token = sa.mint_session_token(role="parent", parent_id=7)
    payload = sa.verify_session_token(token)
    assert payload == {"role": "parent", "parent_id": 7, "athlete_id": None, "exp": payload["exp"]}


def test_mint_and_verify_round_trip_athlete():
    token = sa.mint_session_token(role="athlete", athlete_id=42, parent_id=7)
    payload = sa.verify_session_token(token)
    assert payload["role"] == "athlete"
    assert payload["athlete_id"] == 42
    assert payload["parent_id"] == 7


def test_verify_rejects_tampered_payload():
    token = sa.mint_session_token(role="parent", parent_id=7)
    header, sig = token.split(".", 1)
    # Flip parent_id by re-encoding a different payload with the original signature.
    forged = sa._b64u(b'{"athlete_id":null,"exp":9999999999,"parent_id":999,"role":"parent"}')
    assert sa.verify_session_token(f"{forged}.{sig}") is None


def test_verify_rejects_expired_token():
    token = sa.mint_session_token(role="parent", parent_id=7, ttl_seconds=-1)
    assert sa.verify_session_token(token) is None


def test_verify_rejects_garbage():
    assert sa.verify_session_token("not-a-token") is None
    assert sa.verify_session_token("") is None
    assert sa.verify_session_token("a.b.c") is None


def test_mint_rejects_invalid_role():
    with pytest.raises(ValueError):
        sa.mint_session_token(role="admin", parent_id=1)


def test_require_session_rejects_missing_header():
    with pytest.raises(HTTPException) as exc:
        sa.require_session(authorization=None)
    assert exc.value.status_code == 401


def test_require_session_rejects_non_bearer_header():
    with pytest.raises(HTTPException) as exc:
        sa.require_session(authorization="Basic abc123")
    assert exc.value.status_code == 401


def test_require_session_accepts_valid_bearer():
    token = sa.mint_session_token(role="parent", parent_id=7)
    identity = sa.require_session(authorization=f"Bearer {token}")
    assert identity.role == "parent"
    assert identity.parent_id == 7


def test_assert_owns_athlete_allows_matching_athlete_token(db):
    parent_id = db.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('P', 'p@x.com', datetime('now'), 1)"
    ).lastrowid
    athlete_id = db.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (?, 'A', 15, 'girl', 110, 5, 6)", (parent_id,)
    ).lastrowid
    db.commit()
    identity = sa.SessionIdentity("athlete", parent_id=None, athlete_id=athlete_id)
    sa.assert_owns_athlete(identity, athlete_id, db)  # does not raise


def test_assert_owns_athlete_rejects_other_athlete_token(db):
    identity = sa.SessionIdentity("athlete", parent_id=None, athlete_id=111)
    with pytest.raises(HTTPException) as exc:
        sa.assert_owns_athlete(identity, 222, db)
    assert exc.value.status_code == 403


def test_assert_owns_athlete_allows_owning_parent_token(db):
    parent_id = db.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('P', 'p2@x.com', datetime('now'), 1)"
    ).lastrowid
    athlete_id = db.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (?, 'A', 15, 'girl', 110, 5, 6)", (parent_id,)
    ).lastrowid
    db.commit()
    identity = sa.SessionIdentity("parent", parent_id=parent_id, athlete_id=None)
    sa.assert_owns_athlete(identity, athlete_id, db)  # does not raise


def test_assert_owns_athlete_rejects_non_owning_parent_token(db):
    other_parent_id = db.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('P', 'p3@x.com', datetime('now'), 1)"
    ).lastrowid
    real_parent_id = db.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('P', 'p4@x.com', datetime('now'), 1)"
    ).lastrowid
    athlete_id = db.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (?, 'A', 15, 'girl', 110, 5, 6)", (real_parent_id,)
    ).lastrowid
    db.commit()
    identity = sa.SessionIdentity("parent", parent_id=other_parent_id, athlete_id=None)
    with pytest.raises(HTTPException) as exc:
        sa.assert_owns_athlete(identity, athlete_id, db)
    assert exc.value.status_code == 403


def test_assert_owns_athlete_404s_on_unknown_athlete(db):
    identity = sa.SessionIdentity("parent", parent_id=1, athlete_id=None)
    with pytest.raises(HTTPException) as exc:
        sa.assert_owns_athlete(identity, 999999, db)
    assert exc.value.status_code == 404


def test_assert_owns_parent_allows_matching_token():
    identity = sa.SessionIdentity("parent", parent_id=7, athlete_id=None)
    sa.assert_owns_parent(identity, 7)  # does not raise


def test_assert_owns_parent_rejects_other_parent_token():
    identity = sa.SessionIdentity("parent", parent_id=7, athlete_id=None)
    with pytest.raises(HTTPException) as exc:
        sa.assert_owns_parent(identity, 8)
    assert exc.value.status_code == 403


def test_assert_owns_parent_rejects_athlete_token():
    identity = sa.SessionIdentity("athlete", parent_id=None, athlete_id=5)
    with pytest.raises(HTTPException) as exc:
        sa.assert_owns_parent(identity, 5)
    assert exc.value.status_code == 403
