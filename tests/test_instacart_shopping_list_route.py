"""Integration tests for POST /api/instacart/shopping-list, mirroring
tests/test_instacart_feedback_route.py's fixture setup. Instacart's HTTP client
(instacart_client.requests) is monkeypatched — no test calls a real Instacart
endpoint, per the same style as tests/test_weather_location.py."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services import instacart_client
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def _instacart_flags(monkeypatch):
    # Via monkeypatch (reverts after each test) rather than a bare os.environ
    # assignment, so the flags don't leak into later test files sharing this
    # process (see the identical fix in test_plate_route.py). pytest's
    # monkeypatch fixture is function-scoped only, so this can't be
    # module-scoped alongside the module-scoped `client` fixture below —
    # function scope is fine since these are plain env reads, not one-time
    # setup.
    monkeypatch.setenv("INSTACART_SHOPPING_LIST_ENABLED", "true")
    monkeypatch.setenv("INSTACART_API_KEY", "test-key")


@pytest.fixture(scope="module")
def client():
    # Module-scoped: a single TestClient/lifespan cycle for the whole file, not
    # one per test. Cycling the app's lifespan (migrations + scheduler startup)
    # once per test against the shared in-memory DB caused intermittent
    # "database is locked" errors — one cycle for the module matches how the
    # rest of this suite exercises TestClient without that flakiness.
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    keepalive.execute(
        """INSERT INTO athletes (id, first_name, age, gender, weight_lbs, height_ft, height_in)
           VALUES (1, 'Test Athlete', 15, 'boy', 120.0, 5, 6.0)"""
    )
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


class _FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _stub_instacart(monkeypatch, status_code=200, body=None, side_effect=None):
    body = body if body is not None else {"products_link_url": "https://www.instacart.com/store/x"}

    def fake_post(url, json=None, headers=None, timeout=None):
        if side_effect:
            raise side_effect
        assert "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
        return _FakeResp(status_code, body)

    monkeypatch.setattr(instacart_client.requests, "post", fake_post)


VALID_PAYLOAD = {
    "athlete_id": 1,
    "title": "Weekly groceries",
    "items": [{"name": "whole milk", "quantity": 1, "unit": "gallon"}],
}
# NOT computed at import time: auth_headers() now guarantees an
# athlete_logins row exists for athlete_id (docs/planning/
# parent-initiated-athlete-unlink.md), which requires athlete 1 to already
# be in `athletes` -- that row is only inserted inside the `client` fixture
# below, which hasn't run yet at module import time. Recomputed by the
# autouse fixture right after `client` runs, once per test.
HEADERS = None


@pytest.fixture(autouse=True)
def _refresh_headers(client):
    global HEADERS
    HEADERS = auth_headers("athlete", athlete_id=1)


def test_happy_path_returns_shopping_list_url(client, monkeypatch):
    _stub_instacart(monkeypatch)
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider"] == "instacart"
    assert body["shopping_list_url"] == "https://www.instacart.com/store/x"
    assert body["requires_user_review"] is True


def test_flag_disabled_returns_404(client, monkeypatch):
    monkeypatch.setenv("INSTACART_SHOPPING_LIST_ENABLED", "false")
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 404


def test_unknown_athlete_returns_404(client, monkeypatch):
    _stub_instacart(monkeypatch)
    payload = {**VALID_PAYLOAD, "athlete_id": 999}
    r = client.post(
        "/api/instacart/shopping-list", json=payload, headers=auth_headers("parent", parent_id=1),
    )
    assert r.status_code == 404


def test_empty_items_rejected_with_400(client):
    payload = {**VALID_PAYLOAD, "items": []}
    r = client.post("/api/instacart/shopping-list", json=payload, headers=HEADERS)
    assert r.status_code == 422  # FastAPI/Pydantic validation error


def test_missing_api_key_returns_safe_500(client, monkeypatch):
    monkeypatch.delenv("INSTACART_API_KEY", raising=False)
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 500
    assert "test-key" not in r.text


def test_instacart_auth_failure_returns_safe_502(client, monkeypatch):
    _stub_instacart(monkeypatch, status_code=401, body={})
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 502
    assert "401" not in r.text  # no raw upstream status/body leaked to the client


def test_instacart_validation_error_returns_400(client, monkeypatch):
    _stub_instacart(monkeypatch, status_code=400, body={
        "error_code": 1001,
        "message": "Invalid quantity: -0.1. Cannot be lower than or equal to 0.0",
    })
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 400
    # We show our own generic message, not Instacart's raw error text.
    assert "Cannot be lower than" not in r.text


def test_instacart_rate_limit_returns_429(client, monkeypatch):
    _stub_instacart(monkeypatch, status_code=429, body={})
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 429


def test_instacart_5xx_returns_safe_502(client, monkeypatch):
    _stub_instacart(monkeypatch, status_code=503, body={})
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 502


def test_network_timeout_returns_safe_502(client, monkeypatch):
    _stub_instacart(monkeypatch, side_effect=instacart_client.requests.Timeout("timed out"))
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 502


def test_malformed_response_missing_url_returns_safe_502(client, monkeypatch):
    _stub_instacart(monkeypatch, status_code=200, body={"unexpected": "shape"})
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 502


def test_unsafe_returned_url_rejected(client, monkeypatch):
    _stub_instacart(monkeypatch, status_code=200, body={"products_link_url": "https://evil.example.com/x"})
    r = client.post("/api/instacart/shopping-list", json=VALID_PAYLOAD, headers=HEADERS)
    assert r.status_code == 502
