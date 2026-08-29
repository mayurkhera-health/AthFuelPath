"""OpenWeatherMap transport hardening — api/services/weather.py (Security
Item 4, S2). All four request-building call sites used plain http:// rather
than https://, sending OPENWEATHERMAP_API_KEY (a query-param key, per
vendor's own API contract) over an unencrypted connection. Fixed by
switching every call site to https:// — no query params, caching, timeout,
or response-parsing behavior changes.
"""
import pytest

from api.services import weather


@pytest.fixture(autouse=True)
def _weather_key(monkeypatch):
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    # conftest.py's autouse cache-clear fixture doesn't clear this one
    # (module-level dict persists across the whole test session) — clear it
    # here so a cache hit from another test file can't skip requests.get and
    # make this test's assertion never run.
    weather._forward_geocode_cache.clear()


class _FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {"main": {"temp": 75, "humidity": 40}, "weather": [{"description": "clear"}]}

    def json(self):
        return self._body


def test_fetch_weather_by_coords_uses_https(monkeypatch):
    seen = {}

    def fake_get(url, timeout=None):
        seen["url"] = url
        return _FakeResponse()
    monkeypatch.setattr(weather.requests, "get", fake_get)

    weather._fetch_weather(lat=37.33, lon=-121.89)
    assert seen["url"].startswith("https://api.openweathermap.org/"), seen["url"]


def test_fetch_weather_by_city_uses_https(monkeypatch):
    seen = {}

    def fake_get(url, timeout=None):
        seen["url"] = url
        return _FakeResponse()
    monkeypatch.setattr(weather.requests, "get", fake_get)

    weather._fetch_weather(city="San Jose")
    assert seen["url"].startswith("https://api.openweathermap.org/"), seen["url"]


def test_reverse_geocode_uses_https(monkeypatch):
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen["url"] = url
        return _FakeResponse(body=[{"name": "San Jose"}])
    monkeypatch.setattr(weather.requests, "get", fake_get)

    weather.reverse_geocode_city(37.33, -121.89)
    assert seen["url"].startswith("https://api.openweathermap.org/"), seen["url"]


@pytest.mark.parametrize("is_zip", [True, False])
def test_geocode_location_uses_https(monkeypatch, is_zip):
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen["url"] = url
        return _FakeResponse(body=[{"lat": 37.33, "lon": -121.89, "name": "San Jose"}])
    monkeypatch.setattr(weather.requests, "get", fake_get)

    weather.geocode_location("95112" if is_zip else "San Jose, CA")
    assert seen["url"].startswith("https://api.openweathermap.org/"), seen["url"]
