"""Integration tests for the Fuel IQ Daily Challenge API surface
(api/routes/fueliq_daily_challenge.py)."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers


def _wipe(conn):
    conn.commit()
    tables = [r["table_name"] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name != 'schema_migrations'"
    ).fetchall()]
    if tables:
        conn.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
    conn.commit()


@pytest.fixture
def client():
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    _wipe(keepalive)  # shared in-memory DB persists across tests — start clean
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client):
    _counter["n"] += 1
    email = f"dailychallenge{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6, "competition_level": "Recreational",
    })
    assert a.status_code == 201, a.text
    return a.json()["id"]


def _seed_challenge(conn, challenge_date, title="T1", verdict="myth"):
    conn.execute(
        "INSERT INTO fueliq_daily_challenges "
        "(challenge_date, title, hook, verdict, science_text, points) "
        "VALUES (%s, %s, 'hook', %s, 'science', 10)",
        (challenge_date, title, verdict),
    )
    conn.commit()


def test_daily_challenge_returns_disabled_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "false")
    aid = _make_athlete(client)
    r = client.get(f"/api/athletes/{aid}/daily-challenge", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_daily_challenge_get_returns_null_challenge_when_nothing_scheduled(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    r = client.get(f"/api/athletes/{aid}/daily-challenge", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["challenge"] is None
    assert body["streak"] == {"current": 0, "best": 0}
    assert body["total_completed"] == 0


def test_daily_challenge_get_hides_verdict_before_answering(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    from api.services.fueliq_daily_challenge_service import _today_pst
    aid = _make_athlete(client)
    conn = get_conn()
    _seed_challenge(conn, _today_pst().isoformat())
    conn.close()

    r = client.get(f"/api/athletes/{aid}/daily-challenge", headers=auth_headers("athlete", athlete_id=aid))
    challenge = r.json()["challenge"]
    assert challenge["answered"] is False
    assert "verdict" not in challenge
    assert "science_text" not in challenge


def test_daily_challenge_verdict_flow_end_to_end(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    from api.services.fueliq_daily_challenge_service import _today_pst
    aid = _make_athlete(client)
    conn = get_conn()
    _seed_challenge(conn, _today_pst().isoformat(), verdict="myth")
    conn.close()

    headers = auth_headers("athlete", athlete_id=aid)
    r = client.post(f"/api/athletes/{aid}/daily-challenge/verdict", json={"guess": "myth"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["correct"] is True
    assert body["points_earned"] == 10
    assert body["streak"] == {"current": 1, "best": 1}

    again = client.get(f"/api/athletes/{aid}/daily-challenge", headers=headers).json()
    assert again["challenge"]["answered"] is True
    assert again["challenge"]["correct"] is True
    assert again["total_completed"] == 1


def test_daily_challenge_verdict_404_when_nothing_scheduled(client, monkeypatch):
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    r = client.post(
        f"/api/athletes/{aid}/daily-challenge/verdict", json={"guess": "myth"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 404


def test_daily_challenge_verdict_rejects_invalid_guess(client, monkeypatch):
    """Regression: guess used to be a bare str — anything other than
    "real"/"myth" never matched _VALID_VERDICTS and was silently recorded as
    wrong instead of being rejected as malformed input."""
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    aid = _make_athlete(client)
    r = client.post(
        f"/api/athletes/{aid}/daily-challenge/verdict", json={"guess": "definitely maybe"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 422


def test_daily_challenge_verdict_does_not_appear_in_fueliq_hub_score(client, monkeypatch):
    """The whole point of the separation — completing the Daily Challenge
    must never move the athlete's Fuel IQ score/rank."""
    monkeypatch.setenv("FUELIQ_ENABLED", "true")
    from api.services.fueliq_daily_challenge_service import _today_pst
    aid = _make_athlete(client)
    conn = get_conn()
    _seed_challenge(conn, _today_pst().isoformat())
    conn.close()

    headers = auth_headers("athlete", athlete_id=aid)
    before = client.get(f"/api/athletes/{aid}/hub", headers=headers).json()
    client.post(f"/api/athletes/{aid}/daily-challenge/verdict", json={"guess": "myth"}, headers=headers)
    after = client.get(f"/api/athletes/{aid}/hub", headers=headers).json()
    assert after["score"] == before["score"]
