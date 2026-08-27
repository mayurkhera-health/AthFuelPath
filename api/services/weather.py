import logging
import os
import re
import time

import requests

from api.services.nutrition_calc import calc_age
from api.services.competition_level import classify_competition_level

logger = logging.getLogger(__name__)


def derive_sweat_profile(athlete: dict) -> str:
    """Auto-derive sweat profile from age, gender, and competition level."""
    age = int(calc_age(
        dob_str=athlete.get("date_of_birth"),
        age_fallback=athlete.get("age") or 13,
    ))
    gender = (athlete.get("gender") or "").lower()
    # Same classifier derive_intensity() uses (api/services/competition_level.py)
    # — hydration and event-intensity guidance now agree on what a given
    # stored competition_level value means, instead of each keeping its own
    # independent keyword match.
    tier = classify_competition_level(athlete.get("competition_level") or athlete.get("level"))

    # Base profile by age (children sweat less efficiently; puberty increases output)
    if age <= 11:
        profile = "light"
    elif age <= 13:
        profile = "moderate"
    elif age <= 15:
        profile = "heavy"
    else:
        profile = "heavy"

    # Post-puberty males (16-17) skew higher
    if age >= 16 and "boy" in gender:
        profile = "very heavy"

    # Elite/competitive athletes have higher sweat rates due to training adaptation.
    if tier in ("elite_club", "competitive_club"):
        bump = {"light": "moderate", "moderate": "heavy", "heavy": "very heavy", "very heavy": "very heavy"}
        profile = bump.get(profile, profile)

    return profile


_WEATHER_TTL_SECONDS = 1800       # 30 minutes for successful results
_WEATHER_ERROR_TTL_SECONDS = 60   # 1 minute for error results (self-heals quickly)
_weather_cache: dict[str, tuple[float, dict]] = {}  # key -> (fetched_at, result)


def _now() -> float:
    return time.monotonic()


def _fetch_weather(city: str | None = None, lat: float | None = None, lon: float | None = None) -> dict:
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return {"temp_f": None, "humidity": None, "description": "unknown", "error": "No API key configured"}
    # Prefer precise coordinates (venue lat/lon) over a coarse city-name query.
    if lat is not None and lon is not None:
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
    elif city:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=imperial"
    else:
        return {"temp_f": None, "humidity": None, "description": "unknown", "error": "No location provided"}
    try:
        resp = requests.get(url, timeout=3)
        data = resp.json()
        if resp.status_code != 200:
            return {"temp_f": None, "humidity": None, "description": "unknown", "error": data.get("message", "API error")}
        return {
            "temp_f": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "description": data["weather"][0]["description"],
            "error": None,
        }
    except Exception as e:
        return {"temp_f": None, "humidity": None, "description": "unknown", "error": str(e)}


def get_weather(city: str | None = None, lat: float | None = None, lon: float | None = None) -> dict:
    """Cached weather lookup. Prefers precise coordinates (lat/lon) when BOTH are
    provided; otherwise falls back to a city-name query. Returns an error result if
    neither is given. Successful results are cached for _WEATHER_TTL_SECONDS; error
    results are cached too but for the much shorter _WEATHER_ERROR_TTL_SECONDS, so a
    transient failure self-heals quickly instead of hammering the upstream API.
    In-memory, per-process — correct for the single-VM deployment."""
    use_coords = lat is not None and lon is not None
    key = (
        f"coord:{round(float(lat), 3)},{round(float(lon), 3)}"
        if use_coords
        else (city or "").strip().lower()
    )
    if not key:
        return {"temp_f": None, "humidity": None, "description": "unknown", "error": "No location provided"}
    cached = _weather_cache.get(key)
    if cached:
        ttl = _WEATHER_ERROR_TTL_SECONDS if cached[1].get("error") else _WEATHER_TTL_SECONDS
        if (_now() - cached[0]) < ttl:
            return cached[1]
    result = _fetch_weather(city=city, lat=lat, lon=lon)
    _weather_cache[key] = (_now(), result)  # cache both successes and errors
    return result


def compute_heat_flag(temp_f: float, humidity: int) -> tuple[bool, str]:
    effective = temp_f + (5 if humidity > 70 else 0)
    if effective >= 95:
        return True, "very_hot"
    if effective >= 85:
        return True, "hot"
    if effective >= 78:
        return True, "warm"
    return False, "none"


def weather_context(raw: dict, location_label: str | None = None) -> dict | None:
    """Shape a raw get_weather() result into the coach-prompt-ready form —
    heat-flag classified, with an optional resolved location name for copy.
    Never raises: malformed upstream data (e.g. the API returning a null
    humidity field — a real, observed shape, not a hypothetical) just means
    no weather enrichment for this call, not a broken coach response."""
    if raw.get("error") or raw.get("temp_f") is None:
        return None
    try:
        humidity_raw = raw.get("humidity")
        humidity = int(humidity_raw) if humidity_raw is not None else 50
        heat_flag, heat_level = compute_heat_flag(float(raw["temp_f"]), humidity)
    except (TypeError, ValueError):
        logger.warning("weather_context: unusable raw weather shape %r", raw)
        return None
    return {
        "temp_f": raw["temp_f"],
        "humidity": raw.get("humidity"),
        "description": raw.get("description", ""),
        "heat_flag": heat_flag,
        "heat_level": heat_level,
        "location_label": location_label,
    }


def resolve_weather(
    event: dict | None, latitude: float | None = None, longitude: float | None = None
) -> dict | None:
    """Weather for a coach prompt: an event's own venue location always wins
    (game/practice-site weather matters more than wherever the athlete's
    phone happens to be) — falls back to device coordinates only when there's
    no event, or the event has no stored location. None if neither resolves,
    or on any unexpected failure — this is best-effort enrichment for the
    coach prompt and must never be the reason a real chat request breaks."""
    try:
        has_coords = event and event.get("latitude") is not None and event.get("longitude") is not None
        if event and (has_coords or event.get("city")):
            raw = get_weather(city=event.get("city"), lat=event.get("latitude"), lon=event.get("longitude"))
            return weather_context(raw)
        if latitude is not None and longitude is not None:
            location_label = None
            try:
                location_label = reverse_geocode_city(latitude, longitude)
            except Exception:
                pass
            raw = get_weather(lat=latitude, lon=longitude)
            return weather_context(raw, location_label=location_label)
        return None
    except Exception:
        logger.exception("resolve_weather failed unexpectedly")
        return None


_GEOCODE_TTL_SECONDS = 86400  # a coordinate's city doesn't change — cache a full day
_geocode_cache: dict[str, tuple[float, str | None]] = {}


def reverse_geocode_city(lat: float, lon: float) -> str | None:
    """Coordinates -> a human-readable city string ("San Jose, CA"), for
    location-flavored search queries. Reuses OPENWEATHERMAP_API_KEY (already
    configured) via their free geocoding endpoint — no new vendor. Returns
    None on any failure; callers should degrade gracefully, not block on it."""
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return None

    key = f"{round(float(lat), 2)},{round(float(lon), 2)}"
    cached = _geocode_cache.get(key)
    if cached and (_now() - cached[0]) < _GEOCODE_TTL_SECONDS:
        return cached[1]

    try:
        resp = requests.get(
            "http://api.openweathermap.org/geo/1.0/reverse",
            params={"lat": lat, "lon": lon, "limit": 1, "appid": api_key},
            timeout=3,
        )
        data = resp.json()
        if resp.status_code != 200 or not data:
            _geocode_cache[key] = (_now(), None)
            return None
        place = data[0]
        name = place.get("name")
        state = place.get("state")
        city = f"{name}, {state}" if name and state else name
        _geocode_cache[key] = (_now(), city)
        return city
    except Exception:
        _geocode_cache[key] = (_now(), None)
        return None


_forward_geocode_cache: dict[str, tuple[float, tuple[float, float] | None]] = {}
_ZIP_RE = re.compile(r"^\d{5}$")


def geocode_location(text: str) -> tuple[float, float] | None:
    """Free-text location (US zip code or city/place name) -> (lat, lon).
    Forward counterpart to reverse_geocode_city — same OPENWEATHERMAP_API_KEY,
    same free geocoding API, same graceful-degrade-on-failure contract (never
    raises; callers fall back to whatever location they already had). A bare
    5-digit string is treated as a US zip (the dedicated /geo/1.0/zip endpoint
    is more reliable than /direct for zips); anything else goes through
    /geo/1.0/direct as a city/place query."""
    text = (text or "").strip()
    if not text:
        return None

    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return None

    key = text.lower()
    cached = _forward_geocode_cache.get(key)
    if cached and (_now() - cached[0]) < _GEOCODE_TTL_SECONDS:
        return cached[1]

    is_zip = bool(_ZIP_RE.match(text))
    url = "http://api.openweathermap.org/geo/1.0/zip" if is_zip else "http://api.openweathermap.org/geo/1.0/direct"
    params = {"zip": f"{text},US", "appid": api_key} if is_zip else {"q": text, "limit": 1, "appid": api_key}

    try:
        resp = requests.get(url, params=params, timeout=3)
        data = resp.json()
        if resp.status_code != 200 or not data:
            _forward_geocode_cache[key] = (_now(), None)
            return None
        place = data if is_zip else data[0]
        lat, lon = place.get("lat"), place.get("lon")
        if lat is None or lon is None:
            _forward_geocode_cache[key] = (_now(), None)
            return None
        result = (float(lat), float(lon))
        _forward_geocode_cache[key] = (_now(), result)
        return result
    except Exception:
        _forward_geocode_cache[key] = (_now(), None)
        return None


def calc_sweat_output(athlete: dict, event: dict, weather: dict) -> dict:
    wt_kg = athlete["weight_lbs"] * 0.453592
    event_type = (event.get("event_type") or "").lower()

    if any(x in event_type for x in ["game", "tournament"]):
        base_rate = 1.2
    elif any(x in event_type for x in ["practice", "training", "strength"]):
        base_rate = 1.0
    else:
        base_rate = 0.5

    sweat_multipliers = {"light": 0.7, "moderate": 1.0, "heavy": 1.3, "very heavy": 1.6}
    profile_mult = sweat_multipliers.get(derive_sweat_profile(athlete), 1.0)

    temp_f = weather.get("temp_f")
    humidity = weather.get("humidity")
    temp_mult = 1.0
    humidity_mult = 1.0

    if temp_f:
        if temp_f > 95:
            temp_mult = 1.40
        elif temp_f > 85:
            temp_mult = 1.25
        elif temp_f > 75:
            temp_mult = 1.10

    if humidity:
        if humidity > 80:
            humidity_mult = 1.30
        elif humidity > 60:
            humidity_mult = 1.15

    duration = event.get("duration_hours") or 1.5
    sweat_rate = base_rate * profile_mult * temp_mult * humidity_mult
    total_loss_liters = sweat_rate * duration
    hydration_oz_during = int(total_loss_liters * 33.8)

    electrolytes_needed = False
    reasons = []

    if temp_f and temp_f > 80:
        electrolytes_needed = True
        reasons.append(f"Temperature {temp_f:.0f}°F")
    if humidity and humidity > 70:
        electrolytes_needed = True
        reasons.append(f"Humidity {humidity}%")
    if duration > 1.0:
        electrolytes_needed = True
        reasons.append(f"Event duration {duration}hrs")
    if "tournament" in event_type:
        electrolytes_needed = True
        reasons.append("Tournament day")
    if "strength" in event_type and duration > 0.75:
        electrolytes_needed = True
        reasons.append("Strength training")

    recommendations = []
    if electrolytes_needed:
        recommendations.append("Natural sports drink — NO artificial dyes (Red #40, Yellow #5, Yellow #6 linked to behavioral changes in adolescents — Everett MD 2025)")
        if temp_f and temp_f > 80:
            recommendations.append("Add a pinch of salt to your pre-event meal")
        if "tournament" in event_type:
            recommendations.append("Sodium + potassium priority between games")
    else:
        recommendations.append("Plain water is sufficient — no sports drink needed")
    recommendations.append("Drink 6-8oz every 20 minutes during activity")

    return {
        "sweat_loss_liters": round(total_loss_liters, 2),
        "hydration_oz_during": hydration_oz_during,
        "electrolytes_needed": electrolytes_needed,
        "electrolyte_reason": ", ".join(reasons) if reasons else None,
        "weather_temp_f": temp_f,
        "weather_humidity": humidity,
        "recommendations": recommendations,
    }
