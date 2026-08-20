"""Integration tests for the athlete Blueprint route."""

import os
os.environ["DB_PATH"] = ":memory:"

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
    with TestClient(app) as c:
        yield c
    keepalive.close()


_counter = {"n": 0}


def _make_athlete(client, *, age=15, gender="girl"):
    _counter["n"] += 1
    email = f"bp{_counter['n']}@example.com"
    p = client.post(
        "/api/parents/",
        json={"full_name": "P", "email": email, "consent_confirmed": True},
    )
    assert p.status_code == 201, p.text
    parent_id = p.json()["id"]
    a = client.post(
        "/api/athletes/",
        json={
            "parent_id": parent_id, "first_name": "A", "age": age, "gender": gender,
            "weight_lbs": 110, "height_ft": 5, "height_in": 6,
        },
        headers=auth_headers("parent", parent_id=parent_id),
    )
    assert a.status_code == 201, a.text
    return a.json()["id"]


def test_blueprint_get_does_not_500_for_age_ge_14(client):
    """Regression: _computed_calculated must not raise NameError for age>=14."""
    aid = _make_athlete(client, age=15, gender="girl")
    r = client.get(f"/api/athletes/{aid}/blueprint", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    # female + age>=14 → magnesium 360 (the exact branch that referenced is_girl)
    assert body["_calculated"]["magnesium_mg"] == 360


def test_blueprint_get_lazy_generates_when_null(client):
    """A never-generated athlete (background task was killed) self-heals on view."""
    aid = _make_athlete(client, age=13, gender="boy")  # age<14 → isolates from Task 1
    conn = get_conn()
    conn.execute("UPDATE athletes SET blueprint_json=NULL WHERE id=%s", (aid,))
    conn.commit()

    r = client.get(f"/api/athletes/{aid}/blueprint", headers=auth_headers("athlete", athlete_id=aid))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready"
    assert r.json()["blueprint"]["hero"]["headline"]  # real blueprint content

    # Persisted: a follow-up read shows a real blueprint, not NULL / not a sentinel.
    row = get_conn().execute(
        "SELECT blueprint_json FROM athletes WHERE id=%s", (aid,)
    ).fetchone()
    assert row["blueprint_json"]
    assert "__status" not in json.loads(row["blueprint_json"])


def test_create_generates_blueprint_inline_not_via_background(client, monkeypatch):
    """create_athlete must generate inline, not depend on the post-response task
    (which gets killed by Fly machine-stop / deploy)."""
    import api.routes.athletes as ar

    called = {"bg": False}
    monkeypatch.setattr(
        ar, "generate_blueprint_bg",
        lambda *a, **k: called.__setitem__("bg", True),
    )

    aid = _make_athlete(client, age=15, gender="girl")

    assert called["bg"] is False, "create should not schedule the background task"
    row = get_conn().execute(
        "SELECT blueprint_json FROM athletes WHERE id=%s", (aid,)
    ).fetchone()
    assert row["blueprint_json"], "blueprint should be generated inline during create"
    assert "__status" not in json.loads(row["blueprint_json"])
