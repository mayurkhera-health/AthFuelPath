"""BOLA/auth regression tests — legacy push-subscription endpoints in
api/routes/notifications.py (Security Hardening Pass).

POST /subscribe, GET/PUT /{athlete_id}/prefs, and DELETE /{athlete_id}/unsubscribe
had zero authentication before this pass: any anonymous caller could read,
overwrite, or delete another family's push-notification subscription/prefs by
supplying an arbitrary athlete_id. This file proves: (A) unauthenticated ->
401, (B) an invalid/garbage session token -> 401, (C) an unrelated athlete
token -> 403, (D) an unrelated parent token -> 403, (E) the real owning
athlete still succeeds, (F) the real owning parent still succeeds — and for
every rejection, that no database mutation occurred and (for GET) that no
victim data was disclosed in the response body.

This mirrors the existing pattern in tests/test_meals_bola.py.
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
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM push_subscriptions")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


INVALID_TOKEN_HEADERS = {"Authorization": "Bearer not-a-real-token.garbage"}


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


def make_subscription(athlete_id, endpoint="https://push.example/ep-1", **prefs):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO push_subscriptions
                   (athlete_id, endpoint, p256dh, auth,
                    remind_pregame_meal, remind_pregame_snack, remind_meal_log, remind_hydration)
               VALUES (%s, %s, 'p256dh-val', 'auth-val', %s, %s, %s, %s)
               RETURNING id""",
            (
                athlete_id, endpoint,
                int(prefs.get("remind_pregame_meal", True)),
                int(prefs.get("remind_pregame_snack", True)),
                int(prefs.get("remind_meal_log", True)),
                int(prefs.get("remind_hydration", True)),
            ),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def get_subscription_row(athlete_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM push_subscriptions WHERE athlete_id = %s", (athlete_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _victim_and_attacker(email_prefix):
    victim_parent = make_parent(f"{email_prefix}-victim@example.com")
    victim_athlete = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent(f"{email_prefix}-attacker@example.com")
    attacker_athlete = make_athlete(attacker_parent, "Attacker")
    return victim_athlete, victim_parent, attacker_athlete, attacker_parent


# ── POST /api/notifications/subscribe ───────────────────────────────────────

def test_subscribe_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker("sub1")
    r = client.post("/api/notifications/subscribe", json={
        "athlete_id": victim_id, "endpoint": "https://push.example/x", "p256dh": "k", "auth": "a",
    })
    assert r.status_code == 401
    assert get_subscription_row(victim_id) is None


def test_subscribe_rejects_invalid_session_token(client):
    victim_id, _, _, _ = _victim_and_attacker("sub2")
    r = client.post("/api/notifications/subscribe", json={
        "athlete_id": victim_id, "endpoint": "https://push.example/x", "p256dh": "k", "auth": "a",
    }, headers=INVALID_TOKEN_HEADERS)
    assert r.status_code == 401
    assert get_subscription_row(victim_id) is None


def test_subscribe_rejects_unrelated_athlete_token(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker("sub3")
    r = client.post("/api/notifications/subscribe", json={
        "athlete_id": victim_id, "endpoint": "https://push.example/x", "p256dh": "k", "auth": "a",
    }, headers=auth_headers("athlete", athlete_id=attacker_id))
    assert r.status_code == 403
    assert get_subscription_row(victim_id) is None


def test_subscribe_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker("sub4")
    r = client.post("/api/notifications/subscribe", json={
        "athlete_id": victim_id, "endpoint": "https://push.example/x", "p256dh": "k", "auth": "a",
    }, headers=auth_headers("parent", parent_id=attacker_parent))
    assert r.status_code == 403
    assert get_subscription_row(victim_id) is None


def test_subscribe_allows_owning_athlete(client):
    victim_id, _, _, _ = _victim_and_attacker("sub5")
    r = client.post("/api/notifications/subscribe", json={
        "athlete_id": victim_id, "endpoint": "https://push.example/x", "p256dh": "k", "auth": "a",
    }, headers=auth_headers("athlete", athlete_id=victim_id))
    assert r.status_code == 200, r.text
    assert get_subscription_row(victim_id) is not None


def test_subscribe_allows_owning_parent(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker("sub6")
    r = client.post("/api/notifications/subscribe", json={
        "athlete_id": victim_id, "endpoint": "https://push.example/x", "p256dh": "k", "auth": "a",
    }, headers=auth_headers("parent", parent_id=victim_parent))
    assert r.status_code == 200, r.text
    assert get_subscription_row(victim_id) is not None


# ── GET /api/notifications/{athlete_id}/prefs ───────────────────────────────

def test_get_prefs_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker("getp1")
    make_subscription(victim_id, remind_hydration=False)
    r = client.get(f"/api/notifications/{victim_id}/prefs")
    assert r.status_code == 401


def test_get_prefs_rejects_invalid_session_token(client):
    victim_id, _, _, _ = _victim_and_attacker("getp2")
    make_subscription(victim_id, remind_hydration=False)
    r = client.get(f"/api/notifications/{victim_id}/prefs", headers=INVALID_TOKEN_HEADERS)
    assert r.status_code == 401


def test_get_prefs_rejects_unrelated_athlete_token_and_discloses_nothing(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker("getp3")
    make_subscription(victim_id, remind_hydration=False)
    r = client.get(
        f"/api/notifications/{victim_id}/prefs",
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert "subscribed" not in r.json()
    assert "remind_hydration" not in r.json()


def test_get_prefs_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker("getp4")
    make_subscription(victim_id, remind_hydration=False)
    r = client.get(
        f"/api/notifications/{victim_id}/prefs",
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert "subscribed" not in r.json()


def test_get_prefs_allows_owning_athlete_with_no_subscription(client):
    victim_id, _, _, _ = _victim_and_attacker("getp5")
    r = client.get(
        f"/api/notifications/{victim_id}/prefs",
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text
    assert r.json()["subscribed"] is False


def test_get_prefs_allows_owning_parent_with_existing_subscription(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker("getp6")
    make_subscription(victim_id, remind_hydration=False)
    r = client.get(
        f"/api/notifications/{victim_id}/prefs",
        headers=auth_headers("parent", parent_id=victim_parent),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subscribed"] is True
    assert body["remind_hydration"] is False


# ── PUT /api/notifications/{athlete_id}/prefs ───────────────────────────────

def test_update_prefs_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker("putp1")
    make_subscription(victim_id, remind_hydration=True)
    r = client.put(f"/api/notifications/{victim_id}/prefs", json={"remind_hydration": False})
    assert r.status_code == 401
    assert get_subscription_row(victim_id)["remind_hydration"] == 1


def test_update_prefs_rejects_invalid_session_token(client):
    victim_id, _, _, _ = _victim_and_attacker("putp2")
    make_subscription(victim_id, remind_hydration=True)
    r = client.put(
        f"/api/notifications/{victim_id}/prefs", json={"remind_hydration": False},
        headers=INVALID_TOKEN_HEADERS,
    )
    assert r.status_code == 401
    assert get_subscription_row(victim_id)["remind_hydration"] == 1


def test_update_prefs_rejects_unrelated_athlete_token(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker("putp3")
    make_subscription(victim_id, remind_hydration=True)
    r = client.put(
        f"/api/notifications/{victim_id}/prefs", json={"remind_hydration": False},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert get_subscription_row(victim_id)["remind_hydration"] == 1


def test_update_prefs_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker("putp4")
    make_subscription(victim_id, remind_hydration=True)
    r = client.put(
        f"/api/notifications/{victim_id}/prefs", json={"remind_hydration": False},
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert get_subscription_row(victim_id)["remind_hydration"] == 1


def test_update_prefs_allows_owning_athlete(client):
    victim_id, _, _, _ = _victim_and_attacker("putp5")
    make_subscription(victim_id, remind_hydration=True)
    r = client.put(
        f"/api/notifications/{victim_id}/prefs",
        json={"remind_hydration": False, "remind_meal_log": True},
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text
    row = get_subscription_row(victim_id)
    assert row["remind_hydration"] == 0
    assert row["remind_meal_log"] == 1


def test_update_prefs_allows_owning_parent(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker("putp6")
    make_subscription(victim_id, remind_hydration=True)
    r = client.put(
        f"/api/notifications/{victim_id}/prefs",
        json={"remind_hydration": False, "remind_meal_log": True},
        headers=auth_headers("parent", parent_id=victim_parent),
    )
    assert r.status_code == 200, r.text
    row = get_subscription_row(victim_id)
    assert row["remind_hydration"] == 0
    assert row["remind_meal_log"] == 1


# ── DELETE /api/notifications/{athlete_id}/unsubscribe ──────────────────────

def test_unsubscribe_requires_a_session(client):
    victim_id, _, _, _ = _victim_and_attacker("del1")
    make_subscription(victim_id)
    r = client.delete(f"/api/notifications/{victim_id}/unsubscribe")
    assert r.status_code == 401
    assert get_subscription_row(victim_id) is not None


def test_unsubscribe_rejects_invalid_session_token(client):
    victim_id, _, _, _ = _victim_and_attacker("del2")
    make_subscription(victim_id)
    r = client.delete(f"/api/notifications/{victim_id}/unsubscribe", headers=INVALID_TOKEN_HEADERS)
    assert r.status_code == 401
    assert get_subscription_row(victim_id) is not None


def test_unsubscribe_rejects_unrelated_athlete_token(client):
    victim_id, _, attacker_id, _ = _victim_and_attacker("del3")
    make_subscription(victim_id)
    r = client.delete(
        f"/api/notifications/{victim_id}/unsubscribe",
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert get_subscription_row(victim_id) is not None


def test_unsubscribe_rejects_unrelated_parent_token(client):
    victim_id, _, _, attacker_parent = _victim_and_attacker("del4")
    make_subscription(victim_id)
    r = client.delete(
        f"/api/notifications/{victim_id}/unsubscribe",
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert get_subscription_row(victim_id) is not None


def test_unsubscribe_allows_owning_athlete(client):
    victim_id, _, _, _ = _victim_and_attacker("del5")
    make_subscription(victim_id)
    r = client.delete(
        f"/api/notifications/{victim_id}/unsubscribe",
        headers=auth_headers("athlete", athlete_id=victim_id),
    )
    assert r.status_code == 200, r.text
    assert get_subscription_row(victim_id) is None


def test_unsubscribe_allows_owning_parent(client):
    victim_id, victim_parent, _, _ = _victim_and_attacker("del6")
    make_subscription(victim_id)
    r = client.delete(
        f"/api/notifications/{victim_id}/unsubscribe",
        headers=auth_headers("parent", parent_id=victim_parent),
    )
    assert r.status_code == 200, r.text
    assert get_subscription_row(victim_id) is None
