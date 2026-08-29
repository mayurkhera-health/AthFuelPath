"""FDC_API_KEY secret-leak regression — api/services/fdc_client.py +
api/routes/meals.py (Security Item 4, S1).

api/services/fdc_client.py::search_foods() sends the USDA FDC API key as a
URL QUERY PARAMETER (`params={"api_key": ...}`) and previously called
resp.raise_for_status() unguarded — requests.exceptions.HTTPError's message
includes the fully-resolved request URL, key included. Both
POST /api/meals/analyze-photo and POST /api/meals/analyze-voice route this
straight into a client-facing HTTPException via a broad
`except Exception as e: raise HTTPException(500, f"...: {e}")`, so any
authenticated caller hitting either endpoint during an FDC outage/rate-limit/
key-rotation window received the live API key in the JSON error body.

Fixed by catching every FDC failure INSIDE fdc_client.py and re-raising a
typed FdcError subclass whose message only ever contains a safe status_code/
category — never resp.url, never the api_key, never raw request/response
headers (same principle as instacart_client.py's InstacartError hierarchy,
whose own docstring says "Never includes the API key").

This file proves, for a realistic range of upstream failure modes (401-style
rejection, 404, 429, 500, timeout, connection error): the sentinel key never
reaches the client response, never reaches exception text that could escape
the service boundary, and never reaches logs.
"""
import logging
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

import pytest
import requests as requests_lib
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services import fdc_client
from tests.conftest import auth_headers

SENTINEL_KEY = "TEST_SECRET_FDC_KEY_12345"
SENTINEL_URL = f"https://api.nal.usda.gov/fdc/v1/foods/search?api_key={SENTINEL_KEY}"


@pytest.fixture(autouse=True)
def _fdc_key(monkeypatch):
    monkeypatch.setenv("FDC_API_KEY", SENTINEL_KEY)


def _http_error_response(status_code):
    """A REAL requests.Response — raise_for_status() produces requests' own
    real HTTPError formatting, which is what actually leaks the URL/key in
    production, not a hand-crafted approximation of it."""
    resp = requests_lib.Response()
    resp.status_code = status_code
    resp.url = SENTINEL_URL
    resp._content = b'{"error": "upstream failure"}'
    return resp


def _post_returns(status_code):
    def fake_post(url, params=None, json=None, timeout=None):
        assert params.get("api_key") == SENTINEL_KEY  # sanity: this IS the real call shape
        return _http_error_response(status_code)
    return fake_post


def _post_raises(exc):
    def fake_post(url, params=None, json=None, timeout=None):
        assert params.get("api_key") == SENTINEL_KEY
        raise exc
    return fake_post


# ─── Service-layer: sentinel must never appear in raised exception text ────

@pytest.mark.parametrize("status_code", [401, 403, 404, 429, 500])
def test_search_foods_never_leaks_key_in_exception_text(monkeypatch, status_code):
    monkeypatch.setattr(fdc_client.requests, "post", _post_returns(status_code))
    with pytest.raises(Exception) as exc_info:
        fdc_client.search_foods("chicken breast")
    assert SENTINEL_KEY not in str(exc_info.value)
    assert SENTINEL_URL not in str(exc_info.value)


def test_search_foods_never_leaks_key_on_timeout(monkeypatch):
    timeout_exc = requests_lib.exceptions.Timeout(
        f"HTTPSConnectionPool(host='api.nal.usda.gov', port=443): Read timed out. "
        f"(read timeout=30) url=/fdc/v1/foods/search?api_key={SENTINEL_KEY}"
    )
    monkeypatch.setattr(fdc_client.requests, "post", _post_raises(timeout_exc))
    with pytest.raises(Exception) as exc_info:
        fdc_client.search_foods("chicken breast")
    assert SENTINEL_KEY not in str(exc_info.value)


def test_search_foods_never_leaks_key_on_connection_error(monkeypatch):
    conn_exc = requests_lib.exceptions.ConnectionError(
        f"HTTPSConnectionPool(host='api.nal.usda.gov', port=443): Max retries exceeded "
        f"with url: /fdc/v1/foods/search?api_key={SENTINEL_KEY} "
        f"(Caused by NewConnectionError('Failed to establish a new connection'))"
    )
    monkeypatch.setattr(fdc_client.requests, "post", _post_raises(conn_exc))
    with pytest.raises(Exception) as exc_info:
        fdc_client.search_foods("chicken breast")
    assert SENTINEL_KEY not in str(exc_info.value)


# ─── Logs: sentinel must never be written, even server-side ────────────────

def test_search_foods_failure_never_logs_the_key(monkeypatch, caplog):
    monkeypatch.setattr(fdc_client.requests, "post", _post_returns(500))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(Exception):
            fdc_client.search_foods("chicken breast")
    assert SENTINEL_KEY not in caplog.text


# ─── Route-level: sentinel must never appear in the HTTP response body ─────

@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    keepalive.execute("DELETE FROM meal_logs")
    keepalive.execute("DELETE FROM athletes")
    keepalive.execute("DELETE FROM parents")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def make_parent(email):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("Test Parent", email.lower(), datetime.utcnow().isoformat(), True),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


def make_athlete(parent_id, first_name="Alex"):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO athletes
               (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in)
               VALUES (%s, %s, 15, 'girl', 115, 5, 6) RETURNING id""",
            (parent_id, first_name),
        )
        conn.commit()
        return cur.fetchone()["id"]
    finally:
        conn.close()


@pytest.mark.parametrize("status_code", [401, 403, 404, 429, 500])
def test_analyze_photo_never_leaks_key_in_response(client, monkeypatch, caplog, status_code):
    parent_id = make_parent(f"photoleak{status_code}@example.com")
    athlete_id = make_athlete(parent_id)

    import api.services.photo_meal_analyzer as photo_meal_analyzer
    monkeypatch.setattr(
        photo_meal_analyzer, "detect_foods",
        lambda *a, **k: [{"name": "grilled chicken", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                          "estimated_portion_g": 120}],
    )
    monkeypatch.setattr(fdc_client.requests, "post", _post_returns(status_code))

    with caplog.at_level(logging.DEBUG):
        r = client.post(
            "/api/meals/analyze-photo",
            json={"athlete_id": athlete_id, "image_base64": "x" * 200},
            headers=auth_headers("athlete", athlete_id=athlete_id),
        )
    assert r.status_code == 503, r.text
    assert SENTINEL_KEY not in r.text
    assert SENTINEL_URL not in r.text
    assert SENTINEL_KEY not in caplog.text


@pytest.mark.parametrize("status_code", [401, 403, 404, 429, 500])
def test_analyze_voice_never_leaks_key_in_response(client, monkeypatch, caplog, status_code):
    parent_id = make_parent(f"voiceleak{status_code}@example.com")
    athlete_id = make_athlete(parent_id)

    import api.services.voice_meal_analyzer as voice_meal_analyzer
    monkeypatch.setattr(
        voice_meal_analyzer, "detect_foods_from_text",
        lambda *a, **k: [{"name": "grilled chicken", "estimated_portion_g": 120}],
    )
    monkeypatch.setattr(fdc_client.requests, "post", _post_returns(status_code))

    with caplog.at_level(logging.DEBUG):
        r = client.post(
            "/api/meals/analyze-voice",
            json={"athlete_id": athlete_id, "transcription": "chicken and rice"},
            headers=auth_headers("athlete", athlete_id=athlete_id),
        )
    assert r.status_code == 503, r.text
    assert SENTINEL_KEY not in r.text
    assert SENTINEL_URL not in r.text
    assert SENTINEL_KEY not in caplog.text


def test_analyze_photo_never_leaks_key_on_timeout(client, monkeypatch, caplog):
    parent_id = make_parent("phototimeout@example.com")
    athlete_id = make_athlete(parent_id)
    import api.services.photo_meal_analyzer as photo_meal_analyzer
    monkeypatch.setattr(
        photo_meal_analyzer, "detect_foods",
        lambda *a, **k: [{"name": "grilled chicken", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                          "estimated_portion_g": 120}],
    )
    timeout_exc = requests_lib.exceptions.Timeout(
        f"HTTPSConnectionPool(host='api.nal.usda.gov', port=443): Read timed out. "
        f"(read timeout=30) url=/fdc/v1/foods/search?api_key={SENTINEL_KEY}"
    )
    monkeypatch.setattr(fdc_client.requests, "post", _post_raises(timeout_exc))

    with caplog.at_level(logging.DEBUG):
        r = client.post(
            "/api/meals/analyze-photo",
            json={"athlete_id": athlete_id, "image_base64": "x" * 200},
            headers=auth_headers("athlete", athlete_id=athlete_id),
        )
    assert r.status_code == 503, r.text
    assert SENTINEL_KEY not in r.text
    assert SENTINEL_KEY not in caplog.text


def test_analyze_photo_never_leaks_key_on_connection_error(client, monkeypatch, caplog):
    parent_id = make_parent("photoconnerr@example.com")
    athlete_id = make_athlete(parent_id)
    import api.services.photo_meal_analyzer as photo_meal_analyzer
    monkeypatch.setattr(
        photo_meal_analyzer, "detect_foods",
        lambda *a, **k: [{"name": "grilled chicken", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                          "estimated_portion_g": 120}],
    )
    conn_exc = requests_lib.exceptions.ConnectionError(
        f"HTTPSConnectionPool(host='api.nal.usda.gov', port=443): Max retries exceeded "
        f"with url: /fdc/v1/foods/search?api_key={SENTINEL_KEY} "
        f"(Caused by NewConnectionError('Failed to establish a new connection'))"
    )
    monkeypatch.setattr(fdc_client.requests, "post", _post_raises(conn_exc))

    with caplog.at_level(logging.DEBUG):
        r = client.post(
            "/api/meals/analyze-photo",
            json={"athlete_id": athlete_id, "image_base64": "x" * 200},
            headers=auth_headers("athlete", athlete_id=athlete_id),
        )
    assert r.status_code == 503, r.text
    assert SENTINEL_KEY not in r.text
    assert SENTINEL_KEY not in caplog.text


# ─── Success-path regression: FDC lookup still works when it succeeds ──────

def _ok_response(foods):
    resp = requests_lib.Response()
    resp.status_code = 200
    resp.url = SENTINEL_URL
    import json as _json
    resp._content = _json.dumps({"foods": foods}).encode()
    return resp


_CHICKEN_FOOD = {
    "fdcId": 171077,
    "description": "Chicken, breast, grilled",
    "foodNutrients": [
        {"nutrientId": 1008, "value": 165},
        {"nutrientId": 1003, "value": 31},
        {"nutrientId": 1005, "value": 0},
        {"nutrientId": 1004, "value": 3.6},
    ],
}


def test_search_foods_success_path_unchanged(monkeypatch):
    def fake_post(url, params=None, json=None, timeout=None):
        assert params["api_key"] == SENTINEL_KEY
        return _ok_response([_CHICKEN_FOOD])
    monkeypatch.setattr(fdc_client.requests, "post", fake_post)

    foods = fdc_client.search_foods("grilled chicken breast")
    assert foods == [_CHICKEN_FOOD]
    match = fdc_client.best_match("grilled chicken breast")
    assert match == _CHICKEN_FOOD
    macros = fdc_client.macros_for_portion(match, 120)
    assert macros["calories"] == round(165 * 1.2)


def test_analyze_photo_success_path_unchanged(client, monkeypatch):
    parent_id = make_parent("photook@example.com")
    athlete_id = make_athlete(parent_id)
    import api.services.photo_meal_analyzer as photo_meal_analyzer
    monkeypatch.setattr(
        photo_meal_analyzer, "detect_foods",
        lambda *a, **k: [{"name": "grilled chicken", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                          "estimated_portion_g": 120}],
    )
    monkeypatch.setattr(fdc_client.requests, "post", lambda *a, **k: _ok_response([_CHICKEN_FOOD]))

    r = client.post(
        "/api/meals/analyze-photo",
        json={"athlete_id": athlete_id, "image_base64": "x" * 200},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200, r.text
    analysis = r.json()["analysis"]
    food = analysis["foods"][0]
    assert food["fdc_id"] == 171077
    assert food["fdc_description"] == "Chicken, breast, grilled"
    assert food["calories"] == round(165 * 1.2)


def test_analyze_voice_success_path_unchanged(client, monkeypatch):
    parent_id = make_parent("voiceok@example.com")
    athlete_id = make_athlete(parent_id)
    import api.services.voice_meal_analyzer as voice_meal_analyzer
    monkeypatch.setattr(
        voice_meal_analyzer, "detect_foods_from_text",
        lambda *a, **k: [{"name": "grilled chicken", "estimated_portion_g": 120}],
    )
    monkeypatch.setattr(fdc_client.requests, "post", lambda *a, **k: _ok_response([_CHICKEN_FOOD]))

    r = client.post(
        "/api/meals/analyze-voice",
        json={"athlete_id": athlete_id, "transcription": "grilled chicken"},
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 200, r.text
    analysis = r.json()["analysis"]
    food = analysis["foods"][0]
    assert food["fdc_id"] == 171077
    assert food["fdc_description"] == "Chicken, breast, grilled"
    assert food["calories"] == round(165 * 1.2)
