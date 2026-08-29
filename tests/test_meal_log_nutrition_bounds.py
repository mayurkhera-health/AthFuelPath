"""Manual meal-log numeric bounds — POST /api/meals/ (Security Item 6, N1).

MealLogCreate's calories/carbs_g/protein_g/fat_g/iron_mg/calcium_mg/water_oz
were all bare Optional[float] with no bound at any layer — Pydantic, route,
or DB. A client (fat-fingered typo or a tampered app) could submit a
negative or absurdly large value and it would be inserted into meal_logs
verbatim, feeding directly into the AI Nutrition Coach's prompt, the
Weekly Report's nutrient totals / low-iron safety flag, and the Today
screen's logged totals with no plausibility check anywhere.

Fixed with broad, deliberately generous Field(ge=, le=) bounds on
MealLogCreate — this is corruption-prevention, not nutrition guidance: the
ceilings are far above any real single meal, so no legitimate log is ever
rejected. None remains valid for every field (manual logging doesn't
require every nutrient to be estimated).
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


def _meal_logs_count(athlete_id) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) c FROM meal_logs WHERE athlete_id = %s", (athlete_id,)
        ).fetchone()["c"]
    finally:
        conn.close()


def _base_body(athlete_id, **overrides):
    body = {"athlete_id": athlete_id, "log_method": "text", "description": "Chicken and rice"}
    body.update(overrides)
    return body


# Field -> (below-min value, above-max value, ordinary valid value, meaningful-zero?)
_BOUNDS = {
    "calories":    (-500, 1_000_000, 650, True),
    "carbs_g":     (-10, 100_000, 80, True),
    "protein_g":   (-10, 100_000, 35, True),
    "fat_g":       (-10, 100_000, 20, True),
    "iron_mg":     (-1, 1_000, 3, True),
    "calcium_mg":  (-1, 100_000, 300, True),
    "water_oz":    (-100, 10_000, 12, True),
}


@pytest.mark.parametrize("field", list(_BOUNDS.keys()))
def test_negative_value_currently_rejected(client, field):
    """RED (pre-fix): this currently PASSES (201) against unmodified
    MealLogCreate — the parametrize id names the field under test so a
    failure here after the fix pinpoints exactly which bound is missing."""
    parent_id = make_parent(f"neg-{field}@example.com")
    athlete_id = make_athlete(parent_id)
    below_min, _, _, _ = _BOUNDS[field]
    r = client.post(
        "/api/meals/", json=_base_body(athlete_id, **{field: below_min}),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 422, r.text
    assert _meal_logs_count(athlete_id) == 0


@pytest.mark.parametrize("field", list(_BOUNDS.keys()))
def test_extreme_value_currently_rejected(client, field):
    parent_id = make_parent(f"ext-{field}@example.com")
    athlete_id = make_athlete(parent_id)
    _, above_max, _, _ = _BOUNDS[field]
    r = client.post(
        "/api/meals/", json=_base_body(athlete_id, **{field: above_max}),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 422, r.text
    assert _meal_logs_count(athlete_id) == 0


@pytest.mark.parametrize("field", list(_BOUNDS.keys()))
def test_zero_is_accepted(client, field):
    """Zero is meaningful (e.g. a water-only entry with 0 protein) — must
    not be rejected by a ge=0 bound."""
    parent_id = make_parent(f"zero-{field}@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/meals/", json=_base_body(athlete_id, **{field: 0}),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert _meal_logs_count(athlete_id) == 1


@pytest.mark.parametrize("field", list(_BOUNDS.keys()))
def test_ordinary_value_is_accepted(client, field):
    parent_id = make_parent(f"ok-{field}@example.com")
    athlete_id = make_athlete(parent_id)
    _, _, ordinary, _ = _BOUNDS[field]
    r = client.post(
        "/api/meals/", json=_base_body(athlete_id, **{field: ordinary}),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert _meal_logs_count(athlete_id) == 1


def test_all_nutrition_fields_none_is_accepted(client):
    """Manual logging doesn't require every nutrient to be estimated."""
    parent_id = make_parent("all-none@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/meals/", json=_base_body(athlete_id),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    for field in _BOUNDS:
        assert body[field] is None


def test_realistic_full_meal_log_is_accepted(client):
    parent_id = make_parent("realistic@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post(
        "/api/meals/",
        json=_base_body(
            athlete_id, calories=650, carbs_g=80, protein_g=35, fat_g=20,
            iron_mg=3, calcium_mg=300, water_oz=12,
        ),
        headers=auth_headers("athlete", athlete_id=athlete_id),
    )
    assert r.status_code == 201, r.text
    assert _meal_logs_count(athlete_id) == 1


# ─── Rejected requests must not corrupt another athlete's data ────────────

def test_rejected_value_does_not_touch_another_athletes_data(client):
    victim_parent = make_parent("nutrition-victim@example.com")
    victim_id = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent("nutrition-attacker@example.com")
    attacker_id = make_athlete(attacker_parent, "Attacker")

    r = client.post(
        "/api/meals/", json=_base_body(attacker_id, calories=1_000_000),
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 422, r.text
    assert _meal_logs_count(victim_id) == 0
    assert _meal_logs_count(attacker_id) == 0


# ─── Existing BOLA behavior on this route must remain unchanged ───────────

def test_log_meal_still_requires_a_session(client):
    parent_id = make_parent("bola-unchanged1@example.com")
    athlete_id = make_athlete(parent_id)
    r = client.post("/api/meals/", json=_base_body(athlete_id, calories=500))
    assert r.status_code == 401


def test_log_meal_still_rejects_unrelated_athlete_token(client):
    victim_parent = make_parent("bola-unchanged2-victim@example.com")
    victim_id = make_athlete(victim_parent, "Victim")
    attacker_parent = make_parent("bola-unchanged2-attacker@example.com")
    attacker_id = make_athlete(attacker_parent, "Attacker")
    r = client.post(
        "/api/meals/", json=_base_body(victim_id, calories=500),
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403
    assert _meal_logs_count(victim_id) == 0
