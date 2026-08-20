"""Integration tests for the feature-request (feedback) route."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
from tests.conftest import auth_headers
import api.routes.feedback as feedback


@pytest.fixture
def client(monkeypatch):
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    # Capture email attempts instead of sending real SMTP.
    sent = []
    monkeypatch.setattr(
        feedback, "send_email",
        lambda subject, body, to, attachment_path=None, html=None, bcc=None: sent.append(
            {"subject": subject, "body": body, "to": to, "html": html, "bcc": bcc}
        ) or True,
    )
    with TestClient(app) as c:
        c.sent = sent
        yield c
    keepalive.close()


_n = {"i": 0}


def _make_parent_athlete(client):
    _n["i"] += 1
    email = f"feat{_n['i']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "P", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": parent_id, "first_name": "A", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 6, "competition_level": "Recreational",
    }, headers=auth_headers("parent", parent_id=parent_id))
    assert a.status_code == 201, a.text
    return email, a.json()["id"]


def test_confirmation_uses_account_email_from_athlete_id(client):
    # A logged-in feature idea: the client sends athlete_id but no payload email.
    # The confirmation must go to the account holder's email, resolved server-side.
    email, aid = _make_parent_athlete(client)
    r = client.post("/api/feedback/feature-request", json={
        "suggestion": "Add a water-logging widget to the home screen",
        "athlete_id": aid,
        # deliberately NO email in the payload
    })
    assert r.status_code == 200, r.text
    # two sends: team notification + confirmation to the account holder
    assert len(client.sent) == 2
    confirm = client.sent[1]
    assert confirm["to"] == [email]
    assert confirm["bcc"] == ["mayurkhera@gmail.com"]
    assert confirm["html"] is not None  # HTML confirmation


def test_no_identifier_sends_only_team_email(client):
    # No athlete_id and no email -> only the internal team notification.
    r = client.post("/api/feedback/feature-request", json={
        "suggestion": "A suggestion with no account info attached",
    })
    assert r.status_code == 200, r.text
    assert len(client.sent) == 1  # team only, no confirmation
