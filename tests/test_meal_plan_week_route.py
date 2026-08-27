"""GET /api/athletes/:id/meal-plan/week — week-batched real-engine windows
for the mobile Plan tab. Confirms: 7 days returned, a rest day gets the 4
everyday windows, a practice day gets real pre/post-event windows (not a
single generic bucket), and ownership is enforced."""
import os
os.environ["DB_PATH"] = ":memory:"
os.environ["EVENT_RELATIVE_WINDOWS"] = "true"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client):
    _counter["n"] += 1
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"weekwindows{_counter['n']}@example.com", "consent_confirmed": True,
    })
    pid = p.json()["id"]
    # POST /api/athletes/ requires a session (auth v2.1 BOLA hardening,
    # landed on main after this route was originally authored).
    a = client.post(
        "/api/athletes/",
        json={
            "parent_id": pid, "first_name": "A", "age": 15, "gender": "girl",
            "weight_lbs": 110, "height_ft": 5, "height_in": 6,
        },
        headers=auth_headers("parent", parent_id=pid),
    )
    return a.json()["id"]


def test_returns_all_7_days_starting_at_week_start(client):
    aid = _make_athlete(client)
    r = client.get(
        "/api/athletes/{}/meal-plan/week".format(aid),
        params={"week_start": "2026-08-16"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 200, r.text
    days = r.json()["days"]
    assert set(days.keys()) == {
        "2026-08-16", "2026-08-17", "2026-08-18", "2026-08-19",
        "2026-08-20", "2026-08-21", "2026-08-22",
    }


def test_rest_day_gets_4_everyday_windows(client):
    aid = _make_athlete(client)
    r = client.get(
        "/api/athletes/{}/meal-plan/week".format(aid),
        params={"week_start": "2026-08-16"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    windows = r.json()["days"]["2026-08-16"]["windows"]
    keys = {w["window_key"] for w in windows}
    assert keys == {"everyday_breakfast", "everyday_lunch", "everyday_snack", "everyday_dinner"}


def test_practice_day_gets_real_pre_and_post_windows_not_one_generic_bucket(client):
    aid = _make_athlete(client)
    client.post(
        "/api/events/",
        json={
            "athlete_id": aid, "event_name": "Evening Practice", "event_type": "practice",
            "event_date": "2026-08-20", "start_time": "19:00", "duration_hours": 1.5,
        },
        headers=auth_headers("athlete", athlete_id=aid),
    )
    r = client.get(
        "/api/athletes/{}/meal-plan/week".format(aid),
        params={"week_start": "2026-08-16"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    windows = r.json()["days"]["2026-08-20"]["windows"]
    keys = {w["window_key"] for w in windows}
    # A single "practice" bucket must NOT be the outcome — this is the exact
    # bug the user reported (one generic Practice Fuel window regardless of
    # the practice's actual time).
    assert "practice" not in keys
    assert any(k.startswith("pre_event_meal") for k in keys), keys
    assert any(k.startswith("fuel_after_primary") for k in keys), keys


def test_ownership_enforced(client):
    aid = _make_athlete(client)
    other_aid = _make_athlete(client)
    r = client.get(
        "/api/athletes/{}/meal-plan/week".format(aid),
        params={"week_start": "2026-08-16"},
        headers=auth_headers("athlete", athlete_id=other_aid),
    )
    assert r.status_code == 403
