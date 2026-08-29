"""Athlete-creation double-submit/concurrency regression (Security Item 5,
F1). POST /api/athletes/ previously did an unconditional INSERT with no
existence check and no unique constraint — two genuinely concurrent
identical submissions (a mobile network-retry or double-tap) could both
insert, producing two full duplicate athlete profiles for the same minor
with no reconciliation path.

Fixed by serializing creation per-parent with a transaction-scoped Postgres
advisory lock (same pattern as event_matching.acquire_reconciliation_lock)
and, inside that lock, checking for an exact-payload match created within a
short (10s) retry window before inserting. Deliberately does NOT enforce
"one athlete per parent" or match on a narrow subset of fields (first_name/
age/DOB/parent_id) that could coincide for two real, different children.
"""
import os
os.environ["DB_PATH"] = ":memory:"

import threading
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.routes import athletes as athletes_module
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM events")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def make_parent(email):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), True),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def _athlete_body(parent_id, **overrides):
    body = {
        "parent_id": parent_id, "first_name": "New Kid", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 4,
    }
    body.update(overrides)
    return body


def _athlete_count(parent_id) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM athletes WHERE parent_id = %s", (parent_id,)
        ).fetchone()["c"]
    finally:
        conn.close()


# ─── A: genuine concurrent identical submissions -> one row ────────────────

def test_concurrent_identical_submissions_result_in_one_athlete_row(client):
    parent_id = make_parent("idempotent-athlete@example.com")
    headers = auth_headers("parent", parent_id=parent_id)
    body = _athlete_body(parent_id)

    barrier = threading.Barrier(2)
    results = []

    def _submit():
        barrier.wait(timeout=5)
        r = client.post("/api/athletes/", json=body, headers=headers)
        results.append(r)

    t1 = threading.Thread(target=_submit)
    t2 = threading.Thread(target=_submit)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert len(results) == 2
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    ids = {r.json()["id"] for r in results}
    assert len(ids) == 1, f"expected both concurrent submissions to resolve to 1 row, got ids={ids}"
    assert _athlete_count(parent_id) == 1


# ─── B: same parent, clearly different athlete -> two rows ─────────────────

def test_same_parent_different_athlete_creates_two_rows(client):
    parent_id = make_parent("two-kids@example.com")
    headers = auth_headers("parent", parent_id=parent_id)

    r1 = client.post("/api/athletes/", json=_athlete_body(parent_id, first_name="Alex"), headers=headers)
    r2 = client.post("/api/athletes/", json=_athlete_body(parent_id, first_name="Jordan"), headers=headers)

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] != r2.json()["id"]
    assert _athlete_count(parent_id) == 2


# ─── C: different parents, identical-looking payload -> two rows ──────────

def test_different_parents_identical_looking_payload_creates_two_rows(client):
    parent_a = make_parent("parenta@example.com")
    parent_b = make_parent("parentb@example.com")

    r1 = client.post(
        "/api/athletes/", json=_athlete_body(parent_a),
        headers=auth_headers("parent", parent_id=parent_a),
    )
    r2 = client.post(
        "/api/athletes/", json=_athlete_body(parent_b),
        headers=auth_headers("parent", parent_id=parent_b),
    )

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] != r2.json()["id"]
    assert _athlete_count(parent_a) == 1
    assert _athlete_count(parent_b) == 1


# ─── D: sequential duplicate OUTSIDE the retry window -> allowed ───────────

def test_sequential_duplicate_outside_retry_window_creates_two_rows(client):
    parent_id = make_parent("outside-window@example.com")
    headers = auth_headers("parent", parent_id=parent_id)
    body = _athlete_body(parent_id)

    r1 = client.post("/api/athletes/", json=body, headers=headers)
    assert r1.status_code == 201, r1.text

    time.sleep(athletes_module._ATHLETE_CREATE_RETRY_WINDOW_SECONDS + 1)

    r2 = client.post("/api/athletes/", json=body, headers=headers)
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] != r2.json()["id"], (
        "a submission outside the documented retry window must be treated as a "
        "genuinely new request, not deduped"
    )
    assert _athlete_count(parent_id) == 2


# ─── H: blueprint generation remains correct for the winning athlete ──────

def test_blueprint_is_correct_after_concurrent_creation(client):
    parent_id = make_parent("blueprint-race@example.com")
    headers = auth_headers("parent", parent_id=parent_id)
    body = _athlete_body(parent_id)

    barrier = threading.Barrier(2)
    results = []

    def _submit():
        barrier.wait(timeout=5)
        r = client.post("/api/athletes/", json=body, headers=headers)
        results.append(r)

    t1 = threading.Thread(target=_submit)
    t2 = threading.Thread(target=_submit)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    athlete_id = results[0].json()["id"]
    r = client.get(f"/api/athletes/{athlete_id}/blueprint", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["athlete_id"] == athlete_id
    assert isinstance(body["blueprint"], dict) and body["blueprint"]
    assert body["_calculated"]["ffm_kg"] > 0
