"""
SSRF regression — api/services/ics_sync.py::fetch_ics_text.

POST /{athlete_id}/calendar/sync-url (api/routes/calendar.py) takes a user-
submitted ICS URL and has the server fetch it via fetch_ics_text() before ever
storing it. The only prior validation was that the string started with
webcal(s):// or https:// — nothing stopped a URL that resolves to a private,
loopback, link-local, or cloud-metadata address, letting an authenticated user
turn the server into a request proxy against internal infrastructure.
Fixed via _resolve_validated_ips()/_is_public_host() (checked before every
fetch AND every redirect hop, since a URL can start out public and 302 to an
internal address).

Security Item 3 hardening pass adds: IP pinning (the validated IP is what the
HTTP client actually connects to — see test_ics_sync_dns_rebinding.py for the
DNS-rebinding TOCTOU this closes), the 100.64.0.0/10 CGNAT range, per-redirect-
hop scheme re-validation, and a response-size cap. fetch_ics_text now issues
requests via httpx.Client(...).stream(...) instead of the module-level
httpx.get() — the fakes below model that interface.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import pytest

from api.services import ics_sync


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
        if not self._body:
            return


class _FakeClient:
    """Stands in for httpx.Client — .stream() calls are handed to `handler`,
    which receives (method, url, headers, extensions) and returns a
    _FakeResponse. Records every call in `.calls` for assertions."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, method, url, headers=None, extensions=None, follow_redirects=False):
        self.calls.append({"method": method, "url": url, "headers": headers, "extensions": extensions})
        return _FakeStreamCtx(self.handler(method, url, headers, extensions))


def _patch_client(monkeypatch, handler):
    client = _FakeClient(handler)
    monkeypatch.setattr(ics_sync.httpx, "Client", lambda **k: client)
    return client


# ─── _is_public_host / _resolve_validated_ips ──────────────────────────────

@pytest.mark.parametrize("host", [
    "127.0.0.1",        # loopback
    "169.254.169.254",  # cloud metadata endpoint
    "10.0.0.5",          # RFC 1918
    "192.168.1.1",       # RFC 1918
    "172.16.0.1",        # RFC 1918
    "::1",                # loopback v6
    "100.64.0.1",         # CGNAT / RFC 6598 shared address space
])
def test_is_public_host_rejects_private_and_internal_ips(host):
    assert ics_sync._is_public_host(host) is False


def test_is_public_host_accepts_a_known_public_ip():
    assert ics_sync._is_public_host("8.8.8.8") is True


def test_resolve_validated_ips_rejects_mixed_public_and_private_dns_answers(monkeypatch):
    """A hostname whose DNS answer contains BOTH a public and a private IP
    must be rejected outright, not filtered down to just the public one —
    resolving that same hostname again later (e.g. at a redirect hop, or if
    round-robin DNS serves a different answer) could hand back only the
    private address."""
    def fake_getaddrinfo(host, *a, **k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
        ]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)
    assert ics_sync._is_public_host("mixed.example") is False
    with pytest.raises(ValueError, match="not allowed"):
        ics_sync._resolve_validated_ips("mixed.example")


def test_resolve_validated_ips_rejects_metadata_google_internal_hostname(monkeypatch):
    """Exercises the DNS-resolution branch (not just the literal-IP branch) —
    a hostname that RESOLVES to the link-local metadata address must be
    blocked exactly like the literal IP is."""
    def fake_getaddrinfo(host, *a, **k):
        assert host == "metadata.google.internal"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)
    assert ics_sync._is_public_host("metadata.google.internal") is False


# ─── fetch_ics_text guard — rejection before any network call ──────────────

def test_fetch_rejects_a_loopback_url_without_making_any_request(monkeypatch):
    monkeypatch.setattr(ics_sync.httpx, "Client",
                         lambda **k: (_ for _ in ()).throw(AssertionError("must not open a client")))
    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://127.0.0.1/feed.ics")


def test_fetch_rejects_a_cloud_metadata_url(monkeypatch):
    monkeypatch.setattr(ics_sync.httpx, "Client",
                         lambda **k: (_ for _ in ()).throw(AssertionError("should never fetch a metadata URL")))
    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://169.254.169.254/latest/meta-data/")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://public-host.example/feed.ics",
    "gopher://public-host.example/feed.ics",
    "data:text/plain;base64,QkVHSU46VkNBTEVOREFS",
])
def test_fetch_rejects_non_http_schemes_without_making_any_request(monkeypatch, url):
    monkeypatch.setattr(ics_sync.httpx, "Client",
                         lambda **k: (_ for _ in ()).throw(AssertionError("must not fetch a non-http(s) scheme")))
    with pytest.raises(ValueError):
        ics_sync.fetch_ics_text(url)


# ─── fetch_ics_text — happy path + pinning ──────────────────────────────────

def test_fetch_allows_a_public_host_through_and_pins_the_connection_to_its_ip(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    def handler(method, url, headers, extensions):
        return _FakeResponse(200, body=b"BEGIN:VCALENDAR")
    client = _patch_client(monkeypatch, handler)

    result = ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics")
    assert result == "BEGIN:VCALENDAR"

    call = client.calls[0]
    assert urlparse(call["url"]).hostname == "93.184.216.34", "must connect to the pinned IP, not the hostname"
    assert call["headers"]["Host"] == "calendar.byga.example.com"
    assert call["extensions"] == {"sni_hostname": "calendar.byga.example.com"}


def test_fetch_never_disables_certificate_verification(monkeypatch):
    """Static guarantee: nothing in the fetch path ever passes verify=False —
    certificate verification stays at httpx's default (True) for every call."""
    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    seen_client_kwargs = []

    def fake_client_ctor(**kwargs):
        seen_client_kwargs.append(kwargs)
        return _FakeClient(lambda m, u, h, e: _FakeResponse(200, body=b"BEGIN:VCALENDAR"))
    monkeypatch.setattr(ics_sync.httpx, "Client", fake_client_ctor)

    ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics")

    for kwargs in seen_client_kwargs:
        assert kwargs.get("verify", True) is True, "verify must never be overridden to False"


def test_fetch_allows_a_literal_public_ip_url(monkeypatch):
    def handler(method, url, headers, extensions):
        assert urlparse(url).hostname == "8.8.8.8"
        return _FakeResponse(200, body=b"BEGIN:VCALENDAR")
    _patch_client(monkeypatch, handler)
    assert ics_sync.fetch_ics_text("https://8.8.8.8/feed.ics") == "BEGIN:VCALENDAR"


# ─── Redirects ──────────────────────────────────────────────────────────────

def test_fetch_follows_a_redirect_to_another_public_host(monkeypatch):
    ip_by_host = {"calendar.byga.example.com": "93.184.216.34", "cdn.example.com": "8.8.4.4"}

    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip_by_host[host], 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    responses = [
        _FakeResponse(302, headers={"location": "https://cdn.example.com/feed.ics"}),
        _FakeResponse(200, body=b"BEGIN:VCALENDAR"),
    ]

    def handler(method, url, headers, extensions):
        return responses.pop(0)
    client = _patch_client(monkeypatch, handler)

    assert ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics") == "BEGIN:VCALENDAR"
    assert len(client.calls) == 2
    assert urlparse(client.calls[1]["url"]).hostname == "8.8.4.4"
    assert client.calls[1]["headers"]["Host"] == "cdn.example.com"


def test_fetch_rejects_a_redirect_that_points_at_an_internal_host(monkeypatch):
    """The initial URL resolves fine, but its 302 points at a private address —
    the internal hop must be checked, not just the original URL."""
    def fake_getaddrinfo(host, *a, **k):
        if host == "internal-service.local":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    def handler(method, url, headers, extensions):
        return _FakeResponse(302, headers={"location": "https://internal-service.local/secrets"})
    client = _patch_client(monkeypatch, handler)

    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics")
    assert len(client.calls) == 1, "Must not follow the redirect to the internal host"


def test_fetch_rejects_a_redirect_that_points_at_the_metadata_endpoint(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        if host == "metadata.google.internal":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    def handler(method, url, headers, extensions):
        return _FakeResponse(302, headers={"location": "http://metadata.google.internal/computeMetadata/v1/"})
    client = _patch_client(monkeypatch, handler)

    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics")
    assert len(client.calls) == 1


def test_fetch_rejects_a_redirect_to_a_non_http_scheme(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    def handler(method, url, headers, extensions):
        return _FakeResponse(302, headers={"location": "file:///etc/passwd"})
    client = _patch_client(monkeypatch, handler)

    with pytest.raises(ValueError):
        ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics")
    assert len(client.calls) == 1, "Must not follow a redirect to a non-http(s) scheme"


# ─── Response-size cap (F4) ─────────────────────────────────────────────────

def test_fetch_allows_a_feed_under_the_size_cap(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)
    body = b"BEGIN:VCALENDAR" + b"x" * 100
    _patch_client(monkeypatch, lambda m, u, h, e: _FakeResponse(200, body=body))
    assert ics_sync.fetch_ics_text("https://calendar.example.com/feed.ics") == body.decode()


def test_fetch_allows_a_feed_exactly_at_the_size_cap(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)
    body = b"x" * ics_sync._MAX_ICS_BYTES
    _patch_client(monkeypatch, lambda m, u, h, e: _FakeResponse(200, body=body))
    assert len(ics_sync.fetch_ics_text("https://calendar.example.com/feed.ics")) == ics_sync._MAX_ICS_BYTES


def test_fetch_rejects_a_feed_over_the_size_cap(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)
    body = b"x" * (ics_sync._MAX_ICS_BYTES + 1)
    _patch_client(monkeypatch, lambda m, u, h, e: _FakeResponse(200, body=body))
    with pytest.raises(ValueError, match="exceeds"):
        ics_sync.fetch_ics_text("https://calendar.example.com/feed.ics")
