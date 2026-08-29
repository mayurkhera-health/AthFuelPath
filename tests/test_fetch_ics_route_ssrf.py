"""Route-level SSRF + auth regression tests — GET /api/events/fetch-ics
(Security Hardening Pass 1, item 10; extended in Item 3's SSRF hardening
pass). The underlying guard (_resolve_validated_ips / fetch_ics_text) is
already unit-tested against api/services/ics_sync.py in
tests/test_ics_sync_ssrf.py; this file proves the route itself (a) requires
a session and (b) actually wires that guard in — malicious hosts must be
rejected with a clean 400 before any network call, and a redirect to a
private address must not be followed. A real public host still passes
through (network mocked at the httpx.Client layer, matching the
service-level tests' style — fetch_ics_text now issues requests via
httpx.Client(...).stream(...) rather than the module-level httpx.get()).
"""
import socket
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *a):
        return False


class _FakeResponse:
    def __init__(self, status_code=200, body=b"", headers=None, encoding="utf-8"):
        self.status_code = status_code
        self._body = body if isinstance(body, bytes) else body.encode()
        self.headers = headers or {}
        self.encoding = encoding

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def iter_bytes(self):
        step = 4096
        for i in range(0, len(self._body), step):
            yield self._body[i:i + step]


class _FakeHttpxClient:
    def __init__(self, handler, calls):
        self.handler = handler
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, method, url, headers=None, extensions=None, follow_redirects=False):
        self.calls.append({"url": url, "headers": headers, "extensions": extensions})
        return _FakeStreamCtx(self.handler(method, url, headers, extensions))


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
    "https://100.64.0.1/feed.ics",
])
def test_fetch_ics_rejects_disallowed_hosts_without_making_any_request(client, monkeypatch, url):
    from api.services import ics_sync
    monkeypatch.setattr(
        ics_sync.httpx, "Client",
        lambda **k: (_ for _ in ()).throw(AssertionError("must not open a client for a disallowed host")),
    )
    headers = auth_headers("parent", parent_id=1)
    r = client.get("/api/events/fetch-ics", params={"url": url}, headers=headers)
    assert r.status_code == 400, r.text


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://public-host.example/feed.ics",
    "gopher://public-host.example/feed.ics",
])
def test_fetch_ics_rejects_non_http_schemes(client, monkeypatch, url):
    from api.services import ics_sync
    monkeypatch.setattr(
        ics_sync.httpx, "Client",
        lambda **k: (_ for _ in ()).throw(AssertionError("must not fetch a non-http(s) scheme")),
    )
    headers = auth_headers("parent", parent_id=1)
    r = client.get("/api/events/fetch-ics", params={"url": url}, headers=headers)
    assert r.status_code == 400, r.text


def test_fetch_ics_rejects_a_redirect_that_points_at_a_private_address(client, monkeypatch):
    from api.services import ics_sync

    def fake_getaddrinfo(host, *a, **k):
        if host == "internal-service.local":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    calls = []

    def handler(method, url, headers, extensions):
        return _FakeResponse(302, headers={"location": "https://internal-service.local/secrets"})
    monkeypatch.setattr(ics_sync.httpx, "Client", lambda **k: _FakeHttpxClient(handler, calls))

    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "https://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert len(calls) == 1, "must not follow the redirect to the internal host"


def test_fetch_ics_allows_a_valid_public_ics_url(client, monkeypatch):
    from api.services import ics_sync

    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    calls = []

    def handler(method, url, headers, extensions):
        return _FakeResponse(200, body=b"BEGIN:VCALENDAR\nEND:VCALENDAR")
    monkeypatch.setattr(ics_sync.httpx, "Client", lambda **k: _FakeHttpxClient(handler, calls))

    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "https://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert "BEGIN:VCALENDAR" in r.json()["content"]
    # Proves pinning: the actual connection targets the resolved IP, not the
    # hostname, with the original hostname preserved for Host + TLS SNI.
    assert urlparse(calls[0]["url"]).hostname == "93.184.216.34"
    assert calls[0]["headers"]["Host"] == "calendar.byga.example.com"
    assert calls[0]["extensions"] == {"sni_hostname": "calendar.byga.example.com"}


def test_fetch_ics_normalizes_webcal_scheme_for_a_valid_public_host(client, monkeypatch):
    from api.services import ics_sync

    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    calls = []

    def handler(method, url, headers, extensions):
        return _FakeResponse(200, body=b"BEGIN:VCALENDAR\nEND:VCALENDAR")
    monkeypatch.setattr(ics_sync.httpx, "Client", lambda **k: _FakeHttpxClient(handler, calls))

    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "webcal://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert urlparse(calls[0]["url"]).scheme == "https"


def test_fetch_ics_rejects_an_oversized_feed(client, monkeypatch):
    from api.services import ics_sync

    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    calls = []
    body = b"x" * (ics_sync._MAX_ICS_BYTES + 1)

    def handler(method, url, headers, extensions):
        return _FakeResponse(200, body=body)
    monkeypatch.setattr(ics_sync.httpx, "Client", lambda **k: _FakeHttpxClient(handler, calls))

    headers = auth_headers("parent", parent_id=1)
    r = client.get(
        "/api/events/fetch-ics",
        params={"url": "https://calendar.byga.example.com/feed.ics"},
        headers=headers,
    )
    assert r.status_code == 400, r.text
