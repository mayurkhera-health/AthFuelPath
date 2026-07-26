"""
BOLA (Broken Object-Level Authorization) probe — POST/DELETE /api/athletes/{id}/confirmations.

api/routes/fuel_report.py's confirmation endpoints take athlete_id straight from the URL
path and never check it against any caller identity. This app has no session tokens by
design (CLAUDE.md Sec.5: "No auth tokens. Session is identity-by-ID") -- that decision
concerns *how a user authenticates* (the approved email-only login) and is explicitly
out of scope to challenge here. This test is about a DIFFERENT, unrelated question:
once a request arrives, does the server check that the athlete_id in the URL actually
belongs to whoever is asking? Right now it does not, for anyone -- there is no caller
identity captured anywhere in this route to check against. Per CLAUDE.md's own rule
#9 ("Enforce visibility server-side (403), not just in the UI"), this endpoint does
not currently meet the project's own bar, and athlete_id values are small sequential
integers, so they are trivially guessable/enumerable -- this is not a theoretical gap.

Concretely: anyone who merely learns another athlete's numeric ID (a sibling's
device, a support screenshot, a QA build with sequential test accounts, or plain
enumeration) can create AND delete that athlete's fuel-window confirmations, with
nothing tying the request back to a legitimate relationship to that child. In a
COPPA-scoped app for 13-17 year olds this is a real cross-account write/delete
vulnerability, independent of the login mechanism.

STATUS AS OF THIS WRITING: both tests below are EXPECTED TO FAIL against the live
route -- there is no ownership check yet to make them pass. They are included as
regression/triage tests: once a fix lands (e.g. a scoped caller identity + a
belongs-to-parent check mirroring the one that already exists in
POST /api/auth/athlete-create-login/{id}, see tests/test_auth_flow.py
test_create_login_requires_athlete_belongs_to_parent), these tests turn green and
lock the fix in.
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
    relationship to. Nothing needs to be forged -- there is no token to forge, because
    none is ever checked, so only the victim's athlete_id is required.
    """
    # The attacker's own real account exists and is irrelevant to the exploit -- the
    # vulnerability is that it doesn't matter who (if anyone) is asking.
    attacker_parent = make_parent("attacker@example.com")
    make_athlete(attacker_parent, "AttackerKid")

    victim_parent = make_parent("victim@example.com")
    victim_athlete_id = make_athlete(victim_parent, "Victim")

    r = client.post(
        f"/api/athletes/{victim_athlete_id}/confirmations",
        json={"window_key": "breakfast", "window_type": "pre_fuel", "log_date": "2026-07-26"},
    )

    assert r.status_code in (401, 403, 404), (
        "Expected the confirmations endpoint to reject a write for an athlete_id the "
        f"caller has no relationship to, but got {r.status_code}: {r.text}. This "
        "confirms unrestricted cross-athlete write access (BOLA) -- see module "
        "docstring for the real-world impact and the current fix status."
    )
    assert fetch_confirmation(victim_athlete_id, "breakfast") is None, (
        "A confirmation was written for the victim athlete by an unrelated caller."
    )


def test_deleting_another_athletes_confirmation_is_rejected(client):
    """Same gap, the destructive direction: an unrelated caller can erase a real,
    already-recorded confirmation belonging to another family's athlete."""
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
    )

    assert r.status_code in (401, 403, 404), (
        f"Expected the delete to be rejected, got {r.status_code}: {r.text}. Any "
        "caller can silently delete another athlete's fuel confirmation."
    )
    assert fetch_confirmation(victim_athlete_id, "breakfast") is not None, (
        "The victim's confirmation was deleted by an unrelated caller."
    )
