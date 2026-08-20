"""
Integration tests for POST /api/coach/dietitian-booking.

Previously the 'Talk to a Dietitian' request only ever reached on-device
AsyncStorage (app/(app)/coach/dietitian.tsx) — no backend endpoint existed,
so no dietitian ever saw the request despite the in-app "Request received!"
confirmation screen. This route persists the booking and emails the
dietitian (best-effort — persistence never depends on email success).
"""
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from unittest.mock import patch
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


def _make_athlete(client, first_name="Jordan"):
    _counter["n"] += 1
    email = f"dietitian-booking{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": first_name, "age": 15, "gender": "boy",
        "weight_lbs": 130, "height_ft": 5, "height_in": 8,
    }, headers=auth_headers("parent", parent_id=parent_id))
    assert a.status_code == 201, a.text
    return a.json()["id"]


def test_booking_persists_and_emails_the_dietitian(client):
    aid = _make_athlete(client)
    with patch("api.routes.coach.send_email", return_value=True) as mock_send:
        r = client.post(
            "/api/coach/dietitian-booking",
            json={
                "athlete_id": aid, "session_type": "60min",
                "about_athlete": "Jordan is 15, plays midfield, trains 4x/week.",
                "reason": "Pre-game meal timing.",
            },
            headers=auth_headers("athlete", athlete_id=aid),
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["email_sent"] is True

    row = get_conn().execute(
        "SELECT athlete_id, session_type, about_athlete, reason FROM dietitian_bookings WHERE id = %s",
        (body["id"],),
    ).fetchone()
    assert row["athlete_id"] == aid
    assert row["session_type"] == "60min"
    assert row["about_athlete"] == "Jordan is 15, plays midfield, trains 4x/week."
    assert row["reason"] == "Pre-game meal timing."

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    subject, body_text, recipients = call_args[0][0], call_args[0][1], call_args[0][2]
    assert recipients == ["purvihshah@gmail.com"]
    assert "Jordan" in subject
    assert "Jordan is 15, plays midfield" in body_text
    assert "Pre-game meal timing." in body_text


def test_booking_persists_even_when_email_fails(client):
    """Persistence must never depend on email success — this is the exact
    bug being fixed: the request must actually reach durable storage."""
    aid = _make_athlete(client)
    with patch("api.routes.coach.send_email", return_value=False):
        r = client.post(
            "/api/coach/dietitian-booking",
            json={"athlete_id": aid, "session_type": "30min", "about_athlete": "Quick check-in needed."},
            headers=auth_headers("athlete", athlete_id=aid),
        )
    assert r.status_code == 201, r.text
    assert r.json()["email_sent"] is False

    row = get_conn().execute(
        "SELECT id FROM dietitian_bookings WHERE athlete_id = %s", (aid,)
    ).fetchone()
    assert row is not None, "booking must be saved even if the email send fails"


def test_missing_athlete_context_rejected(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/coach/dietitian-booking",
        json={"athlete_id": aid, "session_type": "30min", "about_athlete": "hi"},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 400, r.text


def test_invalid_session_type_rejected(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/coach/dietitian-booking",
        json={"athlete_id": aid, "session_type": "bogus", "about_athlete": "Plenty of detail here."},
        headers=auth_headers("athlete", athlete_id=aid),
    )
    assert r.status_code == 400, r.text


def test_no_session_token_rejected(client):
    aid = _make_athlete(client)
    r = client.post(
        "/api/coach/dietitian-booking",
        json={"athlete_id": aid, "session_type": "30min", "about_athlete": "Plenty of detail here."},
    )
    assert r.status_code == 401, r.text


def test_wrong_owner_rejected(client):
    victim_id = _make_athlete(client, "Victim")
    attacker_id = _make_athlete(client, "Attacker")
    r = client.post(
        "/api/coach/dietitian-booking",
        json={"athlete_id": victim_id, "session_type": "30min", "about_athlete": "Plenty of detail here."},
        headers=auth_headers("athlete", athlete_id=attacker_id),
    )
    assert r.status_code == 403, r.text
