"""
Security Item 7B — admin hard-delete cascade repair.

api/routes/admin.py's ATHLETE_CHILD_TABLES / PARENT_CHILD_TABLES explicit
deletion lists were missing several current athlete/parent-owned tables with
ON DELETE NO ACTION (or no FK at all) back to athletes/parents — dietitian
bookings, FuelIQ progress tables, TeamCoach roster membership, recipe lists,
recipe selections, and the parent's own pending account_deletion_requests
row. Any of those FK-enforced tables having a row for the target athlete/
parent makes DELETE /api/admin/athletes/{id} or DELETE /api/admin/parents/{id}
500 with an IntegrityError instead of completing.

This file seeds one representative row in every table added by the 7B fix
(plus a couple of already-handled ones, to prove nothing regressed) and
exercises the real admin routes end-to-end.
"""

import os
os.environ["DB_PATH"] = ":memory:"

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth
from api.routes import admin as admin_module
from api.main import app

PASSWORD = "s3cret-admin-7b"


def _wipe(conn):
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


def _add_parent(conn, name, email):
    return conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, sqlite_now(), TRUE) RETURNING id",
        (name, email),
    ).fetchone()["id"]


def _add_athlete(conn, parent_id, first_name):
    return conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in, "
        "position, competition_level) VALUES (%s, %s, 14, 'F', 110.0, 5, 4.0, 'Forward', 'competitive_club') "
        "RETURNING id",
        (parent_id, first_name),
    ).fetchone()["id"]


def _seed_lesson_and_question(conn):
    lesson_id = conn.execute(
        "INSERT INTO fueliq_lessons (level, order_in_level, title, hook, source_citation) "
        "VALUES (1, 1, 'Iron 101', 'Why iron matters', 'USDA') RETURNING id"
    ).fetchone()["id"]
    question_id = conn.execute(
        "INSERT INTO fueliq_questions (lesson_id, question_text, option_a, option_b, correct_option, "
        "explanation, order_in_lesson) VALUES (%s, 'Q?', 'A', 'B', 'A', 'because', 1) RETURNING id",
        (lesson_id,),
    ).fetchone()["id"]
    return lesson_id, question_id


def _seed_team(conn, name="Surf FC"):
    return conn.execute(
        "INSERT INTO teams (name, season) VALUES (%s, '2026-fall') RETURNING id", (name,)
    ).fetchone()["id"]


def _seed_full_athlete_data(conn, athlete_id, lesson_id, question_id, team_id):
    """One row in every table the 7B fix newly handles, plus a couple of
    already-handled ones (events, meal_logs) so a full-family/athlete-only
    delete test exercises old and new cascade paths together."""
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date) "
                 "VALUES (%s, 'Practice', 'practice', sqlite_today())", (athlete_id,))
    conn.execute("INSERT INTO meal_logs (athlete_id, log_method, description) VALUES (%s, 'text', 'oatmeal')",
                 (athlete_id,))

    # ── newly-handled athlete-child tables (Item 7B) ──────────────────────────
    conn.execute("INSERT INTO dietitian_bookings (athlete_id, session_type, about_athlete) "
                 "VALUES (%s, 'intro', 'likes pasta')", (athlete_id,))
    conn.execute("INSERT INTO fueling_window_log (athlete_id, date, window_slot) "
                 "VALUES (%s, sqlite_today(), 'breakfast')", (athlete_id,))
    conn.execute("INSERT INTO roster_membership (athlete_id, team_id) VALUES (%s, %s)", (athlete_id, team_id))
    conn.execute("INSERT INTO recipe_selections (athlete_id, week_start, selection_date, fueling_window_key, "
                 "recipe_id) VALUES (%s, sqlite_today(), sqlite_today(), 'everyday_breakfast', 'R001')",
                 (athlete_id,))
    conn.execute("INSERT INTO instacart_handoff_feedback (athlete_id, outcome, would_use_again) "
                 "VALUES (%s, 'completed', 'yes')", (athlete_id,))
    conn.execute("INSERT INTO fueliq_athlete_progress (athlete_id) VALUES (%s)", (athlete_id,))
    conn.execute("INSERT INTO fueliq_badges_earned (athlete_id, badge_key) VALUES (%s, 'iron_starter')",
                 (athlete_id,))
    conn.execute("INSERT INTO fueliq_daily_challenge_answers (athlete_id, challenge_date, guess, correct) "
                 "VALUES (%s, sqlite_today(), 'true', 1)", (athlete_id,))
    conn.execute("INSERT INTO fueliq_daily_challenge_streak (athlete_id) VALUES (%s)", (athlete_id,))
    conn.execute("INSERT INTO fueliq_lesson_completions (athlete_id, lesson_id, points_earned) "
                 "VALUES (%s, %s, 10)", (athlete_id, lesson_id))
    conn.execute("INSERT INTO fueliq_notification_prefs (athlete_id) VALUES (%s)", (athlete_id,))
    conn.execute("INSERT INTO fueliq_quiz_attempts (athlete_id, question_id, selected_option, correct) "
                 "VALUES (%s, %s, 'A', 1)", (athlete_id, question_id))
    conn.execute("INSERT INTO fueliq_push_events (athlete_id, trigger, outcome, event_date) "
                 "VALUES (%s, 'morning', 'sent', sqlite_today())", (athlete_id,))

    # recipe_lists → recipe_list_items → recipe_list_item_sources (CASCADE from items)
    list_id = conn.execute("INSERT INTO recipe_lists (athlete_id, week_start) VALUES (%s, sqlite_today()) "
                            "RETURNING id", (athlete_id,)).fetchone()["id"]
    item_id = conn.execute("INSERT INTO recipe_list_items (list_id, name) VALUES (%s, 'Chicken breast') "
                            "RETURNING id", (list_id,)).fetchone()["id"]
    conn.execute("INSERT INTO recipe_list_item_sources (list_item_id, recipe_id, recipe_name) "
                 "VALUES (%s, 'R001', 'Grilled Chicken')", (item_id,))

    # notification_prefs — polymorphic, athlete side
    conn.execute("INSERT INTO notification_prefs (profile_type, profile_id) VALUES ('athlete', %s)",
                 (athlete_id,))


@pytest.fixture
def ctx(monkeypatch):
    keepalive = get_conn()
    init_db()
    run_all()
    _wipe(keepalive)
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "unit-test-signing-key-7b")
    admin_auth._failed_logins.clear()

    lesson_id, question_id = _seed_lesson_and_question(keepalive)
    team_id = _seed_team(keepalive)

    # Family under test: parent "Dana" -> athlete "Zoe" (fully loaded), plus a
    # deletion-request row for Dana (the normal real-world trigger for an
    # admin ending up performing this delete at all).
    dana_id = _add_parent(keepalive, "Dana Delete", "dana@example.com")
    zoe_id = _add_athlete(keepalive, dana_id, "Zoe")
    _seed_full_athlete_data(keepalive, zoe_id, lesson_id, question_id, team_id)
    keepalive.execute(
        "INSERT INTO account_deletion_requests (parent_id, parent_name, parent_email, athlete_names) "
        "VALUES (%s, 'Dana Delete', 'dana@example.com', 'Zoe')", (dana_id,)
    )
    keepalive.execute("INSERT INTO notification_prefs (profile_type, profile_id) VALUES ('parent', %s)",
                       (dana_id,))

    # Sibling family for the athlete-only delete test: parent "Eli" -> "Max"
    # (delete target, fully loaded) + "Mia" (sibling, must survive untouched).
    eli_id = _add_parent(keepalive, "Eli Sibling", "eli@example.com")
    max_id = _add_athlete(keepalive, eli_id, "Max")
    mia_id = _add_athlete(keepalive, eli_id, "Mia")
    _seed_full_athlete_data(keepalive, max_id, lesson_id, question_id, team_id)
    _seed_full_athlete_data(keepalive, mia_id, lesson_id, question_id, team_id)

    # A third athlete + coach on the SAME team as Max, to prove team/other-
    # roster-member data survives an athlete-only delete.
    other_parent_id = _add_parent(keepalive, "Other Parent", "other@example.com")
    other_athlete_id = _add_athlete(keepalive, other_parent_id, "Ivy")
    keepalive.execute("INSERT INTO roster_membership (athlete_id, team_id) VALUES (%s, %s)",
                       (other_athlete_id, team_id))
    coach_id = keepalive.execute(
        "INSERT INTO coaches (name, email) VALUES ('Coach K', 'coachk@example.com') RETURNING id"
    ).fetchone()["id"]
    keepalive.execute("INSERT INTO coach_team_access (coach_id, team_id) VALUES (%s, %s)", (coach_id, team_id))
    keepalive.commit()

    ids = {
        "dana": dana_id, "zoe": zoe_id,
        "eli": eli_id, "max": max_id, "mia": mia_id,
        "other_parent": other_parent_id, "other_athlete": other_athlete_id,
        "team": team_id, "coach": coach_id,
        "lesson": lesson_id, "question": question_id,
    }

    with TestClient(app) as c:
        r = c.post("/api/admin/login", json={"password": PASSWORD})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c, ids, keepalive
    keepalive.close()


_NEW_ATHLETE_TABLES = [
    "dietitian_bookings", "fueling_window_log", "roster_membership",
    "recipe_selections", "instacart_handoff_feedback",
    "fueliq_athlete_progress", "fueliq_badges_earned",
    "fueliq_daily_challenge_answers", "fueliq_daily_challenge_streak",
    "fueliq_lesson_completions", "fueliq_notification_prefs",
    "fueliq_quiz_attempts", "fueliq_push_events",
]


def _count(conn, table, col, id_):
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {col} = %s", (id_,)).fetchone()["n"]


# ── Step 7: full family delete ────────────────────────────────────────────────

def test_full_family_delete_succeeds_and_removes_all_child_rows(ctx):
    c, ids, ka = ctx

    r = c.request("DELETE", f"/api/admin/parents/{ids['dana']}", json={"confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True

    assert _count(ka, "parents", "id", ids["dana"]) == 0
    assert _count(ka, "athletes", "id", ids["zoe"]) == 0

    for table in ["events", "meal_logs", *_NEW_ATHLETE_TABLES]:
        assert _count(ka, table, "athlete_id", ids["zoe"]) == 0, f"{table} not cascaded"

    assert _count(ka, "recipe_lists", "athlete_id", ids["zoe"]) == 0
    assert ka.execute(
        "SELECT COUNT(*) AS n FROM recipe_list_items WHERE list_id IN "
        "(SELECT id FROM recipe_lists WHERE athlete_id = %s)", (ids["zoe"],)
    ).fetchone()["n"] == 0
    # recipe_list_item_sources cascades automatically off recipe_list_items —
    # confirm no dangling sources anywhere (the fixture also seeds Max/Mia's
    # own rows in the same tables, so this checks the FK invariant rather than
    # a whole-table zero count).
    assert ka.execute(
        "SELECT COUNT(*) AS n FROM recipe_list_item_sources s "
        "LEFT JOIN recipe_list_items i ON i.id = s.list_item_id WHERE i.id IS NULL"
    ).fetchone()["n"] == 0

    assert ka.execute(
        "SELECT COUNT(*) AS n FROM notification_prefs WHERE profile_type='athlete' AND profile_id=%s",
        (ids["zoe"],),
    ).fetchone()["n"] == 0
    assert ka.execute(
        "SELECT COUNT(*) AS n FROM notification_prefs WHERE profile_type='parent' AND profile_id=%s",
        (ids["dana"],),
    ).fetchone()["n"] == 0
    assert _count(ka, "account_deletion_requests", "parent_id", ids["dana"]) == 0

    # No FK violation happened (the request wouldn't have returned 200 if one had).
    assert ka.execute("SELECT COUNT(*) AS n FROM admin_audit_log WHERE action='delete_parent' AND target_id=%s",
                       (ids["dana"],)).fetchone()["n"] == 1


# ── Step 8: athlete-only delete — sibling + team preservation ────────────────

def test_athlete_only_delete_preserves_sibling_and_team(ctx):
    c, ids, ka = ctx

    r = c.request("DELETE", f"/api/admin/athletes/{ids['max']}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True

    assert _count(ka, "athletes", "id", ids["max"]) == 0
    for table in ["events", "meal_logs", *_NEW_ATHLETE_TABLES]:
        assert _count(ka, table, "athlete_id", ids["max"]) == 0, f"{table} not cascaded for Max"

    # Parent remains.
    assert _count(ka, "parents", "id", ids["eli"]) == 1

    # Sibling Mia and ALL her data remain, byte-for-byte untouched.
    assert _count(ka, "athletes", "id", ids["mia"]) == 1
    for table in ["events", "meal_logs", *_NEW_ATHLETE_TABLES]:
        assert _count(ka, table, "athlete_id", ids["mia"]) == 1, f"{table} incorrectly touched for sibling Mia"
    assert _count(ka, "recipe_lists", "athlete_id", ids["mia"]) == 1

    # Team, coach, and the OTHER roster member (Ivy) on the same team survive.
    assert _count(ka, "teams", "id", ids["team"]) == 1
    assert _count(ka, "coaches", "id", ids["coach"]) == 1
    assert _count(ka, "roster_membership", "athlete_id", ids["other_athlete"]) == 1
    assert ka.execute("SELECT COUNT(*) AS n FROM coach_team_access WHERE coach_id=%s AND team_id=%s",
                       (ids["coach"], ids["team"])).fetchone()["n"] == 1
    # Only Max's own roster row is gone.
    assert _count(ka, "roster_membership", "athlete_id", ids["max"]) == 0


# ── Step 9: forced child-table failure rolls back the whole transaction ──────

def test_forced_child_table_failure_rolls_back_entire_delete(ctx, monkeypatch):
    c, ids, ka = ctx

    # Force a failure INSIDE the route's transaction (after _delete_athlete has
    # done every real delete in-memory within that transaction, before commit)
    # by making the real _delete_athlete raise right after doing its normal
    # work. Exercises the actual try/BEGIN.../except: rollback path in
    # delete_athlete() with zero risk to real data — the preview step (which
    # runs before the try block and isn't itself exception-safe) is untouched.
    real_delete_athlete = admin_module._delete_athlete

    def _delete_athlete_then_raise(conn, athlete_id):
        real_delete_athlete(conn, athlete_id)
        raise RuntimeError("forced failure for Item 7B rollback test")

    monkeypatch.setattr(admin_module, "_delete_athlete", _delete_athlete_then_raise)

    r = c.request("DELETE", f"/api/admin/athletes/{ids['zoe']}")
    assert r.status_code == 500

    # Nothing was partially deleted — the whole transaction rolled back.
    assert _count(ka, "athletes", "id", ids["zoe"]) == 1
    for table in ["events", "meal_logs", *_NEW_ATHLETE_TABLES]:
        assert _count(ka, table, "athlete_id", ids["zoe"]) == 1, f"{table} partially deleted despite rollback"
    assert _count(ka, "recipe_lists", "athlete_id", ids["zoe"]) == 1
    # No audit row for a failed delete.
    assert ka.execute("SELECT COUNT(*) AS n FROM admin_audit_log WHERE action='delete_athlete' AND target_id=%s",
                       (ids["zoe"],)).fetchone()["n"] == 0


# ── Step 6: preview parity — newly-cascaded tables are counted too ───────────

def test_delete_preview_counts_the_newly_cascaded_tables(ctx):
    c, ids, _ = ctx
    preview = c.get(f"/api/admin/athletes/{ids['zoe']}/delete-preview").json()["counts"]
    for table in _NEW_ATHLETE_TABLES:
        assert preview.get(table) == 1, f"preview missing/wrong count for {table}: {preview}"
    assert preview.get("recipe_lists") == 1
    assert preview.get("recipe_list_items") == 1
    assert preview.get("notification_prefs") == 1

    parent_preview = c.get(f"/api/admin/parents/{ids['dana']}/delete-preview").json()["counts"]
    assert parent_preview.get("account_deletion_requests:parent_id") == 1
    assert parent_preview.get("notification_prefs:parent") == 1
