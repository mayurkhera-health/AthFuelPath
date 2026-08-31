"""
Security Item 7C — POST/DELETE /api/athletes/{id}/windows/{slot}/capture must
stop persisting full-size photo/audio media to disk. api/services/nutrient_resolver.py
never reads window_logs.photo_url/audio_url (queue_nutrient_resolution() only flips
nutrient_status to 'pending'), and today_service.py's response builder only ever reads
wl["thumb_url"] (an in-memory base64 data URI, not a file path) — there is no active
consumer of the full-size files or their stored paths anywhere in the backend. Web
contract (frontend/src/components/today/DailyMission.jsx) — endpoint URL, multipart
fields, response shape — must stay byte-for-byte unchanged.

Item 7C removed _PHOTOS_DIR/_AUDIO_DIR (and the writes to them) from
api/routes/today.py entirely — there is no path left to monkeypatch. The
photo/audio tests below snapshot the real /tmp/athfuelpath_photos and
/tmp/athfuelpath_audio directory LISTINGS (filenames only, never file content —
no historical/real user media is opened or read) before and after the request
and assert no new file appeared. Read-only listing of a real system temp
directory, never a write into it or an inspection of any existing file's bytes.
"""

import io
import os
from pathlib import Path

os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_headers

TODAY = "2026-06-23"
_n = {"i": 0}


def _real_jpeg_bytes() -> bytes:
    """A genuine tiny JPEG — _store_meal_photo() opens it with PIL, so fake bytes
    would hit the bare except and silently return (None, None), masking the RED
    signal (the write-to-disk step, not the thumbnail step, is what we're testing)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), color=(200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def _shared_client_and_conn():
    """Module-scoped: FastAPI's lifespan (api/startup.py's ensure_knowledge_ingested())
    re-ingests + re-attempts embedding the whole knowledge base on every TestClient
    startup when review_status never reaches 'approved' in a test DB — a function-scoped
    TestClient here made every single test in this file redo that (non-critical,
    unrelated to capture) work from scratch. One TestClient for the whole module matches
    real test isolation intent and avoids the redundant work entirely."""
    from api.database import get_conn
    from api.main import app

    keepalive = get_conn()
    # api.database.get_conn() defaults to autocommit=False — a bare SELECT on this
    # shared connection would otherwise leave a transaction open for the rest of the
    # module, holding a lock that deadlocks against today_service.py's
    # _ensure_window_logs_table() (`ALTER TABLE window_logs ADD COLUMN IF NOT EXISTS
    # ...`, run on every capture request via its own short-lived connection).
    keepalive.autocommit = True
    with TestClient(app) as c:
        yield c, keepalive
    keepalive.close()


@pytest.fixture
def client(_shared_client_and_conn):
    c, keepalive = _shared_client_and_conn
    yield c, keepalive


def _athlete(client):
    _n["i"] += 1
    p = client.post("/api/parents/", json={
        "full_name": "P", "email": f"media7c{_n['i']}@example.com", "consent_confirmed": True})
    pid = p.json()["id"]
    a = client.post("/api/athletes/", json={
        "parent_id": pid, "first_name": "A", "age": 14, "gender": "girl",
        "weight_lbs": 110, "height_ft": 5, "height_in": 4,
        "competition_level": "competitive_club"}, headers=auth_headers("parent", parent_id=pid))
    return a.json()["id"], pid


def _window_log_row(conn, athlete_id, slot):
    return conn.execute(
        "SELECT * FROM window_logs WHERE athlete_id = %s AND window_id = %s AND log_date = %s",
        (athlete_id, slot, TODAY),
    ).fetchone()


def _listing(dirpath: Path) -> set:
    return set(p.name for p in dirpath.iterdir()) if dirpath.exists() else set()


# ── PHOTO ──────────────────────────────────────────────────────────────────────

def test_photo_capture_does_not_write_full_image_file(client):
    c, ka = client
    aid, _ = _athlete(c)
    headers = auth_headers("athlete", athlete_id=aid)
    photos_dir = Path("/tmp/athfuelpath_photos")
    before = _listing(photos_dir)

    r = c.post(
        f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
        data={"method": "photo", "log_date": TODAY},
        files={"photo": ("meal.jpg", _real_jpeg_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    after = _listing(photos_dir)
    assert after == before, f"a new file appeared in {photos_dir}: {after - before}"

    row = _window_log_row(ka, aid, "everyday_breakfast")
    assert row["photo_url"] is None, f"photo_url should be NULL, got {row['photo_url']!r}"


def test_photo_capture_preserves_thumbnail_and_method(client):
    c, ka = client
    aid, _ = _athlete(c)
    headers = auth_headers("athlete", athlete_id=aid)

    r = c.post(
        f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
        data={"method": "photo", "log_date": TODAY},
        files={"photo": ("meal.jpg", _real_jpeg_bytes(), "image/jpeg")},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    row = _window_log_row(ka, aid, "everyday_breakfast")
    assert row["method"] == "photo"
    assert row["thumb_url"] is not None
    assert row["thumb_url"].startswith("data:image/jpeg;base64,")
    assert row["nutrient_status"] == "pending"

    # The web UI's mission-complete signal (log.photo_thumb_url on the Today
    # response) still comes through — thumbnail behavior is unaffected.
    today = c.get(f"/api/athletes/{aid}/today", params={"date": TODAY}, headers=headers).json()
    w = next(w for w in today["windows"] if w["slot_name"] == "everyday_breakfast")
    assert w["log"]["photo_thumb_url"] is not None
    assert w["logged"] is True


# ── AUDIO ──────────────────────────────────────────────────────────────────────

def test_voice_capture_does_not_write_audio_file(client):
    c, ka = client
    aid, _ = _athlete(c)
    headers = auth_headers("athlete", athlete_id=aid)
    audio_dir = Path("/tmp/athfuelpath_audio")
    before = _listing(audio_dir)

    r = c.post(
        f"/api/athletes/{aid}/windows/everyday_lunch/capture",
        data={"method": "voice", "log_date": TODAY},
        files={"audio": ("clip.webm", b"fake-but-opaque-audio-bytes", "audio/webm")},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    after = _listing(audio_dir)
    assert after == before, f"a new file appeared in {audio_dir}: {after - before}"

    row = _window_log_row(ka, aid, "everyday_lunch")
    assert row["audio_url"] is None, f"audio_url should be NULL, got {row['audio_url']!r}"
    assert row["method"] == "voice"
    assert row["nutrient_status"] == "pending"


# ── TEXT (must be completely unchanged) ─────────────────────────────────────────

def test_text_capture_unchanged(client):
    c, ka = client
    aid, _ = _athlete(c)
    headers = auth_headers("athlete", athlete_id=aid)

    r = c.post(
        f"/api/athletes/{aid}/windows/everyday_dinner/capture",
        data={"method": "text", "text": "grilled chicken and rice", "log_date": TODAY},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    row = _window_log_row(ka, aid, "everyday_dinner")
    assert row["method"] == "text"
    assert row["text"] == "grilled chicken and rice"
    assert row["photo_url"] is None
    assert row["audio_url"] is None
    assert row["thumb_url"] is None
    assert row["nutrient_status"] == "pending"


# ── UNDO (must be completely unchanged) ─────────────────────────────────────────

def test_undo_removes_row_resets_meal_plan_logged_and_is_idempotent(client):
    c, ka = client
    aid, _ = _athlete(c)
    headers = auth_headers("athlete", athlete_id=aid)

    c.post(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
          data={"method": "text", "text": "x", "log_date": TODAY}, headers=headers)
    assert _window_log_row(ka, aid, "everyday_breakfast") is not None

    d = c.delete(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
                params={"log_date": TODAY}, headers=headers)
    assert d.status_code == 200
    assert _window_log_row(ka, aid, "everyday_breakfast") is None

    # Idempotent — un-confirming an already-unconfirmed window is a no-op, not an error.
    d2 = c.delete(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
                 params={"log_date": TODAY}, headers=headers)
    assert d2.status_code == 200


# ── AUTH / BOLA ──────────────────────────────────────────────────────────────────

def test_capture_anonymous_denied(client):
    c, _ = client
    aid, _ = _athlete(c)
    r = c.post(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
              data={"method": "text", "text": "x", "log_date": TODAY})
    assert r.status_code == 401


def test_capture_unrelated_athlete_denied(client):
    c, _ = client
    aid, _ = _athlete(c)
    other_aid, _ = _athlete(c)
    headers = auth_headers("athlete", athlete_id=other_aid)
    r = c.post(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
              data={"method": "text", "text": "x", "log_date": TODAY}, headers=headers)
    assert r.status_code == 403


def test_capture_owner_succeeds(client):
    c, _ = client
    aid, pid = _athlete(c)
    r = c.post(f"/api/athletes/{aid}/windows/everyday_breakfast/capture",
              data={"method": "text", "text": "x", "log_date": TODAY},
              headers=auth_headers("parent", parent_id=pid))
    assert r.status_code == 200
