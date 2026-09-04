"""
DELETE /api/families/{parent_id}/athletes/{athlete_id}/link — parent-initiated
unlink, the only recovery path for an athlete whose provider identity (Apple/
Google) becomes unusable. Replaces the old email-based athlete-claim flow —
see docs/planning/family-account-onboarding-spec.md in the mobile repo for
the full addendum this implements.

Security properties under test:
  - Only the owning parent, in a live session, can unlink — never by email.
  - auth_identities (and, via ON DELETE CASCADE, apple_provider_credentials)
    and athlete_logins are actually removed.
  - A session token minted for the athlete BEFORE the unlink is rejected on
    its very next authenticated request — session tokens are stateless with
    no revocation list, so this only works because assert_owns_athlete()
    re-checks athlete_logins on every athlete-role call (session_auth.py).
  - The unlink is durably logged with the PARENT as actor, not the fixed
    admin actor write_audit() defaults to elsewhere.
  - Re-linking the same Apple provider_subject afterward doesn't hit a
    leftover uniqueness constraint.
"""
import base64
import os

os.environ["DB_PATH"] = ":memory:"

import psycopg
import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services.session_auth import mint_session_token, verify_session_token, SessionIdentity, assert_owns_athlete
from fastapi import HTTPException

TEST_KEY_B64 = base64.b64encode(b"0" * 32).decode()


@pytest.fixture(autouse=True)
def _provider_credential_key(monkeypatch):
    monkeypatch.setenv("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", TEST_KEY_B64)


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM admin_audit_log")
    keepalive.execute("DELETE FROM apple_provider_credentials")
    keepalive.execute("DELETE FROM auth_identities")
    keepalive.execute("DELETE FROM athlete_logins")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def _make_parent_and_athlete(conn, parent_email="parent@x.com"):
    parent_id = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES ('P', %s, sqlite_now(), TRUE) RETURNING id", (parent_email,)
    ).fetchone()["id"]
    athlete_id = conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, 'Jake', 15, 'boy', 130, 5, 8) RETURNING id", (parent_id,)
    ).fetchone()["id"]
    return parent_id, athlete_id


def _claim_athlete(conn, athlete_id, provider_subject="apple-sub-1"):
    """Simulate a fully claimed athlete: a login row, an apple auth_identity,
    and its credential row — the full set unlink must clean up."""
    conn.execute(
        "INSERT INTO athlete_logins (email, athlete_id) VALUES ('jake@x.com', %s)", (athlete_id,)
    )
    identity_id = conn.execute(
        "INSERT INTO auth_identities (provider, provider_subject, athlete_id, email, email_verified) "
        "VALUES ('apple', %s, %s, 'jake@x.com', TRUE) RETURNING id", (provider_subject, athlete_id)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO apple_provider_credentials (auth_identity_id, encrypted_refresh_token, encryption_nonce) "
        "VALUES (%s, %s, %s)", (identity_id, b"ciphertext", b"nonce123456")
    )
    conn.commit()


def test_unlink_requires_parent_session(client):
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn)
    _claim_athlete(conn, athlete_id)
    athlete_token = mint_session_token(role="athlete", athlete_id=athlete_id, parent_id=parent_id)
    resp = client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {athlete_token}"},
    )
    assert resp.status_code == 403


def test_unlink_rejects_non_owning_parent(client):
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn, "owner@x.com")
    other_parent_id, _ = _make_parent_and_athlete(conn, "stranger@x.com")
    _claim_athlete(conn, athlete_id)
    other_token = mint_session_token(role="parent", parent_id=other_parent_id)
    resp = client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


def test_unlink_removes_identity_credential_and_login(client):
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn)
    _claim_athlete(conn, athlete_id)
    parent_token = mint_session_token(role="parent", parent_id=parent_id)

    resp = client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"unlinked": True, "athlete_id": athlete_id}

    assert conn.execute(
        "SELECT 1 FROM athlete_logins WHERE athlete_id = %s", (athlete_id,)
    ).fetchone() is None
    assert conn.execute(
        "SELECT 1 FROM auth_identities WHERE athlete_id = %s", (athlete_id,)
    ).fetchone() is None
    # ON DELETE CASCADE from auth_identities -> apple_provider_credentials
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM apple_provider_credentials"
    ).fetchone()["c"] == 0


def test_unlink_invalidates_a_token_minted_before_the_unlink(client):
    """GET /api/auth/session deliberately doesn't call assert_owns_athlete
    (it does its own separate athlete_logins lookup, for display context,
    not enforcement — see its docstring) — so it can't be used to observe
    this. Every athlete_id/parent_id-scoped route DOES call
    assert_owns_athlete/assert_owns_parent (CLAUDE.md: "treat a new route
    that skips this as a bug, not a pattern to copy"), so exercising that
    function directly against the pre-unlink token is the real integration
    point, not an implementation-detail shortcut."""
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn)
    _claim_athlete(conn, athlete_id)

    stale_athlete_token = mint_session_token(role="athlete", athlete_id=athlete_id, parent_id=parent_id)
    stale_payload = verify_session_token(stale_athlete_token)
    stale_identity = SessionIdentity(stale_payload["role"], stale_payload.get("parent_id"), stale_payload.get("athlete_id"))
    # Prove the token is genuinely live before the unlink.
    assert_owns_athlete(stale_identity, athlete_id, conn)  # does not raise

    parent_token = mint_session_token(role="parent", parent_id=parent_id)
    assert client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {parent_token}"},
    ).status_code == 200

    # Signature and athlete_id still check out — only the DB-backed
    # athlete_logins check should be what rejects this now.
    assert verify_session_token(stale_athlete_token) is not None
    with pytest.raises(HTTPException) as exc:
        assert_owns_athlete(stale_identity, athlete_id, conn)
    assert exc.value.status_code == 401


def test_unlink_logs_the_parent_as_actor_not_the_admin_default(client):
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn, "actor-check@x.com")
    _claim_athlete(conn, athlete_id)
    parent_token = mint_session_token(role="parent", parent_id=parent_id)

    client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {parent_token}"},
    )

    row = conn.execute(
        "SELECT actor_id, actor_email, actor_role, action, target_type, target_id "
        "FROM admin_audit_log WHERE action = 'unlink_athlete'"
    ).fetchone()
    assert row is not None
    row = dict(row)
    assert row["actor_id"] == parent_id
    assert row["actor_email"] == "actor-check@x.com"
    assert row["actor_role"] == "parent"
    assert row["target_type"] == "athlete"
    assert row["target_id"] == athlete_id


def test_unlink_409s_when_athlete_has_no_active_login(client):
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn)
    conn.commit()  # never claimed — no athlete_logins/auth_identities rows
    parent_token = mint_session_token(role="parent", parent_id=parent_id)

    resp = client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert resp.status_code == 409


def test_relinking_the_same_apple_subject_after_unlink_succeeds(client):
    """Regression guard for the uniqueness question raised during spec review:
    UNIQUE(provider, provider_subject) and the partial one-per-athlete index
    only block a DUPLICATE row existing at the same time — deleting the old
    row via unlink must free the key for a fresh insert with the identical
    provider_subject."""
    conn = get_conn()
    parent_id, athlete_id = _make_parent_and_athlete(conn)
    _claim_athlete(conn, athlete_id, provider_subject="reused-sub")
    parent_token = mint_session_token(role="parent", parent_id=parent_id)

    assert client.request(
        "DELETE", f"/api/families/{parent_id}/athletes/{athlete_id}/link",
        headers={"Authorization": f"Bearer {parent_token}"},
    ).status_code == 200

    # Re-link: same provider_subject, same athlete — must not raise a
    # unique-violation now that the old row is gone.
    conn.execute(
        "INSERT INTO auth_identities (provider, provider_subject, athlete_id, email, email_verified) "
        "VALUES ('apple', 'reused-sub', %s, 'jake@x.com', TRUE)", (athlete_id,)
    )
    conn.execute(
        "INSERT INTO athlete_logins (email, athlete_id) VALUES ('jake@x.com', %s)", (athlete_id,)
    )
    conn.commit()
    assert conn.execute(
        "SELECT 1 FROM auth_identities WHERE provider_subject = 'reused-sub'"
    ).fetchone() is not None
