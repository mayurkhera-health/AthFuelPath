"""POST /api/meal-plans/{athlete_id}/log-slot double-submit/concurrency
regression (Security Item 5, F2). The prior implementation did a plain
SELECT (check `logged`) then a separate INSERT into meal_logs then a
separate UPDATE meal_plans SET logged=1 — three unguarded statements. Two
genuinely concurrent requests for the same slot could both read logged=0,
both insert a meal_logs row, and both then set logged=1 (a harmless-looking
no-op on the flag while silently double-counting that meal's calories/
macros in meal_logs).

Fixed by replacing the check-then-insert with a single atomic
UPDATE ... WHERE logged=0 RETURNING claim: Postgres's own row-level locking
serializes concurrent UPDATEs to the same row, so exactly one request's
claim can succeed. Only the request that receives a returned row proceeds
to insert into meal_logs, and the claim + insert are never committed
separately — a forced meal_logs INSERT failure rolls back the logged=1
claim in the same transaction.
"""
import os
os.environ["DB_PATH"] = ":memory:"

import threading
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
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM meal_plans")
    keepalive.execute("DELETE FROM meal_logs")
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


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in)
               VALUES (%s, %s, 15, 'girl', 115, 5, 6) RETURNING id""",
            (parent_id, first_name),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def make_planned_slot(athlete_id, plan_date="2026-08-01", slot_name="everyday_lunch", logged=0):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO meal_plans
               (athlete_id, plan_date, slot_name, recipe_id, recipe_name,
                calories, carbs_g, protein_g, fat_g, is_ai_generated, logged)
               VALUES (%s, %s, %s, 'r1', 'Chicken and Rice', 500, 40, 35, 15, 0, %s)""",
            (athlete_id, plan_date, slot_name, logged),
        )
        conn.commit()
    finally:
        conn.close()


def _slot_logged(athlete_id, plan_date, slot_name) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT logged FROM meal_plans WHERE athlete_id=%s AND plan_date=%s AND slot_name=%s",
            (athlete_id, plan_date, slot_name),
        ).fetchone()
        return row["logged"]
    finally:
        conn.close()


def _meal_logs_count(athlete_id) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM meal_logs WHERE athlete_id = %s", (athlete_id,)
        ).fetchone()["c"]
    finally:
        conn.close()


PLAN_DATE = "2026-08-01"
SLOT_NAME = "everyday_lunch"


# ─── A/B/C: two concurrent log-slot calls -> exactly one meal_logs row ─────

def test_concurrent_log_slot_calls_result_in_exactly_one_meal_log(client):
    parent_id = make_parent("logslot-race@example.com")
    athlete_id = make_athlete(parent_id)
    make_planned_slot(athlete_id, PLAN_DATE, SLOT_NAME)
    headers = auth_headers("athlete", athlete_id=athlete_id)

    barrier = threading.Barrier(2)
    results = []

    def _submit():
        barrier.wait(timeout=5)
        r = client.post(
            f"/api/meal-plans/{athlete_id}/log-slot",
            json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME},
            headers=headers,
        )
        results.append(r)

    t1 = threading.Thread(target=_submit)
    t2 = threading.Thread(target=_submit)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert len(results) == 2
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 400], (
        f"expected exactly one winner (200) and one already-logged loser (400), got {[r.status_code for r in results]}: "
        f"{[r.text for r in results]}"
    )
    assert _meal_logs_count(athlete_id) == 1
    assert _slot_logged(athlete_id, PLAN_DATE, SLOT_NAME) == 1


# ─── D: second request gets the expected already-logged behavior ──────────

def test_sequential_second_call_gets_already_logged_400(client):
    parent_id = make_parent("logslot-seq@example.com")
    athlete_id = make_athlete(parent_id)
    make_planned_slot(athlete_id, PLAN_DATE, SLOT_NAME)
    headers = auth_headers("athlete", athlete_id=athlete_id)

    r1 = client.post(
        f"/api/meal-plans/{athlete_id}/log-slot",
        json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME}, headers=headers,
    )
    assert r1.status_code == 200, r1.text

    r2 = client.post(
        f"/api/meal-plans/{athlete_id}/log-slot",
        json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME}, headers=headers,
    )
    assert r2.status_code == 400, r2.text
    assert "already" in r2.json()["detail"].lower()
    assert _meal_logs_count(athlete_id) == 1


# ─── E: repeat sequential call does not add a second meal ──────────────────
# (same assertion as above, kept as its own named test since the task lists
# it as a separate required proof)

def test_repeat_call_never_adds_a_second_meal_log_row(client):
    parent_id = make_parent("logslot-repeat@example.com")
    athlete_id = make_athlete(parent_id)
    make_planned_slot(athlete_id, PLAN_DATE, SLOT_NAME)
    headers = auth_headers("athlete", athlete_id=athlete_id)

    for _ in range(3):
        client.post(
            f"/api/meal-plans/{athlete_id}/log-slot",
            json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME}, headers=headers,
        )
    assert _meal_logs_count(athlete_id) == 1


# ─── F: forced meal_logs INSERT failure rolls back the slot claim ──────────

def test_meal_log_insert_failure_rolls_back_the_logged_claim(client, monkeypatch):
    parent_id = make_parent("logslot-rollback@example.com")
    athlete_id = make_athlete(parent_id)
    make_planned_slot(athlete_id, PLAN_DATE, SLOT_NAME)
    headers = auth_headers("athlete", athlete_id=athlete_id)

    import api.routes.meal_plans as meal_plans_module
    real_get_conn = meal_plans_module.get_conn

    class _FailingConn:
        """Thin proxy around a real connection — only intercepts the specific
        meal_logs INSERT to simulate a failure after the logged=1 claim has
        already run in the same (uncommitted) transaction, proving the claim
        rolls back rather than leaving the slot falsely marked logged."""

        def __init__(self, real_conn):
            self._real = real_conn

        def execute(self, query, params=None):
            if isinstance(query, str) and "INSERT INTO meal_logs" in query:
                raise RuntimeError("simulated meal_logs insert failure")
            return self._real.execute(query, params) if params is not None else self._real.execute(query)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def fake_get_conn():
        return _FailingConn(real_get_conn())

    monkeypatch.setattr(meal_plans_module, "get_conn", fake_get_conn)

    # TestClient re-raises unhandled server exceptions to the caller by
    # default (raise_server_exceptions=True) rather than returning a 500
    # response — the exception itself IS the proof the simulated failure
    # actually happened and wasn't silently swallowed.
    with pytest.raises(RuntimeError, match="simulated meal_logs insert failure"):
        client.post(
            f"/api/meal-plans/{athlete_id}/log-slot",
            json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME}, headers=headers,
        )

    monkeypatch.undo()
    assert _slot_logged(athlete_id, PLAN_DATE, SLOT_NAME) == 0, (
        "the logged=1 claim must be rolled back when the meal_logs insert fails"
    )
    assert _meal_logs_count(athlete_id) == 0


# ─── 404 for a slot that doesn't exist at all (unchanged behavior) ─────────

def test_log_slot_404s_when_slot_does_not_exist(client):
    parent_id = make_parent("logslot-404@example.com")
    athlete_id = make_athlete(parent_id)
    headers = auth_headers("athlete", athlete_id=athlete_id)

    r = client.post(
        f"/api/meal-plans/{athlete_id}/log-slot",
        json={"plan_date": "2099-01-01", "slot_name": "nonexistent"}, headers=headers,
    )
    assert r.status_code == 404


# ─── G: unrelated athlete/parent authorization remains denied ─────────────

def test_log_slot_still_rejects_unrelated_athlete_token(client):
    victim_parent = make_parent("logslot-victim@example.com")
    victim_id = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent("logslot-attacker@example.com")
    attacker_id = make_athlete(attacker_parent, "Attacker")
    make_planned_slot(victim_id, PLAN_DATE, SLOT_NAME)

    r = client.post(
        f"/api/meal-plans/{victim_id}/log-slot",
        json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert _meal_logs_count(victim_id) == 0
    assert _slot_logged(victim_id, PLAN_DATE, SLOT_NAME) == 0


# ─── H: normal single-request response shape unchanged ────────────────────

def test_log_slot_success_response_shape_unchanged(client):
    parent_id = make_parent("logslot-shape@example.com")
    athlete_id = make_athlete(parent_id)
    make_planned_slot(athlete_id, PLAN_DATE, SLOT_NAME)
    headers = auth_headers("athlete", athlete_id=athlete_id)

    r = client.post(
        f"/api/meal-plans/{athlete_id}/log-slot",
        json={"plan_date": PLAN_DATE, "slot_name": SLOT_NAME}, headers=headers,
    )
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) == {"logged", "meal_log_id"}
    assert r.json()["logged"] is True
    assert isinstance(r.json()["meal_log_id"], int)
