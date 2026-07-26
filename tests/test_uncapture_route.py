"""End-to-end tests for the window un-confirm endpoint (DELETE .../capture).

Env is set via function-scoped monkeypatch (NOT module level) so the feature
flags never leak into other test modules — EVENT_RELATIVE_WINDOWS in particular
changes the window engine and would break the legacy-engine tests if it leaked.
"""

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_headers

TODAY = "2026-06-23"
_n = {"i": 0}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DB_PATH", ":memory:")
    monkeypatch.setenv("FUEL_GAUGE_ENABLED", "true")
    monkeypatch.setenv("EVENT_RELATIVE_WINDOWS", "true")
    from db.setup import init_db
    from api.services.db_migrations import run_all
    from api.database import get_conn
    from api.main import app

    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def _athlete_with_game(client):
    _n["i"] += 1
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"unc{_n['i']}@example.com", "consent_confirmed": True})
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 4,
        "competition_level": "competitive_club"})
    aid = a.json()["id"]
    client.post("/api/events/", json={
        "athlete_id": aid, "event_name": "Game", "event_type": "game",
        "event_date": TODAY, "start_time": "10:00", "duration_hours": 1.5})
    return aid


def _tappable_slot(view):
    for w in view["windows"]:
        if w.get("status") != "nudge":
            return w["slot_name"]
    raise AssertionError("expected a tappable window on a game day")


def test_delete_endpoint_unconfirms_and_returns_refreshed_today(client):
    aid = _athlete_with_game(client)
    headers = auth_headers("athlete", athlete_id=aid)
    view = client.get(f"/api/athletes/{aid}/today", params={"date": TODAY}, headers=headers).json()
    slot = _tappable_slot(view)

    # confirm via capture
    r = client.post(f"/api/athletes/{aid}/windows/{slot}/capture",
                    data={"method": "text", "text": "x", "log_date": TODAY}, headers=headers)
    assert r.status_code == 200
    assert {w["slot_name"]: w["logged"] for w in r.json()["windows"]}[slot] is True

    # un-confirm via DELETE → returns refreshed Today with the window reversed
    d = client.delete(f"/api/athletes/{aid}/windows/{slot}/capture", params={"log_date": TODAY}, headers=headers)
    assert d.status_code == 200
    body = d.json()
    assert {w["slot_name"]: w["logged"] for w in body["windows"]}[slot] is False
    # gauge state reflects the un-confirm
    assert {w["slot_name"]: w["confirmed"] for w in body["fuel_targets"]["windows"]}[slot] is False


def test_delete_is_idempotent_on_unconfirmed_window(client):
    aid = _athlete_with_game(client)
    d = client.delete(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
                      params={"log_date": TODAY}, headers=auth_headers("athlete", athlete_id=aid))
    assert d.status_code == 200  # no-op, not an error


def test_confirm_tap_drives_gauge_and_delete_decrements(client):
    """End-to-end: the LIVE confirm endpoint (POST /confirmations) fills the gauge,
    and the existing DELETE /confirmations decrements it (Option A union)."""
    aid = _athlete_with_game(client)
    headers = auth_headers("athlete", athlete_id=aid)
    view = client.get(f"/api/athletes/{aid}/today", params={"date": TODAY}, headers=headers).json()
    slot = _tappable_slot(view)

    # confirm via the live Today endpoint (the button the app already uses)
    r = client.post(f"/api/athletes/{aid}/confirmations",
                    json={"window_key": slot, "window_type": "pre_fuel", "log_date": TODAY}, headers=headers)
    assert r.status_code == 200, r.text
    after_confirm = client.get(f"/api/athletes/{aid}/today", params={"date": TODAY}, headers=headers).json()
    assert {w["slot_name"]: w["confirmed"]
            for w in after_confirm["fuel_targets"]["windows"]}[slot] is True

    # un-confirm via the existing DELETE /confirmations (no new endpoint needed)
    d = client.delete(f"/api/athletes/{aid}/confirmations",
                      params={"window_key": slot, "log_date": TODAY}, headers=headers)
    assert d.status_code == 200
    after_delete = client.get(f"/api/athletes/{aid}/today", params={"date": TODAY}, headers=headers).json()
    assert {w["slot_name"]: w["confirmed"]
            for w in after_delete["fuel_targets"]["windows"]}[slot] is False
