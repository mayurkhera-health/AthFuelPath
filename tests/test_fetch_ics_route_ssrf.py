"""Route-level SSRF + auth regression tests — GET /api/events/fetch-ics
(Security Hardening Pass 1, item 10). The underlying guard (_is_public_host /
fetch_ics_text) is already unit-tested against api/services/ics_sync.py in
tests/test_ics_sync_ssrf.py; this file proves the route itself (a) requires
a session and (b) actually wires that guard in — malicious hosts must be
rejected with a clean 400 before any network call, and a redirect to a
private address must not be followed. A real public host still passes
through (network mocked at the httpx layer, matching the service-level
tests' style).
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_fetch_ics_requires_a_session(client):
    r = client.get("/api/events/fetch-ics", params={"url": "https://calendar.example.com/feed.ics"})
    assert r.status_code == 401


@pytest.mark.parametrize("url", [
    "https://localhost/feed.ics",
    "https://127.0.0.1/feed.ics",
    "https://[::1]/feed.ics",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/feed.ics",
    "https://192.168.1.1/feed.ics",
    "https://172.16.0.1/feed.ics",
])
def test_fetch_ics_rejects_disallowed_hosts_without_making_any_request(client, monkeypatch, url):
    from api.services import ics_sync
    monkeypatch.setattr(
        ics_sync.httpx, "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch a disallowed host")),
    )
    headers = auth_headers("parent", parent_id=1)
    r = client.get("/api/events/fetch-ics", params={"url": url}, headers=headers)
    assert r.status_code == 400, r.text


def test_fetch_ics_rejects_a_redirect_that_points_at_a_private_address(client, monkeypatch):
    from api.services import ics_sync

    def fake_is_public(host):
        return host != "internal-service.local"
    monkeypatch.setattr(ics_sync, "_is_public_host", fake_is_public)

    class _FakeResponse:
        status_code = 302
        headers = {"location": "https://internal-service.local/secrets"}

    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        return _FakeResponse()

    monkeypatch.setattr(ics_sync.httpx, "get", fake_get)
    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "https://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert call_count["n"] == 1, "must not follow the redirect to the internal host"


def test_fetch_ics_allows_a_valid_public_ics_url(client, monkeypatch):
    from api.services import ics_sync

    monkeypatch.setattr(ics_sync, "_is_public_host", lambda host: True)

    class _FakeResponse:
        status_code = 200
        text = "BEGIN:VCALENDAR\nEND:VCALENDAR"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(ics_sync.httpx, "get", lambda *a, **k: _FakeResponse())
    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "https://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert "BEGIN:VCALENDAR" in r.json()["content"]


def test_fetch_ics_normalizes_webcal_scheme_for_a_valid_public_host(client, monkeypatch):
    from api.services import ics_sync

    monkeypatch.setattr(ics_sync, "_is_public_host", lambda host: True)

    class _FakeResponse:
        status_code = 200
        text = "BEGIN:VCALENDAR\nEND:VCALENDAR"

        def raise_for_status(self):
            pass

    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        return _FakeResponse()

    monkeypatch.setattr(ics_sync.httpx, "get", fake_get)
    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "webcal://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert seen["url"].startswith("https://")
