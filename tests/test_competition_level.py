"""
Tests for the competition_level canonical model (api/services/competition_level.py)
and every write/read path that depends on it.

Root cause this guards against: a 2026-07-22 bulk TeamCoach roster-setup
operation wrote a club name ("Bay Area Surf") into 12 athletes'
competition_level via the unvalidated admin PUT /admin/athletes/{id}
endpoint. Nothing validated the field at write time, so a free-text club
name silently reached the DB and every downstream keyword match
(derive_intensity, derive_sweat_profile) fell through to its low/baseline
default — a live, product-wide data-quality bug, not just an event-
duplicate artifact.

Covers:
  - validate_competition_level() / classify_competition_level() unit tests
  - POST /api/athletes/ (AthleteCreate) write validation
  - POST /api/onboarding/complete (OnboardingAthlete) write validation
  - PUT /admin/athletes/{id} write validation — see test_admin_users.py for
    the admin-route-level tests (uses the same shared ctx fixture there)
  - derive_intensity() classification, including the loud-warning fallback
  - derive_sweat_profile() using the SAME classifier (hydration unification)
"""

import logging
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from api.services import nutrition_calc as nc
from api.services import weather
from api.services.competition_level import validate_competition_level, classify_competition_level
from tests.conftest import auth_headers


# ── validate_competition_level (write-time gate) ─────────────────────────────

@pytest.mark.parametrize("value", ["recreational", "competitive_club", "elite_club"])
def test_validate_accepts_each_canonical_value(value):
    assert validate_competition_level(value) == value


def test_validate_accepts_none_omitted_field():
    assert validate_competition_level(None) is None


def test_validate_rejects_club_name():
    with pytest.raises(ValueError):
        validate_competition_level("Bay Area Surf")


@pytest.mark.parametrize("value", [
    "Elite Club", "elite", "competitive", "Recreational", "", "made up nonsense",
    "Soccer Club", "Competitive Team",
])
def test_validate_rejects_legacy_and_arbitrary_strings(value):
    """No keyword inference anywhere, at write time or read time (MVP stance) —
    a legacy human-readable label is rejected exactly like a club/team name.
    Only the exact canonical string is ever accepted."""
    with pytest.raises(ValueError):
        validate_competition_level(value)


# ── classify_competition_level (read-time, STRICT exact match only) ─────────
# MVP stance: no substring/keyword inference anywhere, at write time or read
# time. A legacy display-style label is invalid data, exactly like a club
# name — it is never classified as a tier, only logged and given the same
# safe neutral (None) fallback as any other non-canonical value.

@pytest.mark.parametrize("value", ["recreational", "competitive_club", "elite_club"])
def test_classify_returns_each_canonical_value_unchanged(value):
    assert classify_competition_level(value) == value


def test_classify_returns_none_for_empty_or_missing():
    assert classify_competition_level(None) is None
    assert classify_competition_level("") is None


@pytest.mark.parametrize("value", [
    "Bay Area Surf", "Soccer Club", "Competitive Team", "Elite Club", "Elite",
    "Competitive Club", "Club", "Recreational", "made up nonsense",
])
def test_classify_rejects_everything_not_exactly_canonical(value, caplog):
    """No keyword inference: a legacy label is treated identically to a
    club name — neither is a recognized tier, both fall back to None and
    both log a warning."""
    with caplog.at_level(logging.WARNING):
        result = classify_competition_level(value)
    assert result is None
    assert any(value in r.message for r in caplog.records)


def test_classify_empty_value_does_not_warn(caplog):
    """A brand-new athlete with no competition_level set yet is not an error."""
    with caplog.at_level(logging.WARNING):
        classify_competition_level(None)
    assert not any("competition_level" in r.message for r in caplog.records)


# ── derive_intensity: valid tiers derive the intended intensity ─────────────

@pytest.mark.parametrize("level,expected", [
    ("recreational", "low"),
    ("competitive_club", "medium"),
    ("elite_club", "high"),
])
def test_derive_intensity_canonical_values(level, expected):
    assert nc.derive_intensity("game", level) == expected


def test_derive_intensity_club_name_falls_back_to_low_with_warning(caplog):
    """The exact production incident: a club name must not silently become
    anything other than the documented low-fallback, and must be logged."""
    with caplog.at_level(logging.WARNING):
        result = nc.derive_intensity("practice", "Bay Area Surf")
    assert result == "low"
    assert any("Bay Area Surf" in r.message for r in caplog.records)


# ── hydration uses the same canonical interpretation as intensity ───────────

def test_hydration_and_intensity_agree_on_canonical_values():
    for level, elevated in (("elite_club", True), ("competitive_club", True), ("recreational", False)):
        athlete = {"date_of_birth": None, "age": 14, "gender": "boy", "competition_level": level}
        profile = weather.derive_sweat_profile(athlete)
        base_athlete = {**athlete, "competition_level": None}
        base_profile = weather.derive_sweat_profile(base_athlete)
        if elevated:
            assert profile != base_profile or profile == "very heavy", \
                f"{level} should elevate the sweat profile relative to no tier"


def test_hydration_club_name_does_not_elevate_profile(caplog):
    """Before this fix: 'elite'/'competitive' substring-matched independently
    in weather.py — now it goes through the same classifier as intensity, so
    a club name gets the SAME safe non-elevated fallback, not a silent guess."""
    athlete_club_name = {"date_of_birth": None, "age": 14, "gender": "boy", "competition_level": "Bay Area Surf"}
    athlete_none = {"date_of_birth": None, "age": 14, "gender": "boy", "competition_level": None}
    with caplog.at_level(logging.WARNING):
        result = weather.derive_sweat_profile(athlete_club_name)
    baseline = weather.derive_sweat_profile(athlete_none)
    assert result == baseline, "an unclassifiable value must not silently elevate hydration guidance"
    assert any("Bay Area Surf" in r.message for r in caplog.records)


# ── route-level write validation: POST /api/athletes/ + onboarding ──────────

@pytest.fixture
def client():
    keepalive = get_conn()
    init_db()
    run_all()
    for tbl in ("events", "athletes", "parents"):
        keepalive.execute(f"DELETE FROM {tbl}")
    keepalive.commit()
    with TestClient(app) as c:
        yield c
    keepalive.close()


def _make_parent(conn):
    cur = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        ("Pat Parent", "pat-cl@example.com", datetime.utcnow().isoformat(), True),
    )
    conn.commit()
    return cur.fetchone()["id"]


def _athlete_body(parent_id, **overrides):
    base = {
        "parent_id": parent_id, "first_name": "Nora", "age": 15, "gender": "Girl",
        "weight_lbs": 115, "height_ft": 5, "height_in": 5,
    }
    base.update(overrides)
    return base


def _onboarding_body(**athlete_overrides):
    base = {
        "parent": {"full_name": "Pat Parent", "email": "ob-cl@example.com", "consent_confirmed": True},
        "athlete": {
            "first_name": "Nora", "age": 15, "gender": "Girl",
            "weight_lbs": 115, "height_ft": 5, "height_in": 5,
        },
    }
    base["athlete"].update(athlete_overrides)
    return base


class TestCreateAthleteCompetitionLevel:
    def test_accepts_canonical_value(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()
        r = client.post("/api/athletes/", json=_athlete_body(pid, competition_level="competitive_club"),
                         headers=auth_headers("parent", parent_id=pid))
        assert r.status_code == 201, r.text
        assert r.json()["competition_level"] == "competitive_club"

    def test_rejects_club_name(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()
        r = client.post("/api/athletes/", json=_athlete_body(pid, competition_level="Bay Area Surf"),
                         headers=auth_headers("parent", parent_id=pid))
        assert r.status_code == 422, r.text

    def test_omitted_stays_valid(self, client):
        conn = get_conn()
        pid = _make_parent(conn)
        conn.close()
        r = client.post("/api/athletes/", json=_athlete_body(pid),
                         headers=auth_headers("parent", parent_id=pid))
        assert r.status_code == 201, r.text
        assert r.json()["competition_level"] is None


class TestOnboardingCompetitionLevel:
    def test_accepts_canonical_value(self, client):
        r = client.post("/api/onboarding/complete", json=_onboarding_body(competition_level="recreational"))
        assert r.status_code == 201, r.text
        assert r.json()["athlete"]["competition_level"] == "recreational"

    def test_rejects_club_name(self, client):
        r = client.post("/api/onboarding/complete", json=_onboarding_body(competition_level="Bay Area Surf"))
        assert r.status_code == 422, r.text

    def test_omitted_stays_valid(self, client):
        r = client.post("/api/onboarding/complete", json=_onboarding_body())
        assert r.status_code == 201, r.text
        assert r.json()["athlete"]["competition_level"] is None
