"""
Integration tests for legacy email-only login routes — proving they stay gone.

POST /api/auth/login and POST /api/parents/login were retired in auth v2.1
Phase 4 (email-only session issuance removed) in favor of the OTP-verified
POST /api/auth/email/request + /email/verify flow (tests/test_email_auth_flow.py).

This file used to also cover POST /api/auth/athlete-claim-lookup and
POST /api/auth/athlete-create-login/{athlete_id} — both removed
(family-account-onboarding spec addendum, item 2, 2026-09-04) along with the
routes themselves: that was the old email-based athlete-claim flow (a
parent's email alone was enough to discover their athletes and drive account
creation). Replaced by the code-first family-linking flow plus
tests/test_family_unlink.py's parent-initiated unlink, the one remaining
recovery path — and that one requires an authenticated parent session, never
an email address.
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
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def test_legacy_unified_login_endpoint_is_gone(client):
    r = client.post("/api/auth/login", json={"email": "anyone@example.com"})
    assert r.status_code == 404, r.text


def test_legacy_parents_login_endpoint_is_gone(client):
    # Not a clean 404: parents.py's GET/DELETE /{parent_id} use an untyped
    # (string) path param, so they partially match the path "/login" too —
    # pre-existing, unrelated to this deletion. Starlette reports 405
    # (method not allowed on the matched path) rather than 404 in that case.
    # Either way, no route accepts POST here anymore, so no session is
    # ever minted from this path — the property this test exists to prove.
    r = client.post("/api/parents/login", json={"email": "anyone@example.com"})
    assert r.status_code == 405, r.text


def test_athlete_claim_lookup_route_is_gone(client):
    r = client.post("/api/auth/athlete-claim-lookup", json={"parent_email": "anyone@example.com"})
    assert r.status_code == 404, r.text


def test_athlete_create_login_route_is_gone(client):
    r = client.post(
        "/api/auth/athlete-create-login/1",
        json={"email": "a@x.com", "parent_email": "p@x.com", "code": "000000"},
    )
    assert r.status_code == 404, r.text
