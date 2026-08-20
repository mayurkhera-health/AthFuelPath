"""BOLA/auth regression test — POST /api/parents/{parent_id}/confirm
(Security Hardening Pass 1, item 8). Previously unauthenticated: anyone
could flip consent_confirmed=TRUE for an arbitrary parent_id.
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
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def make_parent(email, confirmed=False):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), confirmed),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def test_confirm_consent_requires_a_session(client):
    victim_id = make_parent("confirm1@example.com", confirmed=False)
    r = client.post(f"/api/parents/{victim_id}/confirm")
    assert r.status_code == 401
    row = get_conn().execute("SELECT consent_confirmed FROM parents WHERE id=%s", (victim_id,)).fetchone()
    assert row["consent_confirmed"] is False


def test_confirm_consent_rejects_unrelated_parent(client):
    victim_id = make_parent("confirm2-victim@example.com", confirmed=False)
    attacker_id = make_parent("confirm2-attacker@example.com", confirmed=True)
    r = client.post(
        f"/api/parents/{victim_id}/confirm",
        headers=auth_headers("parent", parent_id=attacker_id),
    )
    assert r.status_code == 403
    row = get_conn().execute("SELECT consent_confirmed FROM parents WHERE id=%s", (victim_id,)).fetchone()
    assert row["consent_confirmed"] is False


def test_confirm_consent_allows_owner(client):
    parent_id = make_parent("confirm3@example.com", confirmed=False)
    r = client.post(
        f"/api/parents/{parent_id}/confirm",
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 200, r.text
    row = get_conn().execute("SELECT consent_confirmed FROM parents WHERE id=%s", (parent_id,)).fetchone()
    assert row["consent_confirmed"] is True
