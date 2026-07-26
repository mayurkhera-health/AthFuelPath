"""Integration tests for the Performance Plate route (GET /api/plate/window)."""
import os
os.environ["DB_PATH"] = ":memory:"
os.environ["PERFORMANCE_PLATE_ENABLED"] = "true"  # flag ships dark; on for these tests

import json
import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    # NOTE: plain TestClient (no `with`) — we deliberately skip the app lifespan
    # startup, whose embedding backfill races on the :memory: connection and
    # intermittently 500s with "database table is locked". Routes register at
    # import, so no lifespan is needed for these tests.
    yield TestClient(app)
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client, *, allergies=None, dietary=None):
    _counter["n"] += 1
    email = f"plate{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 15, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6,
    })
    assert a.status_code == 201, a.text
    aid = a.json()["id"]
    # Seed allergies/dietary directly the way prod stores them (JSON string in the
    # athletes column) — the create API has its own array-vs-string validation quirk.
    if allergies is not None or dietary is not None:
        conn = get_conn()
        conn.execute(
            "UPDATE athletes SET allergies = ?, dietary_restrictions = ? WHERE id = ?",
            (json.dumps(allergies) if allergies is not None else None,
             json.dumps(dietary) if dietary is not None else None, aid),
        )
        conn.commit()
    return aid


def test_window_returns_plate_and_options(client):
    aid = _make_athlete(client)
    r = client.get(
        "/api/plate/window", params={"athlete_id": aid, "window_key": "everyday_breakfast"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plate"] is not None
    assert body["profile_key"] == "breakfast"
    keys = [s["key"] for s in body["plate"]["sections"]]
    assert keys == ["carbs", "protein", "veg", "fat"]
    assert 1 <= len(body["options"]) <= 8
    for o in body["options"]:
        assert o["id"]
        assert o["short_label"]
        assert isinstance(o["plate_sections"], list)


def test_plate_resizes_between_windows(client):
    """Different windows must yield different plate shapes (the whole point)."""
    aid = _make_athlete(client)
    headers = auth_headers("athlete", athlete_id=aid)
    bfast = client.get(
        "/api/plate/window", params={"athlete_id": aid, "window_key": "everyday_breakfast"}, headers=headers
    ).json()
    snack = client.get(
        "/api/plate/window", params={"athlete_id": aid, "window_key": "quick_snack"}, headers=headers
    ).json()
    carbs_bfast = next(s["pct"] for s in bfast["plate"]["sections"] if s["key"] == "carbs")
    carbs_snack = next(s["pct"] for s in snack["plate"]["sections"] if s["key"] == "carbs")
    assert carbs_snack > carbs_bfast  # quick snack is far more carb-dominant


def test_nudge_window_has_no_plate(client):
    aid = _make_athlete(client)
    r = client.get(
        "/api/plate/window", params={"athlete_id": aid, "window_key": "between_games"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plate"] is None
    assert body["profile_key"] is None
    assert body["options"] == []


def test_allergy_filters_options(client):
    """A dairy-allergic athlete must never be offered a dairy dish."""
    aid = _make_athlete(client, allergies=["dairy"])
    r = client.get(
        "/api/plate/window", params={"athlete_id": aid, "window_key": "everyday_dinner"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    labels = [o["short_label"].lower() for o in r.json()["options"]]
    # Butter chicken (dairy) must be excluded; some options should still remain.
    assert r.json()["options"], "expected some non-dairy dinner options"
    assert not any("butter chicken" in lbl for lbl in labels)


def test_unknown_athlete_404(client):
    # A parent-role token always resolves ownership via a DB lookup (unlike an
    # athlete token, which can short-circuit on athlete_id match alone) — the
    # actual parent_id value doesn't matter since athlete 999999 doesn't exist.
    r = client.get(
        "/api/plate/window", params={"athlete_id": 999999, "window_key": "everyday_dinner"},
        headers=auth_headers("parent", parent_id=1),
    )
    assert r.status_code == 404


def test_flag_off_returns_empty(client, monkeypatch):
    """With PERFORMANCE_PLATE_ENABLED off, the endpoint is dark (no plate/options)."""
    aid = _make_athlete(client)
    monkeypatch.setenv("PERFORMANCE_PLATE_ENABLED", "false")
    r = client.get(
        "/api/plate/window", params={"athlete_id": aid, "window_key": "everyday_breakfast"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plate"] is None
    assert body["profile_key"] is None
    assert body["options"] == []
