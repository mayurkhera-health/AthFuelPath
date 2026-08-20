"""derive_sweat_profile + calc_sweat_output (api/services/weather.py) and the
/api/nutrition/sweat route — the other production consumer of weather data
alongside the coach chat, previously with zero test coverage."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import weather
from api.main import app
from tests.conftest import auth_headers


# ── derive_sweat_profile ─────────────────────────────────────────────────────
def test_derive_sweat_profile_age_bands():
    assert weather.derive_sweat_profile({"age": 10, "gender": "girl", "competition_level": "recreational"}) == "light"
    assert weather.derive_sweat_profile({"age": 12, "gender": "girl", "competition_level": "recreational"}) == "moderate"
    assert weather.derive_sweat_profile({"age": 14, "gender": "girl", "competition_level": "recreational"}) == "heavy"
    assert weather.derive_sweat_profile({"age": 17, "gender": "girl", "competition_level": "recreational"}) == "heavy"


def test_derive_sweat_profile_post_puberty_boy_bump():
    # 16-17 boys skew higher regardless of the base age-band profile.
    assert weather.derive_sweat_profile({"age": 16, "gender": "boy", "competition_level": "recreational"}) == "very heavy"
    assert weather.derive_sweat_profile({"age": 16, "gender": "girl", "competition_level": "recreational"}) == "heavy"


def test_derive_sweat_profile_elite_bump():
    light_base = weather.derive_sweat_profile({"age": 10, "gender": "girl", "competition_level": "recreational"})
    light_elite = weather.derive_sweat_profile({"age": 10, "gender": "girl", "competition_level": "elite_club"})
    assert light_base == "light"
    assert light_elite == "moderate"  # bumped one tier


def test_derive_sweat_profile_missing_fields_defaults_safely():
    """No age/gender/level at all — must not raise, falls back to sane defaults."""
    profile = weather.derive_sweat_profile({})
    assert profile in ("light", "moderate", "heavy", "very heavy")


# ── calc_sweat_output ────────────────────────────────────────────────────────
def _athlete(weight_lbs=110, age=14, gender="girl", level="competitive_club"):
    return {"weight_lbs": weight_lbs, "age": age, "gender": gender, "competition_level": level}


def _event(event_type="game", duration_hours=1.5):
    return {"event_type": event_type, "duration_hours": duration_hours}


def test_calc_sweat_output_hot_humid_triggers_electrolytes():
    weather_data = {"temp_f": 92.0, "humidity": 75}
    result = weather.calc_sweat_output(_athlete(), _event(), weather_data)
    assert result["electrolytes_needed"] is True
    assert "Temperature" in result["electrolyte_reason"]
    assert result["sweat_loss_liters"] > 0
    assert result["hydration_oz_during"] > 0


def test_calc_sweat_output_mild_weather_no_electrolytes_from_temp():
    weather_data = {"temp_f": 65.0, "humidity": 40}
    # short, low-intensity event so no OTHER trigger (duration/tournament/strength) fires either
    result = weather.calc_sweat_output(_athlete(), _event(event_type="practice", duration_hours=0.5), weather_data)
    assert result["electrolytes_needed"] is False
    assert "Plain water" in result["recommendations"][0]


def test_calc_sweat_output_null_temp_and_humidity_does_not_crash():
    """weather.get_weather() can return temp_f/humidity as None (no API key,
    upstream error, or a genuinely null field) — calc_sweat_output must
    degrade gracefully (no temp/humidity-driven multiplier or electrolyte
    trigger), not raise."""
    weather_data = {"temp_f": None, "humidity": None}
    result = weather.calc_sweat_output(_athlete(), _event(), weather_data)
    assert result["weather_temp_f"] is None
    assert result["weather_humidity"] is None
    # still produces a baseline sweat estimate from profile + event type alone
    assert result["sweat_loss_liters"] > 0


def test_calc_sweat_output_missing_weather_keys_does_not_crash():
    """An empty dict (weather.get_weather() shape omitted entirely) — .get()
    on missing keys, same safe path as explicit None."""
    result = weather.calc_sweat_output(_athlete(), _event(), {})
    assert result["weather_temp_f"] is None
    assert result["electrolytes_needed"] in (True, False)  # duration-only trigger may still fire


def test_calc_sweat_output_tournament_always_needs_electrolytes():
    weather_data = {"temp_f": 60.0, "humidity": 30}
    result = weather.calc_sweat_output(_athlete(), _event(event_type="tournament", duration_hours=0.5), weather_data)
    assert result["electrolytes_needed"] is True
    assert "Tournament day" in result["electrolyte_reason"]


def test_calc_sweat_output_dye_warning_present_when_electrolytes_needed():
    weather_data = {"temp_f": 90.0, "humidity": 50}
    result = weather.calc_sweat_output(_athlete(), _event(), weather_data)
    assert any("artificial dyes" in r for r in result["recommendations"])


# ── /api/nutrition/sweat route ───────────────────────────────────────────────
@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    weather._weather_cache.clear()
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete_and_event(client, *, city=None, latitude=None, longitude=None, event_type="game"):
    _counter["n"] += 1
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"sweat-test-{_counter['n']}@example.com", "consent_confirmed": True,
    })
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "Alex", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6, "competition_level": "competitive_club",
    }, headers=auth_headers("parent", parent_id=parent_id))
    assert a.status_code == 201, a.text
    athlete_id = a.json()["id"]
    ev = client.post("/api/events/", json={
        "athlete_id": athlete_id, "event_name": "Big Game", "event_type": event_type,
        "event_date": "2026-08-01", "duration_hours": 1.5,
        "city": city, "latitude": latitude, "longitude": longitude,
    }, headers=auth_headers("athlete", athlete_id=athlete_id))
    assert ev.status_code == 201, ev.text
    return athlete_id, ev.json()["id"]


def test_sweat_route_uses_event_venue_coords(client, monkeypatch):
    athlete_id, event_id = _make_athlete_and_event(client, latitude=10.0, longitude=20.0, city="Stadium City")
    seen = {}

    def fake_fetch(city=None, lat=None, lon=None):
        seen.update(city=city, lat=lat, lon=lon)
        return {"temp_f": 88.0, "humidity": 60, "description": "sunny", "error": None}

    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch)
    r = client.post("/api/nutrition/sweat", json={"athlete_id": athlete_id, "event_id": event_id},
                     headers=auth_headers("athlete", athlete_id=athlete_id))
    assert r.status_code == 200, r.text
    assert seen["lat"] == 10.0 and seen["lon"] == 20.0
    assert r.json()["weather_temp_f"] == 88.0


def test_sweat_route_survives_null_humidity_from_weather_api(client, monkeypatch):
    """End-to-end proof through the real HTTP route: a null-humidity weather
    response must not 500 the sweat-output endpoint."""
    athlete_id, event_id = _make_athlete_and_event(client, latitude=10.0, longitude=20.0)
    monkeypatch.setattr(
        weather, "_fetch_weather",
        lambda city=None, lat=None, lon=None: {"temp_f": 90.0, "humidity": None, "description": "hazy", "error": None},
    )
    r = client.post("/api/nutrition/sweat", json={"athlete_id": athlete_id, "event_id": event_id},
                     headers=auth_headers("athlete", athlete_id=athlete_id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weather_temp_f"] == 90.0
    assert body["weather_humidity"] is None


def test_sweat_route_survives_weather_api_error(client, monkeypatch):
    """No API key / upstream failure -> get_weather returns an error dict,
    not an exception. The route must still return a usable sweat estimate."""
    athlete_id, event_id = _make_athlete_and_event(client, latitude=10.0, longitude=20.0)
    monkeypatch.setattr(
        weather, "_fetch_weather",
        lambda city=None, lat=None, lon=None: {"temp_f": None, "humidity": None, "description": "unknown", "error": "API down"},
    )
    r = client.post("/api/nutrition/sweat", json={"athlete_id": athlete_id, "event_id": event_id},
                     headers=auth_headers("athlete", athlete_id=athlete_id))
    assert r.status_code == 200, r.text
    assert r.json()["weather_temp_f"] is None


def test_sweat_route_requires_a_session(client):
    r = client.post("/api/nutrition/sweat", json={"athlete_id": 1, "event_id": 1})
    assert r.status_code == 401


def test_sweat_route_404_for_missing_athlete(client):
    r = client.post("/api/nutrition/sweat", json={"athlete_id": 999999, "event_id": 1},
                     headers=auth_headers("athlete", athlete_id=999999))
    assert r.status_code == 404


def test_sweat_route_404_for_missing_event(client):
    p = client.post("/api/parents/", json={"full_name": "P", "email": "sweat-404@example.com", "consent_confirmed": True})
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "Alex", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    }, headers=auth_headers("parent", parent_id=parent_id))
    athlete_id = a.json()["id"]
    r = client.post("/api/nutrition/sweat", json={"athlete_id": athlete_id, "event_id": 999999},
                     headers=auth_headers("athlete", athlete_id=athlete_id))
    assert r.status_code == 404


def test_sweat_route_rejects_unrelated_athlete_token(client):
    victim_athlete_id, event_id = _make_athlete_and_event(client, latitude=10.0, longitude=20.0)
    attacker_athlete_id, _ = _make_athlete_and_event(client)
    r = client.post(
        "/api/nutrition/sweat", json={"athlete_id": victim_athlete_id, "event_id": event_id},
        headers=auth_headers("athlete", athlete_id=attacker_athlete_id),
    )
    assert r.status_code == 403


def test_sweat_route_rejects_a_real_event_belonging_to_another_athlete(client):
    """The core BOLA fix: a caller who owns athlete A but passes athlete A's own
    athlete_id alongside athlete B's real event_id must not get B's event data."""
    victim_athlete_id, victim_event_id = _make_athlete_and_event(client, latitude=10.0, longitude=20.0)
    attacker_athlete_id, _ = _make_athlete_and_event(client)
    r = client.post(
        "/api/nutrition/sweat", json={"athlete_id": attacker_athlete_id, "event_id": victim_event_id},
        headers=auth_headers("athlete", athlete_id=attacker_athlete_id),
    )
    assert r.status_code == 404, (
        f"Expected the mismatched event to be rejected, got {r.status_code}: {r.text}"
    )
