"""Admin Users: list/search/filter/pagination, detail, edit, cascade delete, audit."""

import os
os.environ["DB_PATH"] = ":memory:"

import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch

import psycopg
import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth
from api.services.identity_resolver import resolve_identity, NoExistingAccount
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


# ── Admin parent-email edit keeps auth_identities in sync (auth v2.1 Phase 6) ─
# Migration 004 (db/postgres/004_phase6_provider_auth.sql) adds
# UNIQUE(provider, parent_id) to auth_identities. Before this corrective fix,
# an admin email edit updated parents.email but left that parent's
# provider='email' auth_identities row's provider_subject pointing at the OLD
# email -- so the parent's NEXT ordinary login (resolve_identity() auto-link,
# see api/services/identity_resolver.py) would try to INSERT a second
# provider='email' row for the same parent and get rejected by the new
# constraint, breaking login with an unrelated-looking 409. These tests use
# the same `ctx` fixture as the rest of this file; that fixture's parents are
# inserted directly via SQL (no login has ever happened), so unlike
# production's Phase-5-backfilled parents they start with ZERO
# auth_identities rows -- _add_email_identity() below seeds one to simulate
# an already-backfilled/already-logged-in parent where relevant.

def _add_email_identity(conn, parent_id=None, athlete_id=None, email=None):
    conn.execute(
        "INSERT INTO auth_identities (provider, provider_subject, parent_id, athlete_id, email, email_verified) "
        "VALUES ('email', %s, %s, %s, %s, TRUE)",
        (email, parent_id, athlete_id, email),
    )
    conn.commit()


def _count_email_identities(conn, parent_id):
    return conn.execute(
        "SELECT COUNT(*) AS count FROM auth_identities WHERE provider = 'email' AND parent_id = %s",
        (parent_id,),
    ).fetchone()["count"]


def _insert_otp_row(conn, email, code):
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    conn.execute(
        "INSERT INTO otp_codes (email, code_hash, expires_at, attempts, used) VALUES (%s, %s, %s, 0, 0)",
        (email.lower(), code_hash, expires_at),
    )
    conn.commit()


def test_update_parent_email_syncs_auth_identity_atomically(ctx):
    """Requirement 1 + 6: both parents.email and the provider='email' identity's
    provider_subject update together, and no second identity row appears."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")
    assert _count_email_identities(ka, ids["mike"]) == 1

    r = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "mike-new@y.com"})
    assert r.status_code == 200
    assert r.json()["email"] == "mike-new@y.com"

    parent_row = ka.execute("SELECT email FROM parents WHERE id = %s", (ids["mike"],)).fetchone()
    assert parent_row["email"] == "mike-new@y.com"

    identity = ka.execute(
        "SELECT provider_subject, email FROM auth_identities WHERE provider = 'email' AND parent_id = %s",
        (ids["mike"],),
    ).fetchone()
    assert identity["provider_subject"] == "mike-new@y.com"
    assert identity["email"] == "mike-new@y.com"
    assert _count_email_identities(ka, ids["mike"]) == 1  # still exactly one


def test_update_parent_email_old_email_no_longer_resolves(ctx):
    """Requirement 2: resolving by the OLD email no longer finds this parent."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")
    r = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "mike-new@y.com"})
    assert r.status_code == 200

    with pytest.raises(NoExistingAccount):
        resolve_identity(
            provider="email", provider_subject="mike@y.com",
            email="mike@y.com", email_verified=True,
        )


def test_update_parent_email_new_email_resolves_to_same_parent(ctx):
    """Requirement 3 (resolver level): a lookup by the NEW email resolves to
    the same parent_id."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")
    c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "mike-new@y.com"})

    result = resolve_identity(
        provider="email", provider_subject="mike-new@y.com",
        email="mike-new@y.com", email_verified=True,
    )
    assert result.role == "parent"
    assert result.parent_id == ids["mike"]


def test_update_parent_email_new_login_end_to_end_via_otp_verify(ctx):
    """Requirement 3 (end-to-end): a real /api/auth/email/verify login with the
    NEW email, after the admin edit, resolves to the same parent -- through
    the actual OTP verify flow, not just the resolver."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")
    c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "mike-new@y.com"})

    _insert_otp_row(ka, "mike-new@y.com", "123456")
    r = c.post("/api/auth/email/verify", json={"email": "mike-new@y.com", "code": "123456"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "parent"
    assert body["parent"]["id"] == ids["mike"]
    assert "session_token" in body


def test_update_parent_email_cross_owner_collision_fails_closed(ctx):
    """Requirement 4: colliding with a DIFFERENT parent's email identity fails
    the whole edit closed -- no partial state for either parent."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")
    _add_email_identity(ka, parent_id=ids["sarah"], email="sarah@x.com")

    r = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "sarah@x.com"})
    assert r.status_code == 409

    mike_row = ka.execute("SELECT email FROM parents WHERE id = %s", (ids["mike"],)).fetchone()
    sarah_row = ka.execute("SELECT email FROM parents WHERE id = %s", (ids["sarah"],)).fetchone()
    assert mike_row["email"] == "mike@y.com"
    assert sarah_row["email"] == "sarah@x.com"

    mike_identity = ka.execute(
        "SELECT provider_subject FROM auth_identities WHERE provider='email' AND parent_id=%s",
        (ids["mike"],),
    ).fetchone()
    sarah_identity = ka.execute(
        "SELECT provider_subject FROM auth_identities WHERE provider='email' AND parent_id=%s",
        (ids["sarah"],),
    ).fetchone()
    assert mike_identity["provider_subject"] == "mike@y.com"
    assert sarah_identity["provider_subject"] == "sarah@x.com"
    assert _count_email_identities(ka, ids["mike"]) == 1
    assert _count_email_identities(ka, ids["sarah"]) == 1


def test_update_parent_email_collision_caught_by_auth_identities_constraint_alone(ctx):
    """Confirms the cross-owner check structurally relies on auth_identities'
    own CONSTRAINT auth_identities_provider_subject_uniq UNIQUE(provider,
    provider_subject) (003_auth_identities.sql), not just parents.email's
    UNIQUE constraint: this collision target is an ATHLETE-owned identity row
    under an email no PARENT holds, so parents.email's own uniqueness never
    fires -- only the auth_identities UPDATE can catch it, and it must."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")
    _add_email_identity(ka, athlete_id=ids["leo"], email="shared-login@example.com")

    r = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "shared-login@example.com"})
    assert r.status_code == 409

    mike_row = ka.execute("SELECT email FROM parents WHERE id = %s", (ids["mike"],)).fetchone()
    assert mike_row["email"] == "mike@y.com"
    mike_identity = ka.execute(
        "SELECT provider_subject FROM auth_identities WHERE provider='email' AND parent_id=%s",
        (ids["mike"],),
    ).fetchone()
    assert mike_identity["provider_subject"] == "mike@y.com"
    athlete_identity = ka.execute(
        "SELECT provider_subject FROM auth_identities WHERE provider='email' AND athlete_id=%s",
        (ids["leo"],),
    ).fetchone()
    assert athlete_identity["provider_subject"] == "shared-login@example.com"


def test_update_parent_email_transaction_rolls_back_on_forced_failure(ctx):
    """Requirement 5: force a failure partway through (matching the
    UniqueViolation-monkeypatch technique from
    tests/test_apple_link_existing_flow.py's rollback tests) and confirm
    NEITHER write landed."""
    c, ids, ka = ctx
    _add_email_identity(ka, parent_id=ids["mike"], email="mike@y.com")

    real_execute = psycopg.Connection.execute

    def flaky_execute(self, query, *args, **kwargs):
        text = str(query)
        if "UPDATE auth_identities" in text:
            raise psycopg.errors.UniqueViolation("simulated conflict on auth_identities")
        return real_execute(self, query, *args, **kwargs)

    with patch.object(psycopg.Connection, "execute", flaky_execute):
        r = c.put(f"/api/admin/parents/{ids['mike']}", json={"email": "mike-new@y.com"})

    assert r.status_code == 409

    mike_row = ka.execute("SELECT email FROM parents WHERE id = %s", (ids["mike"],)).fetchone()
    assert mike_row["email"] == "mike@y.com"  # parents.email write did NOT land
    mike_identity = ka.execute(
        "SELECT provider_subject FROM auth_identities WHERE provider='email' AND parent_id=%s",
        (ids["mike"],),
    ).fetchone()
    assert mike_identity["provider_subject"] == "mike@y.com"  # neither did this one


def test_update_parent_email_with_no_existing_identity_row_is_not_an_error(ctx):
    """Judgment call (see admin.py's update_parent comment): a parent who has
    never logged in yet has zero auth_identities rows -- Phase 5's backfill
    only covers parents that existed at migration time, and
    resolve_identity() creates rows lazily on first login (identity_resolver
    .py), not at parent-creation time. The admin edit must not fail in that
    case; the parents.email UPDATE still succeeds and there is nothing to
    sync."""
    c, ids, ka = ctx
    assert _count_email_identities(ka, ids["nora"]) == 0

    r = c.put(f"/api/admin/parents/{ids['nora']}", json={"email": "nora-new@z.com"})
    assert r.status_code == 200
    assert r.json()["email"] == "nora-new@z.com"
    assert _count_email_identities(ka, ids["nora"]) == 0
