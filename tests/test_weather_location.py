"""get_weather supports coordinate lookup (lat/lon) with city-name fallback."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import api.services.weather as weather


class _FakeResp:
    status_code = 200

    def json(self):
        return {
            "main": {"temp": 72.0, "humidity": 55},
            "weather": [{"description": "clear sky"}],
        }


def _capture_url(monkeypatch):
    """Stub requests.get + the API key, returning a dict that records the URL hit."""
    seen = {"url": None}

    def fake_get(url, timeout=None):
        seen["url"] = url
        return _FakeResp()

    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    monkeypatch.setattr(weather.requests, "get", fake_get)
    return seen


def test_fetch_builds_latlon_url_when_coords_given(monkeypatch):
    seen = _capture_url(monkeypatch)
    result = weather._fetch_weather(city="San Ramon", lat=37.78, lon=-121.98)
    assert "lat=37.78" in seen["url"] and "lon=-121.98" in seen["url"]
    assert "q=" not in seen["url"]               # coords win over city
    assert result["temp_f"] == 72.0 and result["error"] is None


def test_fetch_builds_city_url_when_no_coords(monkeypatch):
    seen = _capture_url(monkeypatch)
    weather._fetch_weather(city="Denver")
    assert "q=Denver" in seen["url"]
    assert "lat=" not in seen["url"]


def test_fetch_errors_when_no_location(monkeypatch):
    _capture_url(monkeypatch)
    result = weather._fetch_weather()
    assert result["error"] == "No location provided"
    assert result["temp_f"] is None


def test_get_weather_prefers_coords(monkeypatch):
    weather._weather_cache.clear()
    monkeypatch.setattr(weather, "_now", lambda: 1000.0)
    got = {}

    def fake_fetch(city=None, lat=None, lon=None):
        got["city"], got["lat"], got["lon"] = city, lat, lon
        return {"temp_f": 80.0, "humidity": 40, "description": "sunny", "error": None}

    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch)
    res = weather.get_weather(city="San Ramon", lat=37.78, lon=-121.98)
    assert (got["lat"], got["lon"]) == (37.78, -121.98)
    assert res["temp_f"] == 80.0
    # cached under a coord key, distinct from the city key
    assert any(k.startswith("coord:") for k in weather._weather_cache)


def test_get_weather_city_fallback(monkeypatch):
    weather._weather_cache.clear()
    monkeypatch.setattr(weather, "_now", lambda: 1000.0)
    got = {}

    def fake_fetch(city=None, lat=None, lon=None):
        got["city"], got["lat"], got["lon"] = city, lat, lon
        return {"temp_f": 65.0, "humidity": 60, "description": "cloudy", "error": None}

    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch)
    res = weather.get_weather(city="Denver")
    assert got["city"] == "Denver" and got["lat"] is None and got["lon"] is None
    assert res["temp_f"] == 65.0


def test_get_weather_none_when_both_missing(monkeypatch):
    weather._weather_cache.clear()

    def boom(city=None, lat=None, lon=None):
        raise AssertionError("_fetch_weather must not be called when no location given")

    monkeypatch.setattr(weather, "_fetch_weather", boom)
    res = weather.get_weather()
    assert res["error"] == "No location provided"
    assert res["temp_f"] is None


class _FakeGeoResp:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else []

    def json(self):
        return self._data


def test_reverse_geocode_returns_city_and_state(monkeypatch):
    weather._geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    monkeypatch.setattr(
        weather.requests, "get",
        lambda url, params=None, timeout=None: _FakeGeoResp(200, [{"name": "San Jose", "state": "CA"}]),
    )
    assert weather.reverse_geocode_city(37.33, -121.89) == "San Jose, CA"


def test_reverse_geocode_no_api_key_returns_none(monkeypatch):
    weather._geocode_cache.clear()
    monkeypatch.delenv("OPENWEATHERMAP_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("must not call the API with no key configured")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.reverse_geocode_city(37.33, -121.89) is None


def test_reverse_geocode_empty_response_returns_none(monkeypatch):
    weather._geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    monkeypatch.setattr(weather.requests, "get", lambda url, params=None, timeout=None: _FakeGeoResp(200, []))
    assert weather.reverse_geocode_city(0.0, 0.0) is None


def test_geocode_location_zip_uses_zip_endpoint(monkeypatch):
    weather._forward_geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeGeoResp(200, {"zip": "65006", "name": "Ashland", "lat": 38.7778, "lon": -92.2626, "country": "US"})

    monkeypatch.setattr(weather.requests, "get", fake_get)
    assert weather.geocode_location("65006") == (38.7778, -92.2626)
    assert captured["url"].endswith("/geo/1.0/zip")
    assert captured["params"]["zip"] == "65006,US"


def test_geocode_location_city_uses_direct_endpoint(monkeypatch):
    weather._forward_geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeGeoResp(200, [{"name": "San Jose", "lat": 37.33, "lon": -121.89, "country": "US", "state": "CA"}])

    monkeypatch.setattr(weather.requests, "get", fake_get)
    assert weather.geocode_location("San Jose, CA") == (37.33, -121.89)
    assert captured["url"].endswith("/geo/1.0/direct")
    assert captured["params"]["q"] == "San Jose, CA"


def test_geocode_location_no_api_key_returns_none(monkeypatch):
    weather._forward_geocode_cache.clear()
    monkeypatch.delenv("OPENWEATHERMAP_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("must not call the API with no key configured")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.geocode_location("65006") is None


def test_geocode_location_empty_response_returns_none(monkeypatch):
    weather._forward_geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    monkeypatch.setattr(weather.requests, "get", lambda url, params=None, timeout=None: _FakeGeoResp(200, []))
    assert weather.geocode_location("Nonexistent Place Zzz") is None


def test_geocode_location_blank_text_returns_none(monkeypatch):
    weather._forward_geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")

    def boom(*a, **k):
        raise AssertionError("must not call the API for blank input")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.geocode_location("   ") is None


def test_geocode_location_caches_result(monkeypatch):
    weather._forward_geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeGeoResp(200, {"zip": "65006", "name": "Ashland", "lat": 38.7778, "lon": -92.2626, "country": "US"})

    monkeypatch.setattr(weather.requests, "get", fake_get)
    weather.geocode_location("65006")
    weather.geocode_location("65006")
    assert calls["n"] == 1


def test_compute_heat_flag_thresholds():
    assert weather.compute_heat_flag(70, 40) == (False, "none")
    assert weather.compute_heat_flag(80, 40) == (True, "warm")
    assert weather.compute_heat_flag(86, 40) == (True, "hot")
    assert weather.compute_heat_flag(96, 40) == (True, "very_hot")
    # high humidity bumps the effective temp by 5
    assert weather.compute_heat_flag(75, 80) == (True, "warm")


def test_weather_context_none_on_error():
    assert weather.weather_context({"error": "boom"}) is None
    assert weather.weather_context({"error": None, "temp_f": None}) is None


def test_weather_context_null_humidity_does_not_crash():
    """Real production crash, confirmed live: OpenWeatherMap can return
    humidity as null (key present, value None) rather than omitting it.
    raw.get("humidity", 50) only defaults when the key is ABSENT — a present-
    but-None value used to reach int(None) and raise TypeError, taking down
    the entire coach response for what's meant to be best-effort enrichment.
    Must degrade to the 50% default, never raise."""
    ctx = weather.weather_context({"temp_f": 92.0, "humidity": None, "description": "clear", "error": None})
    assert ctx is not None
    assert ctx["temp_f"] == 92.0
    assert ctx["humidity"] is None          # preserved as-is for display
    assert ctx["heat_flag"] is True          # classified using the 50% default
    assert ctx["heat_level"] == "hot"


def test_weather_context_malformed_temp_returns_none_not_raise():
    """Any other unexpected shape from upstream (non-numeric temp, etc.)
    degrades to no-weather rather than crashing the caller."""
    assert weather.weather_context({"temp_f": "not-a-number", "humidity": 40, "error": None}) is None
    assert weather.weather_context({"temp_f": 92.0, "humidity": "not-a-number", "error": None}) is None


def test_weather_context_extreme_cold_no_heat_flag():
    ctx = weather.weather_context({"temp_f": -10.0, "humidity": 20, "description": "frigid", "error": None})
    assert ctx["heat_flag"] is False
    assert ctx["heat_level"] == "none"


def test_weather_context_shapes_result():
    ctx = weather.weather_context(
        {"temp_f": 92.0, "humidity": 40, "description": "sunny", "error": None},
        location_label="San Jose, CA",
    )
    assert ctx == {
        "temp_f": 92.0, "humidity": 40, "description": "sunny",
        "heat_flag": True, "heat_level": "hot", "location_label": "San Jose, CA",
    }


def test_resolve_weather_prefers_event_location(monkeypatch):
    event = {"city": "Stadium City", "latitude": 10.0, "longitude": 20.0}
    seen = {}
    monkeypatch.setattr(
        weather, "get_weather",
        lambda city=None, lat=None, lon=None: seen.update(city=city, lat=lat, lon=lon) or
        {"temp_f": 70.0, "humidity": 30, "description": "clear", "error": None},
    )

    def boom(*a, **k):
        raise AssertionError("must not geocode when the event already has a location")

    monkeypatch.setattr(weather, "reverse_geocode_city", boom)
    result = weather.resolve_weather(event, latitude=37.33, longitude=-121.89)
    assert seen == {"city": "Stadium City", "lat": 10.0, "lon": 20.0}
    assert result["temp_f"] == 70.0
    assert result["location_label"] is None


def test_resolve_weather_falls_back_to_device_location(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        weather, "get_weather",
        lambda city=None, lat=None, lon=None: seen.update(city=city, lat=lat, lon=lon) or
        {"temp_f": 92.0, "humidity": 40, "description": "sunny", "error": None},
    )
    monkeypatch.setattr(weather, "reverse_geocode_city", lambda lat, lon: "San Jose, CA")

    result = weather.resolve_weather(None, latitude=37.33, longitude=-121.89)
    assert seen == {"city": None, "lat": 37.33, "lon": -121.89}
    assert result["heat_flag"] is True
    assert result["location_label"] == "San Jose, CA"


def test_resolve_weather_none_when_nothing_available():
    assert weather.resolve_weather(None, latitude=None, longitude=None) is None
    assert weather.resolve_weather({"event_type": "rest"}, None, None) is None


def test_resolve_weather_geocode_failure_still_returns_weather(monkeypatch):
    monkeypatch.setattr(
        weather, "get_weather",
        lambda city=None, lat=None, lon=None: {"temp_f": 60.0, "humidity": 50, "description": "cloudy", "error": None},
    )

    def boom(lat, lon):
        raise RuntimeError("geocode down")

    monkeypatch.setattr(weather, "reverse_geocode_city", boom)
    result = weather.resolve_weather(None, latitude=1.0, longitude=2.0)
    assert result["temp_f"] == 60.0
    assert result["location_label"] is None


def test_resolve_weather_survives_get_weather_raising(monkeypatch):
    """resolve_weather is best-effort enrichment for the coach prompt — an
    unexpected exception anywhere in the chain (not just the known
    null-humidity shape) must degrade to no weather, never propagate up
    into answer_with_knowledge / assemble_context and break the response."""
    def boom(city=None, lat=None, lon=None):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(weather, "get_weather", boom)
    assert weather.resolve_weather(None, latitude=1.0, longitude=2.0) is None
    assert weather.resolve_weather({"city": "Somewhere"}, None, None) is None


def test_resolve_weather_event_with_null_humidity_does_not_crash(monkeypatch):
    """End-to-end through the event-location branch specifically, since that
    path is unreachable from the device-fallback tests above."""
    monkeypatch.setattr(
        weather, "get_weather",
        lambda city=None, lat=None, lon=None: {"temp_f": 88.0, "humidity": None, "description": "hazy", "error": None},
    )
    result = weather.resolve_weather({"city": "Stadium City"}, None, None)
    assert result is not None
    assert result["heat_flag"] is True


def test_reverse_geocode_place_without_state_returns_name_only(monkeypatch):
    """International locations (or some US territories) often have no
    'state' field — must not crash on the `if name and state` check, and
    must still return a usable label rather than None."""
    weather._geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    monkeypatch.setattr(
        weather.requests, "get",
        lambda url, params=None, timeout=None: _FakeGeoResp(200, [{"name": "Tokyo", "state": None}]),
    )
    assert weather.reverse_geocode_city(35.68, 139.69) == "Tokyo"


def test_reverse_geocode_network_exception_returns_none(monkeypatch):
    weather._geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")

    def boom(url, params=None, timeout=None):
        raise ConnectionError("network down")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert weather.reverse_geocode_city(37.33, -121.89) is None


def test_get_weather_error_result_not_cached_past_its_short_ttl(monkeypatch):
    """Error results use a much shorter TTL (60s vs 30min) so a transient
    outage self-heals quickly instead of poisoning the cache for half an hour."""
    weather._weather_cache.clear()
    clock = {"t": 1000.0}
    monkeypatch.setattr(weather, "_now", lambda: clock["t"])
    calls = {"n": 0}

    def fake_fetch(city=None, lat=None, lon=None):
        calls["n"] += 1
        return {"temp_f": None, "humidity": None, "description": "unknown", "error": "API down"}

    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch)
    weather.get_weather(city="Denver")
    assert calls["n"] == 1

    clock["t"] += 30  # still within the 60s error TTL
    weather.get_weather(city="Denver")
    assert calls["n"] == 1, "must serve the cached error, not refetch yet"

    clock["t"] += 40  # now 70s elapsed — past the 60s error TTL
    weather.get_weather(city="Denver")
    assert calls["n"] == 2, "must refetch once the short error TTL expires"


def test_get_weather_success_result_cached_for_full_ttl(monkeypatch):
    weather._weather_cache.clear()
    clock = {"t": 1000.0}
    monkeypatch.setattr(weather, "_now", lambda: clock["t"])
    calls = {"n": 0}

    def fake_fetch(city=None, lat=None, lon=None):
        calls["n"] += 1
        return {"temp_f": 75.0, "humidity": 50, "description": "clear", "error": None}

    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch)
    weather.get_weather(city="Denver")

    clock["t"] += 1700  # under 30min
    weather.get_weather(city="Denver")
    assert calls["n"] == 1, "must still be cached under the 30min success TTL"

    clock["t"] += 200  # now past 1800s total
    weather.get_weather(city="Denver")
    assert calls["n"] == 2


def test_get_weather_nearby_coords_share_cache_key():
    """Documents the intentional rounding behavior: coordinates are rounded
    to 3 decimals (~111m) for the cache key, so two GPS reads a few meters
    apart during the same request burst hit one cached entry rather than
    firing duplicate API calls."""
    weather._weather_cache.clear()
    from unittest.mock import patch
    with patch.object(weather, "_fetch_weather", return_value={
        "temp_f": 70.0, "humidity": 40, "description": "clear", "error": None,
    }) as mock_fetch:
        weather.get_weather(lat=37.33001, lon=-121.89001)
        weather.get_weather(lat=37.33002, lon=-121.89002)
    assert mock_fetch.call_count == 1


def test_reverse_geocode_is_cached(monkeypatch):
    weather._geocode_cache.clear()
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test-key")
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeGeoResp(200, [{"name": "San Jose", "state": "CA"}])

    monkeypatch.setattr(weather.requests, "get", fake_get)
    weather.reverse_geocode_city(37.33, -121.89)
    weather.reverse_geocode_city(37.33, -121.89)
    assert calls["n"] == 1
