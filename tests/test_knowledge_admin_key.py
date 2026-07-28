"""
Regression: the admin gate shared by legal.py, knowledge.py, and library.py
used to default to the hardcoded literal "fuelup-admin" whenever
KNOWLEDGE_ADMIN_KEY wasn't configured — a working admin credential baked into
this public source tree. Fixed via api/services/knowledge_admin.py's
require_knowledge_admin_key, which fails closed (500) when the real key isn't
set, rather than silently accepting a guessable default.
"""
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services.knowledge_admin import require_knowledge_admin_key


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


# ── unit tests on the shared helper ────────────────────────────────────────────

def test_helper_fails_closed_when_key_unset(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ADMIN_KEY", raising=False)
    with pytest.raises(Exception) as exc_info:
        require_knowledge_admin_key("fuelup-admin")  # even the old default string
    assert exc_info.value.status_code == 500


def test_helper_rejects_wrong_key_when_configured(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ADMIN_KEY", "a-real-strong-key")
    with pytest.raises(Exception) as exc_info:
        require_knowledge_admin_key("fuelup-admin")
    assert exc_info.value.status_code == 403


def test_helper_accepts_correct_key_when_configured(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ADMIN_KEY", "a-real-strong-key")
    require_knowledge_admin_key("a-real-strong-key")  # must not raise


# ── route-level: knowledge.py ──────────────────────────────────────────────────

def test_knowledge_admin_route_fails_closed_without_configured_key(client, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ADMIN_KEY", raising=False)
    r = client.get("/api/knowledge/", headers={"X-Admin-Key": "fuelup-admin"})
    assert r.status_code == 500, r.text


def test_knowledge_admin_route_works_with_real_configured_key(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ADMIN_KEY", "a-real-strong-key")
    r = client.get("/api/knowledge/", headers={"X-Admin-Key": "a-real-strong-key"})
    assert r.status_code == 200, r.text
    r_wrong = client.get("/api/knowledge/", headers={"X-Admin-Key": "fuelup-admin"})
    assert r_wrong.status_code == 403, r_wrong.text


# ── route-level: library.py ────────────────────────────────────────────────────

def _article_payload():
    return {
        "title": "Test Article", "summary": "s", "body_markdown": "b",
        "category": "iron", "audience": "both", "read_time_min": 3,
        "published_date": "2026-07-27",
    }


def test_library_admin_route_fails_closed_without_configured_key(client, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ADMIN_KEY", raising=False)
    r = client.post("/api/library/articles", json=_article_payload(),
                     headers={"X-Admin-Key": "fuelup-admin"})
    assert r.status_code == 500, r.text


def test_library_admin_route_works_with_real_configured_key(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ADMIN_KEY", "a-real-strong-key")
    r_wrong = client.post("/api/library/articles", json=_article_payload(),
                           headers={"X-Admin-Key": "fuelup-admin"})
    assert r_wrong.status_code == 403, r_wrong.text
    r = client.post("/api/library/articles", json=_article_payload(),
                     headers={"X-Admin-Key": "a-real-strong-key"})
    assert r.status_code == 200, r.text


# ── route-level: legal.py ──────────────────────────────────────────────────────

def test_legal_admin_route_fails_closed_without_configured_key(client, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ADMIN_KEY", raising=False)
    r = client.put("/api/legal/privacy-policy", json={"content": "new text"},
                    headers={"X-Admin-Key": "fuelup-admin"})
    assert r.status_code == 500, r.text


def test_legal_admin_route_works_with_real_configured_key(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ADMIN_KEY", "a-real-strong-key")
    r_wrong = client.put("/api/legal/privacy-policy", json={"content": "new text"},
                          headers={"X-Admin-Key": "fuelup-admin"})
    assert r_wrong.status_code == 403, r_wrong.text
    r = client.put("/api/legal/privacy-policy", json={"content": "new text"},
                    headers={"X-Admin-Key": "a-real-strong-key"})
    assert r.status_code == 200, r.text
