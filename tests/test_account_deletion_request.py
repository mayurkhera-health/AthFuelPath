"""
DELETE /api/parents/{parent_id} — product decision (2026-07-27): this no
longer deletes anything in-app. The prior automatic cascade delete had a real
bug (it deleted through a column shopping_list_items doesn't have, so it
always 500'd — see the QA audit finding this replaces) and the team wants a
human to handle every account deletion rather than an automated in-app
cascade. The route now records the request and emails the team; the actual
deletion happens manually, out of the app.
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


def _make_family(client, num_athletes=1):
    _counter["n"] += 1
    email = f"deletion-request{_counter['n']}@example.com"
    p = client.post("/api/parents/", json={"full_name": "Jamie Parent", "email": email, "consent_confirmed": True})
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    athlete_ids = []
    for i in range(num_athletes):
        a = client.post("/api/athletes/", json={
            "parent_id": parent_id, "first_name": f"Kid{i}", "age": 14, "gender": "girl",
            "weight_lbs": 110, "height_ft": 5, "height_in": 4,
        })
        assert a.status_code == 201, a.text
        athlete_ids.append(a.json()["id"])
    return parent_id, athlete_ids


def test_request_persists_and_emails_the_team(client):
    parent_id, athlete_ids = _make_family(client, num_athletes=2)
    with patch("api.routes.parents.send_email", return_value=True) as mock_send:
        r = client.delete(
            f"/api/parents/{parent_id}",
            headers=auth_headers("parent", parent_id=parent_id),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] is True
    assert body["email_sent"] is True

    row = get_conn().execute(
        "SELECT parent_id, parent_name, parent_email, athlete_names FROM account_deletion_requests WHERE id = %s",
        (body["id"],),
    ).fetchone()
    assert row["parent_id"] == parent_id
    assert row["parent_name"] == "Jamie Parent"
    assert "Kid0" in row["athlete_names"] and "Kid1" in row["athlete_names"]

    mock_send.assert_called_once()
    subject, body_text, recipients = mock_send.call_args[0][0], mock_send.call_args[0][1], mock_send.call_args[0][2]
    assert recipients == ["purvihshah@gmail.com"]
    assert "Jamie Parent" in subject
    assert "Kid0" in body_text and "Kid1" in body_text


def test_nothing_is_actually_deleted(client):
    """The core of the fix: the parent and athlete rows must still exist
    after the request — deletion happens manually, out of the app."""
    parent_id, athlete_ids = _make_family(client, num_athletes=1)
    with patch("api.routes.parents.send_email", return_value=True):
        r = client.delete(
            f"/api/parents/{parent_id}",
            headers=auth_headers("parent", parent_id=parent_id),
        )
    assert r.status_code == 200, r.text

    conn = get_conn()
    assert conn.execute("SELECT id FROM parents WHERE id = %s", (parent_id,)).fetchone() is not None
    assert conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_ids[0],)).fetchone() is not None


def test_request_persists_even_when_email_fails(client):
    parent_id, _ = _make_family(client)
    with patch("api.routes.parents.send_email", return_value=False):
        r = client.delete(
            f"/api/parents/{parent_id}",
            headers=auth_headers("parent", parent_id=parent_id),
        )
    assert r.status_code == 200, r.text
    assert r.json()["email_sent"] is False
    row = get_conn().execute(
        "SELECT id FROM account_deletion_requests WHERE parent_id = %s", (parent_id,)
    ).fetchone()
    assert row is not None, "request must be saved even if the email send fails"


def test_no_athletes_on_file_still_works(client):
    parent_id, _ = _make_family(client, num_athletes=0)
    with patch("api.routes.parents.send_email", return_value=True) as mock_send:
        r = client.delete(
            f"/api/parents/{parent_id}",
            headers=auth_headers("parent", parent_id=parent_id),
        )
    assert r.status_code == 200, r.text
    body_text = mock_send.call_args[0][1]
    assert "no athletes on file" in body_text
