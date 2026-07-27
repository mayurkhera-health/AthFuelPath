"""
SSRF regression — api/services/ics_sync.py::fetch_ics_text.

POST /{athlete_id}/calendar/sync-url (api/routes/calendar.py) takes a user-
submitted ICS URL and has the server fetch it via fetch_ics_text() before ever
storing it. The only prior validation was that the string started with
webcal(s):// or https:// — nothing stopped a URL that resolves to a private,
loopback, link-local, or cloud-metadata address, letting an authenticated user
turn the server into a request proxy against internal infrastructure.
Fixed via _is_public_host() (checked before every fetch AND every redirect
hop, since a URL can start out public and 302 to an internal address).
"""
import pytest

from api.services import ics_sync


class _FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# ─── _is_public_host ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("host", [
    "127.0.0.1",        # loopback
    "169.254.169.254",  # cloud metadata endpoint
    "10.0.0.5",          # RFC 1918
    "192.168.1.1",       # RFC 1918
    "172.16.0.1",        # RFC 1918
    "::1",                # loopback v6
])
def test_is_public_host_rejects_private_and_internal_ips(host):
    assert ics_sync._is_public_host(host) is False


def test_is_public_host_accepts_a_known_public_ip():
    assert ics_sync._is_public_host("8.8.8.8") is True


# ─── fetch_ics_text guard ──────────────────────────────────────────────────────

def test_fetch_rejects_a_loopback_url_without_making_any_request(monkeypatch):
    calls = []
    monkeypatch.setattr(ics_sync.httpx, "get", lambda *a, **k: calls.append(1) or _FakeResponse())

    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://127.0.0.1/feed.ics")
    assert calls == [], "Guard must reject before any network call is made"


def test_fetch_rejects_a_cloud_metadata_url(monkeypatch):
    monkeypatch.setattr(ics_sync.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("should never fetch a metadata URL")))

    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://169.254.169.254/latest/meta-data/")


def test_fetch_allows_a_public_host_through(monkeypatch):
    monkeypatch.setattr(ics_sync, "_is_public_host", lambda host: True)
    monkeypatch.setattr(ics_sync.httpx, "get",
                         lambda *a, **k: _FakeResponse(200, text="BEGIN:VCALENDAR"))

    assert ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics") == "BEGIN:VCALENDAR"


def test_fetch_follows_a_redirect_to_another_public_host(monkeypatch):
    monkeypatch.setattr(ics_sync, "_is_public_host", lambda host: True)
    responses = [
        _FakeResponse(302, headers={"location": "https://cdn.example.com/feed.ics"}),
        _FakeResponse(200, text="BEGIN:VCALENDAR"),
    ]
    monkeypatch.setattr(ics_sync.httpx, "get", lambda *a, **k: responses.pop(0))

    assert ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics") == "BEGIN:VCALENDAR"


def test_fetch_rejects_a_redirect_that_points_at_an_internal_host(monkeypatch):
    """The initial URL resolves fine, but its 302 points at a private address —
    the internal hop must be checked, not just the original URL."""
    def fake_is_public(host):
        return host != "internal-service.local"
    monkeypatch.setattr(ics_sync, "_is_public_host", fake_is_public)

    call_count = {"n": 0}
    def fake_get(url, **kwargs):
        call_count["n"] += 1
        return _FakeResponse(302, headers={"location": "https://internal-service.local/secrets"})
    monkeypatch.setattr(ics_sync.httpx, "get", fake_get)

    with pytest.raises(ValueError, match="not allowed"):
        ics_sync.fetch_ics_text("https://calendar.byga.example.com/feed.ics")
    assert call_count["n"] == 1, "Must not follow the redirect to the internal host"
