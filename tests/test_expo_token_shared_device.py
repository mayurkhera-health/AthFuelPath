"""
Regressions for POST /api/notifications/expo-token:

1. A push token belongs to a device, not a person. On a shared family device
   (one tablet/phone used by both a parent and an athlete), a parent's
   registration and an athlete's registration carry the SAME token. Since
   token is the unique key, the old unconditional UPDATE (athlete_id=excluded.
   athlete_id, parent_id=excluded.parent_id) blanked out whichever id the
   current call didn't send — e.g. the athlete's later registration (no
   parent_id in that payload) wiped the parent_id a prior registration had
   set, silently killing the parent's push notifications with no error
   anywhere. Fixed via COALESCE(excluded.x, expo_push_tokens.x) so a token can
   carry both ids at once.

2. The route had no ownership check at all — any caller could register their
   own device against ANY athlete_id/parent_id (small sequential integers),
   silently starting to receive that family's push notifications. Fixed via
   require_session + assert_owns_athlete/assert_owns_parent.
"""
import os
os.environ["DB_PATH"] = ":memory:"

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


def _row_for_token(token):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT athlete_id, parent_id FROM expo_push_tokens WHERE token = ?", (token,)
        ).fetchone()
    finally:
        conn.close()


_counter = {"n": 0}


def _make_family(client):
    """A real parent + their own athlete — the shared-device scenario."""
    _counter["n"] += 1
    email = f"expo-token{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    })
    assert a.status_code == 201, a.text
    return parent_id, a.json()["id"]


def test_athlete_registering_the_same_shared_device_token_does_not_wipe_the_parent(client):
    parent_id, athlete_id = _make_family(client)
    shared_token = "ExponentPushToken[shared-device-abc]"

    r1 = client.post(
        "/api/notifications/expo-token", json={"token": shared_token, "parent_id": parent_id},
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r1.status_code == 200, r1.text

    row = _row_for_token(shared_token)
    assert row["parent_id"] == parent_id
    assert row["athlete_id"] is None

    r2 = client.post(
        "/api/notifications/expo-token", json={"token": shared_token, "athlete_id": athlete_id},
        headers=auth_headers("athlete", athlete_id=athlete_id, parent_id=parent_id),
    )
    assert r2.status_code == 200, r2.text

    row = _row_for_token(shared_token)
    assert row["athlete_id"] == athlete_id
    assert row["parent_id"] == parent_id, (
        "Parent's id was wiped when the athlete registered the same shared-device token."
    )


def test_parent_registering_the_same_shared_device_token_does_not_wipe_the_athlete(client):
    """Same bug, opposite order — the athlete registers first."""
    parent_id, athlete_id = _make_family(client)
    shared_token = "ExponentPushToken[shared-device-xyz]"

    client.post(
        "/api/notifications/expo-token", json={"token": shared_token, "athlete_id": athlete_id},
        headers=auth_headers("athlete", athlete_id=athlete_id, parent_id=parent_id),
    )
    r = client.post(
        "/api/notifications/expo-token", json={"token": shared_token, "parent_id": parent_id},
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 200, r.text

    row = _row_for_token(shared_token)
    assert row["parent_id"] == parent_id
    assert row["athlete_id"] == athlete_id


def test_re_registering_with_the_same_ids_still_updates_platform_and_timezone(client):
    """The COALESCE fix must not accidentally freeze platform/timezone in place —
    those should still update normally on every call."""
    parent_id, _ = _make_family(client)
    shared_token = "ExponentPushToken[refresh-test]"
    headers = auth_headers("parent", parent_id=parent_id)

    client.post("/api/notifications/expo-token", json={
        "token": shared_token, "parent_id": parent_id, "platform": "ios", "timezone": "America/Denver",
    }, headers=headers)
    r = client.post("/api/notifications/expo-token", json={
        "token": shared_token, "parent_id": parent_id, "platform": "android", "timezone": "America/New_York",
    }, headers=headers)
    assert r.status_code == 200, r.text

    conn = get_conn()
    row = conn.execute(
        "SELECT platform, timezone FROM expo_push_tokens WHERE token = ?", (shared_token,)
    ).fetchone()
    conn.close()
    assert row["platform"] == "android"
    assert row["timezone"] == "America/New_York"


def test_no_session_token_rejected(client):
    parent_id, _ = _make_family(client)
    r = client.post("/api/notifications/expo-token", json={
        "token": "ExponentPushToken[no-auth]", "parent_id": parent_id,
    })
    assert r.status_code == 401, r.text


def test_registering_someone_elses_athlete_id_rejected(client):
    _, victim_athlete_id = _make_family(client)
    attacker_parent_id, attacker_athlete_id = _make_family(client)

    r = client.post(
        "/api/notifications/expo-token",
        json={"token": "ExponentPushToken[attacker-device]", "athlete_id": victim_athlete_id},
        headers=auth_headers("athlete", athlete_id=attacker_athlete_id, parent_id=attacker_parent_id),
    )
    assert r.status_code == 403, r.text
    assert _row_for_token("ExponentPushToken[attacker-device]") is None, (
        "A token was registered against an athlete the caller does not own."
    )


def test_registering_someone_elses_parent_id_rejected(client):
    victim_parent_id, _ = _make_family(client)
    attacker_parent_id, _ = _make_family(client)

    r = client.post(
        "/api/notifications/expo-token",
        json={"token": "ExponentPushToken[attacker-parent-device]", "parent_id": victim_parent_id},
        headers=auth_headers("parent", parent_id=attacker_parent_id),
    )
    assert r.status_code == 403, r.text
    assert _row_for_token("ExponentPushToken[attacker-parent-device]") is None
