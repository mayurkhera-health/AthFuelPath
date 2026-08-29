"""Athlete weight/height numeric bounds (Security Item 6, N2) — applies
consistently across POST /api/athletes/, PUT /api/athletes/{id}, and
POST /api/onboarding/complete (all three ultimately build an AthleteCreate/
OnboardingAthlete instance).

weight_lbs/height_ft/height_in were bare, unbounded float/int fields —
nothing in Pydantic, the route, or the DB stopped an implausible value (a
parent fat-fingering a digit or unit during onboarding, or a tampered
client) from silently corrupting every downstream nutrition target for that
athlete (calc_rmr/calc_daily_targets derive RMR/TDEE/carb/protein/hydration
straight from these).

Fixed with broad Field(ge=, le=) bounds — input-integrity limits, not
medical/performance targets. The existing 13-17 age gate (route-level, not
model-level) is unchanged.
"""
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime

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


def _athlete_count(parent_id) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM athletes WHERE parent_id = %s", (parent_id,)
        ).fetchone()["c"]
    finally:
        conn.close()


def _parent_count(email) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM parents WHERE email = %s", (email.lower(),)
        ).fetchone()["c"]
    finally:
        conn.close()


def _athlete_body(parent_id, **overrides):
    body = {
        "parent_id": parent_id, "first_name": "New Kid", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 4,
    }
    body.update(overrides)
    return body


# field -> (below-min, above-max, valid boundary-low, valid boundary-high, ordinary)
_MEASUREMENTS = {
    "weight_lbs": (1, 5000, 30, 500, 110),
    "height_ft":  (0, 20, 3, 8, 5),
    "height_in":  (-1, 100, 0, 11, 4),
}


# ─── A: POST /api/athletes/ ─────────────────────────────────────────────────

@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_post_athlete_rejects_below_min(client, field):
    parent_id = make_parent(f"post-belowmin-{field}@example.com")
    below_min, _, _, _, _ = _MEASUREMENTS[field]
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id, **{field: below_min}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 422, r.text
    assert _athlete_count(parent_id) == 0


@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_post_athlete_rejects_above_max(client, field):
    parent_id = make_parent(f"post-abovemax-{field}@example.com")
    _, above_max, _, _, _ = _MEASUREMENTS[field]
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id, **{field: above_max}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 422, r.text
    assert _athlete_count(parent_id) == 0


@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_post_athlete_accepts_boundary_values(client, field):
    parent_id = make_parent(f"post-boundary-{field}@example.com")
    _, _, low, high, _ = _MEASUREMENTS[field]
    r_low = client.post(
        "/api/athletes/", json=_athlete_body(parent_id, first_name="Low", **{field: low}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r_low.status_code == 201, r_low.text
    r_high = client.post(
        "/api/athletes/", json=_athlete_body(parent_id, first_name="High", **{field: high}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r_high.status_code == 201, r_high.text


@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_post_athlete_accepts_ordinary_value(client, field):
    parent_id = make_parent(f"post-ordinary-{field}@example.com")
    _, _, _, _, ordinary = _MEASUREMENTS[field]
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id, **{field: ordinary}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 201, r.text


def test_post_athlete_normal_values_response_shape_unchanged(client):
    parent_id = make_parent("post-shape@example.com")
    r = client.post(
        "/api/athletes/", json=_athlete_body(parent_id),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["weight_lbs"] == 110
    assert body["height_ft"] == 5
    assert body["height_in"] == 4


# ─── B: PUT /api/athletes/{id} ──────────────────────────────────────────────

@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_put_athlete_rejects_below_min(client, field):
    parent_id = make_parent(f"put-belowmin-{field}@example.com")
    athlete_id = make_athlete(parent_id)
    below_min, _, _, _, _ = _MEASUREMENTS[field]
    r = client.put(
        f"/api/athletes/{athlete_id}", json=_athlete_body(parent_id, **{field: below_min}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_put_athlete_rejects_above_max(client, field):
    parent_id = make_parent(f"put-abovemax-{field}@example.com")
    athlete_id = make_athlete(parent_id)
    _, above_max, _, _, _ = _MEASUREMENTS[field]
    r = client.put(
        f"/api/athletes/{athlete_id}", json=_athlete_body(parent_id, **{field: above_max}),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 422, r.text


def test_put_athlete_normal_values_still_succeeds(client):
    parent_id = make_parent("put-normal@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.put(
        f"/api/athletes/{athlete_id}", json=_athlete_body(parent_id, weight_lbs=120, height_ft=5, height_in=8),
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert r.status_code == 200, r.text
    assert r.json()["weight_lbs"] == 120


# ─── C: POST /api/onboarding/complete ──────────────────────────────────────

def _onboarding_body(email, **athlete_overrides):
    athlete = {
        "first_name": "New Kid", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 4,
    }
    athlete.update(athlete_overrides)
    return {
        "parent": {"full_name": "Test Parent", "email": email, "consent_confirmed": True},
        "athlete": athlete,
    }


@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_onboarding_rejects_below_min(client, field):
    email = f"onboard-belowmin-{field}@example.com"
    below_min, _, _, _, _ = _MEASUREMENTS[field]
    r = client.post("/api/onboarding/complete", json=_onboarding_body(email, **{field: below_min}))
    assert r.status_code == 422, r.text
    assert _parent_count(email) == 0


@pytest.mark.parametrize("field", list(_MEASUREMENTS.keys()))
def test_onboarding_rejects_above_max(client, field):
    email = f"onboard-abovemax-{field}@example.com"
    _, above_max, _, _, _ = _MEASUREMENTS[field]
    r = client.post("/api/onboarding/complete", json=_onboarding_body(email, **{field: above_max}))
    assert r.status_code == 422, r.text
    assert _parent_count(email) == 0


def test_onboarding_normal_values_creates_parent_and_athlete(client):
    email = "onboard-normal@example.com"
    r = client.post("/api/onboarding/complete", json=_onboarding_body(email))
    assert r.status_code == 201, r.text
    assert _parent_count(email) == 1
    parent_id = r.json()["parent"]["id"]
    assert _athlete_count(parent_id) == 1
