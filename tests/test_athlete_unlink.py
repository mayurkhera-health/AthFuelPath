"""DELETE /api/athletes/{id}/unlink — parent-initiated athlete unlink
(docs/planning/parent-initiated-athlete-unlink.md). Recovery path for an
athlete whose provider identity became unusable, replacing the removed
athlete-claim.tsx flow. Parent-only, hard-deletes auth_identities +
athlete_logins, logs the action, and must invalidate any already-issued
athlete session token on its very next request."""
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
    keepalive.execute("DELETE FROM athlete_unlink_log")
    keepalive.execute("DELETE FROM apple_provider_credentials")
    keepalive.execute("DELETE FROM auth_identities")
    keepalive.execute("DELETE FROM athlete_logins")
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
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (%s, %s, %s, %s) RETURNING id",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), True),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Jake"):
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


def link_athlete(athlete_id, email, provider_subject="apple-sub-1"):
    """Simulates a fully claimed + provider-linked athlete: an
    athlete_logins row plus an auth_identities row with a cascading
    apple_provider_credentials row."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO athlete_logins (email, athlete_id) VALUES (%s, %s)",
            (email, athlete_id),
        )
        cur = conn.execute(
            "INSERT INTO auth_identities (provider, provider_subject, athlete_id, email, email_verified) "
            "VALUES ('apple', %s, %s, %s, TRUE) RETURNING id",
            (provider_subject, athlete_id, email),
        )
        identity_id = cur.fetchone()["id"]
        conn.execute(
            "INSERT INTO apple_provider_credentials (auth_identity_id, encrypted_refresh_token, encryption_nonce) "
            "VALUES (%s, %s, %s)",
            (identity_id, b"ciphertext", b"nonce"),
        )
        conn.commit()
        return identity_id
    finally:
        conn.close()


def test_unlink_requires_a_session(client):
    parent_id = make_parent("v1@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.delete(f"/api/athletes/{athlete_id}/unlink")
    assert r.status_code == 401


def test_unlink_rejects_athlete_role_token_even_for_self(client):
    """Security property: recovery must be parent-initiated, never
    self-service by the athlete's own (possibly compromised) session."""
    parent_id = make_parent("v2@example.com")
    athlete_id = make_athlete(parent_id)
    link_athlete(athlete_id, "jake2@example.com")
    r = client.delete(
        f"/api/athletes/{athlete_id}/unlink",
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT 1 FROM athlete_logins WHERE athlete_id=%s", (athlete_id,)
    ).fetchone()


def test_unlink_rejects_unrelated_parent(client):
    victim_parent = make_parent("v3@example.com")
    athlete_id = make_athlete(victim_parent)
    link_athlete(athlete_id, "jake3@example.com")
    attacker_parent = make_parent("attacker3@example.com")
    r = client.delete(
        f"/api/athletes/{athlete_id}/unlink",
        headers=auth_headers("parent", parent_id=attacker_parent),
    )
    assert r.status_code == 403
    assert get_conn().execute(
        "SELECT 1 FROM athlete_logins WHERE athlete_id=%s", (athlete_id,)
    ).fetchone()


def test_unlink_404s_on_unknown_athlete(client):
    parent_id = make_parent("v4@example.com")
    r = client.delete(
        f"/api/athletes/999999/unlink",
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 404


def test_unlink_by_owning_parent_deletes_identity_rows_cascades_credentials_and_logs(client):
    parent_id = make_parent("owner4@example.com")
    athlete_id = make_athlete(parent_id)
    identity_id = link_athlete(athlete_id, "jake4@example.com")

    r = client.delete(
        f"/api/athletes/{athlete_id}/unlink",
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 200
    assert r.json() == {"unlinked": True, "athlete_id": athlete_id}

    conn = get_conn()
    assert conn.execute(
        "SELECT 1 FROM athlete_logins WHERE athlete_id=%s", (athlete_id,)
    ).fetchone() is None
    assert conn.execute(
        "SELECT 1 FROM auth_identities WHERE athlete_id=%s", (athlete_id,)
    ).fetchone() is None
    assert conn.execute(
        "SELECT 1 FROM apple_provider_credentials WHERE auth_identity_id=%s", (identity_id,)
    ).fetchone() is None, "apple_provider_credentials must cascade-delete with its auth_identities row"

    log_row = conn.execute(
        "SELECT athlete_id, actor_parent_id FROM athlete_unlink_log WHERE athlete_id=%s", (athlete_id,)
    ).fetchone()
    assert dict(log_row) == {"athlete_id": athlete_id, "actor_parent_id": parent_id}

    # The athlete row itself is untouched — unlink returns the athlete to
    # unclaimed state, it does not delete the profile.
    assert conn.execute("SELECT 1 FROM athletes WHERE id=%s", (athlete_id,)).fetchone()


def test_unlink_invalidates_the_athletes_existing_session_immediately(client):
    """The security-critical property: an already-issued athlete token
    must stop authenticating on its very next request, with no wait for
    token expiry (session_auth.assert_owns_athlete now re-checks
    athlete_logins liveness on every athlete-role call)."""
    parent_id = make_parent("owner5@example.com")
    athlete_id = make_athlete(parent_id)
    link_athlete(athlete_id, "jake5@example.com")
    old_athlete_token_headers = auth_headers("athlete", athlete_id=athlete_id)

    # Sanity: the token works before unlink.
    pre = client.get(f"/api/athletes/{athlete_id}", headers=old_athlete_token_headers)
    assert pre.status_code == 200

    unlink = client.delete(
        f"/api/athletes/{athlete_id}/unlink",
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert unlink.status_code == 200

    post = client.get(f"/api/athletes/{athlete_id}", headers=old_athlete_token_headers)
    assert post.status_code == 401
