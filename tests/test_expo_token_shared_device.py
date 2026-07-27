"""
Regression: POST /api/notifications/expo-token overwriting the OTHER
profile's id on a shared device.

A push token belongs to a device, not a person. On a shared family device
(one tablet/phone used by both a parent and an athlete), a parent's
registration and an athlete's registration carry the SAME token. Since
token is the unique key, the old unconditional UPDATE (athlete_id=excluded.
athlete_id, parent_id=excluded.parent_id) blanked out whichever id the
current call didn't send — e.g. the athlete's later registration (no
parent_id in that payload) wiped the parent_id a prior registration had
set, silently killing the parent's push notifications with no error
anywhere. Fixed via COALESCE(excluded.x, expo_push_tokens.x) so a token can
carry both ids at once.
"""
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app


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


def test_athlete_registering_the_same_shared_device_token_does_not_wipe_the_parent(client):
    shared_token = "ExponentPushToken[shared-device-abc]"

    r1 = client.post("/api/notifications/expo-token", json={"token": shared_token, "parent_id": 42})
    assert r1.status_code == 200, r1.text

    row = _row_for_token(shared_token)
    assert row["parent_id"] == 42
    assert row["athlete_id"] is None

    r2 = client.post("/api/notifications/expo-token", json={"token": shared_token, "athlete_id": 59})
    assert r2.status_code == 200, r2.text

    row = _row_for_token(shared_token)
    assert row["athlete_id"] == 59
    assert row["parent_id"] == 42, (
        "Parent's id was wiped when the athlete registered the same shared-device token."
    )


def test_parent_registering_the_same_shared_device_token_does_not_wipe_the_athlete(client):
    """Same bug, opposite order — the athlete registers first."""
    shared_token = "ExponentPushToken[shared-device-xyz]"

    client.post("/api/notifications/expo-token", json={"token": shared_token, "athlete_id": 77})
    r = client.post("/api/notifications/expo-token", json={"token": shared_token, "parent_id": 10})
    assert r.status_code == 200, r.text

    row = _row_for_token(shared_token)
    assert row["parent_id"] == 10
    assert row["athlete_id"] == 77


def test_re_registering_with_the_same_ids_still_updates_platform_and_timezone(client):
    """The COALESCE fix must not accidentally freeze platform/timezone in place —
    those should still update normally on every call."""
    shared_token = "ExponentPushToken[refresh-test]"

    client.post("/api/notifications/expo-token", json={
        "token": shared_token, "parent_id": 5, "platform": "ios", "timezone": "America/Denver",
    })
    r = client.post("/api/notifications/expo-token", json={
        "token": shared_token, "parent_id": 5, "platform": "android", "timezone": "America/New_York",
    })
    assert r.status_code == 200, r.text

    conn = get_conn()
    row = conn.execute(
        "SELECT platform, timezone FROM expo_push_tokens WHERE token = ?", (shared_token,)
    ).fetchone()
    conn.close()
    assert row["platform"] == "android"
    assert row["timezone"] == "America/New_York"
