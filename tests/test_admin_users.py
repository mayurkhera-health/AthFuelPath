"""Admin Users: list/search/filter/pagination, detail, edit, cascade delete, audit."""

import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth
from api.main import app

PASSWORD = "s3cret-admin"


def _wipe(conn):
    # The shared DB persists across tests; clear every table for a clean
    # slate. TRUNCATE ... CASCADE plays the same role FK-enforcement-off did
    # for SQLite: it clears every table regardless of FK reference order.
    conn.commit()
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "AND table_name != 'schema_migrations'"
    ).fetchall()
    names = [r["table_name"] for r in rows]
    if names:
        conn.execute("TRUNCATE TABLE " + ", ".join(names) + " RESTART IDENTITY CASCADE")
    conn.commit()


def _iso(days_ago=0):
    return (datetime.utcnow() - timedelta(days=days_ago)).isoformat()


def _add_parent(conn, name, email, days_ago=10):
    cur = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed, created_at) "
        "VALUES (%s, %s, %s, TRUE, %s) RETURNING id",
        (name, email, _iso(days_ago), _iso(days_ago)),
    )
    return cur.fetchone()["id"]


def _add_athlete(conn, parent_id, first_name, byga=None, playmetrics=None):
    cur = conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, "
        "position, competition_level, byga_ics_url, playmetrics_ics_url) "
        "VALUES (%s, %s, 12, 'M', 90.0, 5, 2.0, 'Midfield', 'Competitive', %s, %s) RETURNING id",
        (parent_id, first_name, byga, playmetrics),
    )
    return cur.fetchone()["id"]


def _add_event(conn, athlete_id, source="manual", synced_days_ago=None, upcoming=True):
    synced_at = _iso(synced_days_ago) if synced_days_ago is not None else None
    date = (datetime.utcnow() + timedelta(days=3 if upcoming else -3)).date().isoformat()
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, source, synced_at) "
        "VALUES (%s, 'Match', 'game', %s, %s, %s)",
        (athlete_id, date, source, synced_at),
    )


@pytest.fixture
def ctx(monkeypatch):
    keepalive = get_conn()
    init_db()
    run_all()
    _wipe(keepalive)  # shared in-memory DB persists across tests — start clean
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key")
    admin_auth._failed_logins.clear()

    ids = {}
    # Sarah: 2 athletes, one BYGA-connected with a fresh synced event → healthy.
    ids["sarah"] = _add_parent(keepalive, "Sarah Smith", "sarah@x.com", days_ago=20)
    ids["ava"] = _add_athlete(keepalive, ids["sarah"], "Ava", byga="https://byga/ava.ics")
    ids["ben"] = _add_athlete(keepalive, ids["sarah"], "Ben")
    _add_event(keepalive, ids["ava"], source="byga", synced_days_ago=0)
    _add_event(keepalive, ids["ava"], source="manual")
    keepalive.execute("INSERT INTO meal_plans (athlete_id, plan_date, slot_name, recipe_name) "
                      "VALUES (%s, sqlite_today(), 'lunch', 'Pasta')", (ids["ava"],))
    keepalive.execute("INSERT INTO meal_logs (athlete_id, log_method, description) VALUES (%s, 'text', 'eggs')",
                      (ids["ava"],))
    keepalive.execute("INSERT INTO water_logs (athlete_id, log_date, cups) VALUES (%s, sqlite_today(), 4)",
                      (ids["ava"],))
    keepalive.execute("INSERT INTO feature_requests (athlete_id, email, suggestion) VALUES (%s, 'sarah@x.com', 'Dark mode')",
                      (ids["ava"],))

    # Mike: 1 athlete, no calendar, signed up long ago → never_connected chip.
    ids["mike"] = _add_parent(keepalive, "Mike Jones", "mike@y.com", days_ago=15)
    ids["leo"] = _add_athlete(keepalive, ids["mike"], "Leo")

    # Nora: no athletes → no_athletes chip.
    ids["nora"] = _add_parent(keepalive, "Nora NoKids", "nora@z.com", days_ago=1)

    # Stan: BYGA connected but last sync 5 days ago → sync_stale chip.
    ids["stan"] = _add_parent(keepalive, "Stan Stale", "stan@q.com", days_ago=10)
    ids["sky"] = _add_athlete(keepalive, ids["stan"], "Sky", byga="https://byga/sky.ics")
    _add_event(keepalive, ids["sky"], source="byga", synced_days_ago=5)
    keepalive.commit()

    token = None
    with TestClient(app) as c:
        r = c.post("/api/admin/login", json={"password": PASSWORD})
        token = r.json()["token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c, ids, keepalive
    keepalive.close()


def test_list_returns_all_families_with_nested_athletes(ctx):
    c, ids, _ = ctx
    r = c.get("/api/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    sarah = next(f for f in body["items"] if f["id"] == ids["sarah"])
    assert sarah["athlete_count"] == 2
    assert {a["first_name"] for a in sarah["athletes"]} == {"Ava", "Ben"}


def test_search_matches_parent_and_athlete_names(ctx):
    c, ids, _ = ctx
    # Athlete-name search finds the parent family.
    r = c.get("/api/admin/users", params={"search": "Leo"})
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["id"] == ids["mike"]
    # Parent-email search.
    r2 = c.get("/api/admin/users", params={"search": "sarah@x"})
    assert [f["id"] for f in r2.json()["items"]] == [ids["sarah"]]


def test_filter_calendar_none_and_has_athletes(ctx):
    c, ids, _ = ctx
    none_families = {f["id"] for f in c.get("/api/admin/users", params={"calendar": "none"}).json()["items"]}
    assert ids["mike"] in none_families and ids["nora"] in none_families
    assert ids["sarah"] not in none_families  # Sarah has a BYGA athlete
    no_ath = c.get("/api/admin/users", params={"has_athletes": "no"}).json()["items"]
    assert [f["id"] for f in no_ath] == [ids["nora"]]


def test_at_risk_chips(ctx):
    c, ids, _ = ctx
    by_id = {f["id"]: f for f in c.get("/api/admin/users").json()["items"]}
    assert "no_athletes" in by_id[ids["nora"]]["chips"]
    assert "never_connected" in by_id[ids["mike"]]["chips"]
    assert "sync_stale" in by_id[ids["stan"]]["chips"]
    assert by_id[ids["sarah"]]["chips"] == []


def test_pagination(ctx):
    c, _, _ = ctx
    r = c.get("/api/admin/users", params={"limit": 2, "page": 1})
    body = r.json()
    assert len(body["items"]) == 2 and body["total"] == 4


def test_family_detail_has_event_stats_and_activity(ctx):
    c, ids, _ = ctx
    d = c.get(f"/api/admin/users/{ids['sarah']}").json()
    assert d["parent"]["email"] == "sarah@x.com"
    ava = next(a for a in d["athletes"] if a["id"] == ids["ava"])
    assert ava["event_stats"]["total"] == 2
    assert ava["event_stats"]["by_source"] == {"byga": 1, "manual": 1}
    assert ava["last_synced_at"] is not None
    assert any("Dark mode" in i["suggestion"] for i in d["activity"]["feature_ideas"])


def test_update_parent_validates_email_and_audits(ctx):
    c, ids, ka = ctx
    bad = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "not-an-email"})
    assert bad.status_code == 400
    ok = c.put(f"/api/admin/parents/{ids['mike']}", json={"full_name": "Michael Jones"})
    assert ok.status_code == 200 and ok.json()["full_name"] == "Michael Jones"
    row = ka.execute("SELECT COUNT(*) AS count FROM admin_audit_log WHERE action='update_parent' AND target_id=%s",
                     (ids["mike"],)).fetchone()
    assert row["count"] == 1


def test_update_parent_duplicate_email_409(ctx):
    c, ids, _ = ctx
    r = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "sarah@x.com"})
    assert r.status_code == 409


def test_update_athlete(ctx):
    c, ids, _ = ctx
    r = c.put(f"/api/admin/athletes/{ids['leo']}", json={"position": "Goalkeeper", "age": 13})
    assert r.status_code == 200
    assert r.json()["position"] == "Goalkeeper" and r.json()["age"] == 13


def test_delete_athlete_preview_and_cascade(ctx):
    c, ids, ka = ctx
    preview = c.get(f"/api/admin/athletes/{ids['ava']}/delete-preview").json()["counts"]
    assert preview["events"] == 2
    assert preview["meal_plans"] == 1
    assert preview["meal_logs"] == 1
    assert preview["water_logs"] == 1
    assert preview["feature_requests"] == 1

    r = c.request("DELETE", f"/api/admin/athletes/{ids['ava']}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    # Every child row is gone.
    for table in ("events", "meal_plans", "meal_logs", "water_logs", "feature_requests"):
        n = ka.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE athlete_id=%s", (ids["ava"],)).fetchone()["count"]
        assert n == 0, f"{table} not cascaded"
    assert ka.execute("SELECT COUNT(*) AS count FROM athletes WHERE id=%s", (ids["ava"],)).fetchone()["count"] == 0
    # Audit row written.
    assert ka.execute("SELECT COUNT(*) AS count FROM admin_audit_log WHERE action='delete_athlete' AND target_id=%s",
                      (ids["ava"],)).fetchone()["count"] == 1


def test_calendar_badge_distinguishes_import_manual_empty(ctx):
    c, ids, ka = ctx
    # Ben (no sync URL): hand-entered event (uid NULL) -> "manual"
    ka.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date) "
               "VALUES (%s, 'M', 'game', sqlite_today())", (ids["ben"],))
    # Leo (no sync URL): imported .ics event (uid set) -> "imported"
    ka.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, uid) "
               "VALUES (%s, 'M', 'game', sqlite_today(), 'ics-uid-1')", (ids["leo"],))
    ka.commit()
    items = {f["id"]: f for f in c.get("/api/admin/users").json()["items"]}

    ava = next(a for a in items[ids["sarah"]]["athletes"] if a["id"] == ids["ava"])
    ben = next(a for a in items[ids["sarah"]]["athletes"] if a["id"] == ids["ben"])
    leo = next(a for a in items[ids["mike"]]["athletes"] if a["id"] == ids["leo"])
    assert ava["calendar"] == "byga"                       # recurring auto-sync
    assert ben["calendar"] == "manual" and ben["event_count"] == 1
    assert leo["calendar"] == "imported" and leo["imported_count"] == 1

    # Mike uploaded a calendar file (Leo's import) -> no longer "never connected"
    assert "never_connected" not in items[ids["mike"]]["chips"]


def test_empty_schedule_is_none_status(ctx):
    c, ids, _ = ctx
    # Nora has no athletes; check an athlete with zero events reads "none".
    items = {f["id"]: f for f in c.get("/api/admin/users").json()["items"]}
    # Ben currently has no events in the base fixture -> "none".
    ben = next(a for a in items[ids["sarah"]]["athletes"] if a["id"] == ids["ben"])
    assert ben["calendar"] == "none"


def test_hard_deleted_parents_excluded_from_list(ctx):
    # Simulate the prod schema: the old AthFuelPath-Admin soft-delete adds
    # parents.account_status and anonymizes rows to 'hard_deleted'.
    c, ids, ka = ctx
    existing_cols = {
        r["column_name"] for r in ka.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'parents'"
        ).fetchall()
    }
    if "account_status" not in existing_cols:
        ka.execute("ALTER TABLE parents ADD COLUMN account_status TEXT")  # idempotent across shared-DB tests
    ka.execute("UPDATE parents SET account_status = 'hard_deleted' WHERE id = %s", (ids["mike"],))
    ka.commit()
    body = c.get("/api/admin/users").json()
    returned = {f["id"] for f in body["items"]}
    assert ids["mike"] not in returned
    assert ids["sarah"] in returned          # active rows still shown
    assert body["total"] == 3                # was 4


def test_delete_parent_requires_confirm(ctx):
    c, ids, _ = ctx
    r = c.request("DELETE", f"/api/admin/parents/{ids['sarah']}", json={"confirm": "nope"})
    assert r.status_code == 400


def test_delete_parent_cascades_all_athletes(ctx):
    c, ids, ka = ctx
    preview = c.get(f"/api/admin/parents/{ids['sarah']}/delete-preview").json()["counts"]
    assert preview["athletes"] == 2
    assert preview["events"] == 2

    r = c.request("DELETE", f"/api/admin/parents/{ids['sarah']}", json={"confirm": "DELETE"})
    assert r.status_code == 200
    assert ka.execute("SELECT COUNT(*) AS count FROM parents WHERE id=%s", (ids["sarah"],)).fetchone()["count"] == 0
    assert ka.execute("SELECT COUNT(*) AS count FROM athletes WHERE parent_id=%s", (ids["sarah"],)).fetchone()["count"] == 0
    assert ka.execute("SELECT COUNT(*) AS count FROM events WHERE athlete_id IN (%s, %s)",
                      (ids["ava"], ids["ben"])).fetchone()["count"] == 0
    assert ka.execute("SELECT COUNT(*) AS count FROM admin_audit_log WHERE action='delete_parent' AND target_id=%s",
                      (ids["sarah"],)).fetchone()["count"] == 1
