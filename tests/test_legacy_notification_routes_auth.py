"""BOLA regression tests for the legacy web-push routes in
api/routes/notifications.py — POST /subscribe, GET/PUT /{athlete_id}/prefs,
DELETE /{athlete_id}/unsubscribe. These previously took no session at all
(not just "no ownership check" — zero Depends(require_session)), unlike
every other route in the same file. Still called by the legacy web
frontend (frontend/src/notificationService.js -> NotificationsScreen.jsx),
so gated rather than deleted."""
import os
os.environ["DB_PATH"] = ":memory:"

import psycopg
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
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client):
    _counter["n"] += 1
    email = f"legacynotif{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    }, headers=auth_headers("parent", parent_id=parent_id))
    assert a.status_code == 201, a.text
    return a.json()["id"], parent_id


SUBSCRIBE_BODY = lambda athlete_id: {
    "athlete_id": athlete_id, "endpoint": "https://push.example.com/x",
    "p256dh": "key", "auth": "auth",
}
# NOTE: 1/0, not True/False. The route's own DB write does
# `conn.execute("UPDATE ... SET remind_pregame_meal=%s, ...", (prefs.remind_pregame_meal, ...))`
# against push_subscriptions.remind_pregame_meal, an INTEGER column
# (legacy SQLite-era 0/1 schema, ported to Postgres as-is) -- pydantic's
# `Optional[bool]` on NotificationPrefs turns a JSON `true`/`false` body
# into a Python bool, which psycopg3 refuses to bind to an integer column
# (psycopg.errors.DatatypeMismatch). The real web frontend
# (frontend/src/NotificationsScreen.jsx) sends JS `true`/`false` here, so
# this route 500s on every real save today -- a genuine, separate,
# pre-existing bug, out of scope for this auth fix. Reported, not fixed
# here. Using ints below so this auth-focused test file isn't blocked by it.
PREFS_BODY = {
    "remind_pregame_meal": 1, "remind_pregame_snack": 0,
    "remind_meal_log": 1, "remind_hydration": 0,
}


# ── POST /api/notifications/subscribe ─────────────────────────────────────

def test_subscribe_requires_a_session(client):
    athlete_id, _ = _make_athlete(client)
    r = client.post("/api/notifications/subscribe", json=SUBSCRIBE_BODY(athlete_id))
    assert r.status_code == 401


def test_subscribe_rejects_unrelated_athlete_token(client):
    victim_id, _ = _make_athlete(client)
    attacker_id, _ = _make_athlete(client)
    r = client.post(
        "/api/notifications/subscribe", json=SUBSCRIBE_BODY(victim_id),
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT 1 FROM push_subscriptions WHERE athlete_id=%s", (victim_id,)
    ).fetchone() is None


def test_subscribe_allows_owning_athlete(client):
    athlete_id, parent_id = _make_athlete(client)
    r = client.post(
        "/api/notifications/subscribe", json=SUBSCRIBE_BODY(athlete_id),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200
    r2 = client.post(
        "/api/notifications/subscribe", json=SUBSCRIBE_BODY(athlete_id),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r2.status_code == 200


# ── GET /api/notifications/{athlete_id}/prefs ─────────────────────────────

def test_get_prefs_requires_a_session(client):
    athlete_id, _ = _make_athlete(client)
    r = client.get(f"/api/notifications/{athlete_id}/prefs")
    assert r.status_code == 401


def test_get_prefs_rejects_unrelated_athlete_token(client):
    victim_id, _ = _make_athlete(client)
    attacker_id, _ = _make_athlete(client)
    r = client.get(
        f"/api/notifications/{victim_id}/prefs",
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403


def test_get_prefs_allows_owning_parent(client):
    athlete_id, parent_id = _make_athlete(client)
    r = client.get(
        f"/api/notifications/{athlete_id}/prefs",
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 200


# ── PUT /api/notifications/{athlete_id}/prefs ─────────────────────────────

def test_update_prefs_requires_a_session(client):
    athlete_id, _ = _make_athlete(client)
    r = client.put(f"/api/notifications/{athlete_id}/prefs", json=PREFS_BODY)
    assert r.status_code == 401


def test_update_prefs_rejects_unrelated_athlete_token(client):
    victim_id, _ = _make_athlete(client)
    attacker_id, _ = _make_athlete(client)
    r = client.put(
        f"/api/notifications/{victim_id}/prefs", json=PREFS_BODY,
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403


def test_update_prefs_allows_owning_athlete_past_the_auth_check(client):
    """Confirms the owner clears assert_owns_athlete (no 401/403 -- if the
    auth guard were wrongly rejecting the owner, this would raise
    HTTPException before ever reaching the DB call, not DatatypeMismatch).
    The write itself then fails for everyone, owner or not, on a separate,
    pre-existing bug unrelated to auth: pydantic's Optional[bool] on
    NotificationPrefs always coerces to a Python bool before it reaches
    `conn.execute(...)`, and psycopg3 refuses to bind a bool against
    push_subscriptions' legacy INTEGER columns (see PREFS_BODY comment
    above). Out of scope for this auth fix, reported separately.
    TestClient's default raise_server_exceptions=True re-raises the
    uncaught exception rather than returning a 500 response, so this
    asserts the exception directly -- deliberate, not a workaround: proof
    this test isn't silently passing for the wrong reason, and it'll go
    red -- correctly -- the day someone fixes that bug, as a reminder to
    replace this with a plain 200 assertion."""
    athlete_id, _ = _make_athlete(client)
    with pytest.raises(psycopg.errors.DatatypeMismatch):
        client.put(
            f"/api/notifications/{athlete_id}/prefs", json=PREFS_BODY,
            headers=auth_headers("athlete", athlete_id=athlete_id),
        )


# ── DELETE /api/notifications/{athlete_id}/unsubscribe ────────────────────

def test_unsubscribe_requires_a_session(client):
    athlete_id, _ = _make_athlete(client)
    r = client.delete(f"/api/notifications/{athlete_id}/unsubscribe")
    assert r.status_code == 401


def test_unsubscribe_rejects_unrelated_athlete_token(client):
    victim_id, _ = _make_athlete(client)
    attacker_id, _ = _make_athlete(client)
    r = client.delete(
        f"/api/notifications/{victim_id}/unsubscribe",
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403


def test_unsubscribe_allows_owning_athlete(client):
    athlete_id, _ = _make_athlete(client)
    client.post(
        "/api/notifications/subscribe", json=SUBSCRIBE_BODY(athlete_id),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    r = client.delete(
        f"/api/notifications/{athlete_id}/unsubscribe",
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200
    assert get_conn().execute(
        "SELECT 1 FROM push_subscriptions WHERE athlete_id=%s", (athlete_id,)
    ).fetchone() is None
