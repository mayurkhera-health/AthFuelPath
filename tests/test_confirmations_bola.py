"""
BOLA (Broken Object-Level Authorization) regression — POST/DELETE
/api/athletes/{id}/confirmations.

api/routes/fuel_report.py's confirmation endpoints used to take athlete_id
straight from the URL path with no check against any caller identity —
athlete_id values are small sequential integers, trivially guessable, so
anyone who merely learned another athlete's numeric ID could create or
delete that athlete's fuel-window confirmations. Fixed via api/services/
session_auth.py's require_session/assert_owns_athlete (a session token
minted at the existing email-only login, per CLAUDE.md rule #9 "Enforce
visibility server-side (403), not just in the UI") — these tests now pass
and lock the fix in. Every caller below must send a real (but
unauthorized) session token; no token at all 401s instead, which is
covered by test_athletes_parents_bola.py for the equivalent pattern on
other routes.
"""
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    # clean slate for each test (the in-memory DB persists across the module)
    keepalive.execute("DELETE FROM confirmations")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


# --- helpers (mirrors tests/test_auth_flow.py's direct-insert pattern) --------------

def make_parent(email, full_name="Test Parent"):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (?, ?, ?, ?)",
            (full_name, email.lower(), datetime.utcnow().isoformat(), 1),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in)
               VALUES (?, ?, 14, 'Boy', 120, 5, 6)""",
            (parent_id, first_name),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def fetch_confirmation(athlete_id, window_key):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM confirmations WHERE athlete_id = ? AND window_key = ?",
            (athlete_id, window_key),
        ).fetchone()
    finally:
        conn.close()


# --- BOLA probes ---------------------------------------------------------------------

def test_confirming_a_window_for_an_athlete_you_do_not_own_is_rejected(client):
    """
    Simulates the real-world attack: an unrelated caller who only knows a victim's
    numeric athlete_id (guessed a nearby sequential ID, captured it from a shared
    link/screenshot, etc.) writes a fuel-window confirmation for a child they have no
    relationship to. The attacker's token is real and valid — it's just for the
    wrong athlete — proving the rejection comes from the ownership check, not
    merely from having no token at all.
    """
    attacker_parent = make_parent("attacker@example.com")
    attacker_athlete_id = make_athlete(attacker_parent, "AttackerKid")

    victim_parent = make_parent("victim@example.com")
    victim_athlete_id = make_athlete(victim_parent, "Victim")

    r = client.post(
        f"/api/athletes/{victim_athlete_id}/confirmations",
        json={"window_key": "breakfast", "window_type": "pre_fuel", "log_date": "2026-07-26"},
        headers=auth_headers("athlete", athlete_id=attacker_athlete_id),
    )

    assert r.status_code == 403, (
        "Expected the confirmations endpoint to reject a write for an athlete_id the "
        f"caller has no relationship to, but got {r.status_code}: {r.text}. This "
        "would confirm unrestricted cross-athlete write access (BOLA)."
    )
    assert fetch_confirmation(victim_athlete_id, "breakfast") is None, (
        "A confirmation was written for the victim athlete by an unrelated caller."
    )


def test_deleting_another_athletes_confirmation_is_rejected(client):
    """Same gap, the destructive direction: an unrelated caller can erase a real,
    already-recorded confirmation belonging to another family's athlete."""
    attacker_athlete_id = make_athlete(make_parent("attacker2@example.com"), "AttackerKid2")
    victim_parent = make_parent("victim2@example.com")
    victim_athlete_id = make_athlete(victim_parent, "Victim2")

    conn = get_conn()
    conn.execute(
        "INSERT INTO confirmations (athlete_id, log_date, window_key, window_type) VALUES (?, ?, ?, ?)",
        (victim_athlete_id, "2026-07-26", "breakfast", "pre_fuel"),
    )
    conn.commit()
    conn.close()

    r = client.delete(
        f"/api/athletes/{victim_athlete_id}/confirmations",
        params={"window_key": "breakfast", "log_date": "2026-07-26"},
        headers=auth_headers("athlete", athlete_id=attacker_athlete_id),
    )

    assert r.status_code == 403, (
        f"Expected the delete to be rejected, got {r.status_code}: {r.text}. Any "
        "caller can silently delete another athlete's fuel confirmation."
    )
    assert fetch_confirmation(victim_athlete_id, "breakfast") is not None, (
        "The victim's confirmation was deleted by an unrelated caller."
    )


def test_confirming_for_a_nonexistent_athlete_404s_even_with_a_matching_self_token(client):
    """
    assert_owns_athlete's fast path for an athlete-role token (identity.athlete_id
    matches the URL's athlete_id) never touches the DB. A syntactically valid
    self-token for an athlete_id that doesn't exist (deleted account, or a token
    minted then the row removed) used to sail through and silently INSERT an
    orphaned confirmation row instead of erroring.
    """
    ghost_athlete_id = 999999
    r = client.post(
        f"/api/athletes/{ghost_athlete_id}/confirmations",
        json={"window_key": "breakfast", "window_type": "pre_fuel", "log_date": "2026-07-26"},
        headers=auth_headers("athlete", athlete_id=ghost_athlete_id),
    )
    assert r.status_code == 404, (
        f"Expected 404 for a nonexistent athlete_id even with a matching self-token, "
        f"got {r.status_code}: {r.text}."
    )
    assert fetch_confirmation(ghost_athlete_id, "breakfast") is None, (
        "An orphaned confirmation row was inserted for an athlete_id that doesn't exist."
    )
