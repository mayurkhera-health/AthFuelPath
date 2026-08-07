"""
Additive database migrations — CREATE TABLE IF NOT EXISTS and INSERT OR IGNORE only.
Called at FastAPI startup; safe to run multiple times.
"""

from api.database import get_conn
from api.services.nutrition_calc import derive_intensity


def run_all():
    conn = get_conn()
    try:
        _create_confirmations(conn)
        _create_report_config(conn)
        _create_shopping_tables(conn)
        _create_expo_push_tokens(conn)
        _create_window_logs(conn)
        _create_notification_log(conn)
        _create_streak_state(conn)
        _add_timezone_to_tokens(conn)
        _add_intensity_to_events(conn)
        _add_venue_location_to_events(conn)
        _add_activity_type_to_events(conn)
        _add_uid_to_events(conn)
        _add_intensity_to_daily_targets(conn)
        _add_season_phase_to_athletes(conn)
        _add_food_preferences_to_athletes(conn)
        _add_date_of_birth_to_athletes(conn)
        _add_lifestyle_activity_to_athletes(conn)
        _add_diet_pref_to_athletes(conn)
        _create_problem_reports(conn)
        _add_category_to_problem_reports(conn)
        _create_coach_feedback(conn)
        _create_instacart_handoff_feedback(conn)
        _create_pantry_list_items(conn)
        _create_recipe_selections(conn)
        _create_recipe_lists(conn)
        _create_recipe_list_items(conn)
        _add_category_to_recipe_list_items(conn)
        _add_ingredient_type_to_recipe_list_items(conn)
        _create_recipe_list_item_sources(conn)
        _create_feature_requests(conn)
        _add_calendar_sync_to_athletes(conn)
        _add_source_to_events(conn)
        _create_admin_audit_log(conn)
        _create_health_tables(conn)
        _add_last_login_to_parents(conn)
        _add_blueprint_viewed_to_parents(conn)
        _create_fueliq_tables(conn)
        _create_fueliq_daily_challenge_tables(conn)
        _add_push_sent_to_daily_challenges(conn)
        _create_fueliq_notification_prefs(conn)
        _create_notification_prefs(conn)
        _create_fueliq_push_events(conn)
        _drop_fueliq_lessons_drop_week(conn)
        _add_phone_to_athletes(conn)
        _add_phone_to_parents(conn)
        _add_wind_down_dismissed_to_athletes(conn)
        _create_account_deletion_requests(conn)
        _create_dietitian_bookings(conn)
        _create_teamcoach_tables(conn)
        conn.commit()
    finally:
        conn.close()

    # Table-rebuild migrations run on their OWN connection, AFTER the batch above
    # has committed and closed. A rebuild must toggle PRAGMA foreign_keys, which
    # cannot change inside a transaction — so it owns its full transaction/pragma
    # lifecycle in isolation and must never share the batch connection.
    _migrate_athlete_logins_unique()
    _fix_recipe_selections_unique_constraint()
    _fix_daily_targets_unique_constraint()


def _create_confirmations(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS confirmations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL REFERENCES athletes(id),
            log_date    TEXT    NOT NULL,
            window_key  TEXT    NOT NULL,
            window_type TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, window_key, log_date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_confirmations_athlete_date
            ON confirmations (athlete_id, log_date)
    """)


_DEFAULT_CONFIG = [
    # key, value, description
    ("load_high_game_days",       3.0, "Game/tournament days per week that qualifies as high load"),
    ("prefuel_rate_low",          0.5, "Pre-fuel confirmation rate below which the safety flag can fire"),
    ("recovery_rate_low",         0.5, "Recovery confirmation rate below which the safety flag can fire"),
    ("hydration_rate_low",        0.5, "Hydration confirmation rate below which the safety flag can fire"),
    ("streak_min_confirms_per_day", 1.0, "Min confirmations in a day to count toward streak"),
    ("fueliq_lesson_points",         10.0, "Fuel IQ: points for completing a lesson"),
    ("fueliq_perfect_quiz_bonus",     5.0, "Fuel IQ: bonus for a 3/3 first-try quiz"),
    ("fueliq_streak_milestone_bonus", 15.0, "Fuel IQ: bonus for a 7-day streak milestone"),
    ("fueliq_review_points",          5.0, "Fuel IQ: points for a Refuel Your Brain review session"),
    ("fueliq_daily_challenge_points", 10.0, "Fuel IQ: points for completing the Daily Challenge"),
]


def _create_report_config(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_config (
            key         TEXT PRIMARY KEY,
            value       REAL NOT NULL,
            description TEXT,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.executemany(
        "INSERT OR IGNORE INTO report_config (key, value, description) VALUES (?, ?, ?)",
        _DEFAULT_CONFIG,
    )


def _create_expo_push_tokens(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expo_push_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER,
            parent_id   INTEGER,
            token       TEXT NOT NULL UNIQUE,
            platform    TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_expo_tokens_athlete
            ON expo_push_tokens (athlete_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_expo_tokens_parent
            ON expo_push_tokens (parent_id)
    """)


def _create_shopping_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueling_foods (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL UNIQUE,
            category      TEXT NOT NULL,
            role          TEXT,
            allergen_tags TEXT DEFAULT '',
            soft_hint     TEXT DEFAULT '',
            is_active     INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS athlete_food_prefs (
            athlete_id  INTEGER NOT NULL,
            food_name   TEXT NOT NULL,
            preference  TEXT NOT NULL,
            category    TEXT,
            PRIMARY KEY (athlete_id, food_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shopping_lists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL,
            week_start  TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, week_start)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shopping_list_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id     INTEGER NOT NULL,
            name        TEXT NOT NULL,
            category    TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'suggested',
            checked     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (list_id) REFERENCES shopping_lists(id)
        )
    """)

def _create_window_logs(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS window_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id      INTEGER NOT NULL,
            window_id       TEXT NOT NULL,
            log_date        TEXT NOT NULL,
            method          TEXT NOT NULL DEFAULT 'photo',
            text            TEXT,
            photo_url       TEXT,
            thumb_url       TEXT,
            audio_url       TEXT,
            nutrient_status TEXT NOT NULL DEFAULT 'none',
            logged_by       TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, window_id, log_date)
        )
    """)
    # Additive column migrations for rows created before these columns existed
    cols = [r[1] for r in conn.execute("PRAGMA table_info(window_logs)").fetchall()]
    if "logged_by" not in cols:
        conn.execute("ALTER TABLE window_logs ADD COLUMN logged_by TEXT")
    if "audio_url" not in cols:
        conn.execute("ALTER TABLE window_logs ADD COLUMN audio_url TEXT")


def _create_notification_log(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            window_key TEXT    NOT NULL,
            send_date  TEXT    NOT NULL,
            recipient  TEXT    NOT NULL,
            token      TEXT    NOT NULL,
            sent_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, window_key, send_date, recipient)
        )
    """)


def _add_timezone_to_tokens(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(expo_push_tokens)").fetchall()]
    if "timezone" not in cols:
        conn.execute("ALTER TABLE expo_push_tokens ADD COLUMN timezone TEXT")


def _create_streak_state(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS streak_state (
            athlete_id                INTEGER PRIMARY KEY,
            freeze_tokens             INTEGER NOT NULL DEFAULT 1,
            last_celebrated_milestone INTEGER NOT NULL DEFAULT 0,
            updated_at                TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _add_intensity_to_events(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "intensity" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN intensity TEXT")
        rows = conn.execute("""
            SELECT e.id AS id, e.event_type AS event_type, a.competition_level AS competition_level
            FROM events e LEFT JOIN athletes a ON a.id = e.athlete_id
        """).fetchall()
        for r in rows:
            intensity = derive_intensity(r["event_type"], r["competition_level"])
            conn.execute("UPDATE events SET intensity = ? WHERE id = ?", (intensity, r["id"]))


def _add_season_phase_to_athletes(conn):
    """Fuel Gauge: season phase feeds the daily target formula + intensity
    derivation (design §2.4). Nullable; existing athletes default to 'in_season'.
    Idempotent — safe to run on every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "season_phase" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN season_phase TEXT DEFAULT 'in_season'")


def _add_food_preferences_to_athletes(conn):
    """Onboarding wizard: free-text food preferences (textures, likes/dislikes)
    captured in Step 4 and fed to the AI coach context alongside allergies +
    dietary_restrictions. Nullable, no default — absence means 'not provided',
    so the coach omits it cleanly. Idempotent — safe to run on every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "food_preferences" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN food_preferences TEXT DEFAULT NULL")


def _add_date_of_birth_to_athletes(conn):
    """Capture true date of birth (ISO 'YYYY-MM-DD') so age can be derived live
    via nutrition_calc.calc_age() instead of stored as a static integer. Nullable:
    existing athletes have no DOB and fall back to the stored `age` column until
    they re-enter it. Idempotent — safe to run on every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "date_of_birth" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN date_of_birth TEXT NULL")


def _add_diet_pref_to_athletes(conn):
    """Dietary pattern for protein multiplier (ISSN leucine bioavailability).
    Values: omnivore / vegetarian / vegan. Defaults to 'omnivore'.
    Drives DIET_PROT_MULT in calc_daily_protein(). Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "diet_pref" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN diet_pref TEXT DEFAULT 'omnivore'")


def _add_lifestyle_activity_to_athletes(conn):
    """Onboarding field 7: athlete's daily non-training lifestyle activity level.
    Drives the lifestyle PAL in calc_tdee(). Defaults to 'light' (PAL 1.4) for all
    existing athletes. Values: sedentary / light / moderate. Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "lifestyle_activity" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN lifestyle_activity TEXT DEFAULT 'light'")


def _add_venue_location_to_events(conn):
    """Venue + precise coordinates for an event, captured from Google Places on the
    client. `latitude`/`longitude` feed coordinate-based weather lookup; `city` is
    kept for backward compat + fallback. All nullable (venue stays optional)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "venue_name" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN venue_name TEXT")
    if "address" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN address TEXT")
    if "latitude" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN latitude REAL")
    if "longitude" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN longitude REAL")


def _add_activity_type_to_events(conn):
    """Per-event activity type tagged by the athlete (Calendar Sync & Day Layout).
    One of the 7 activity_engine keys: practice / game / tournament / speed_sprint /
    strength_cond / active_recovery / double_session. Nullable = untagged; the
    2-hour default (activity_type_resolver) resolves untagged events to 'practice'
    on read. Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "activity_type" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN activity_type TEXT DEFAULT NULL")


def _add_uid_to_events(conn):
    """ICS import dedup: store the source calendar VEVENT UID so re-imports — and
    the onboarding-then-Schedule-tab double import — skip events already on the
    athlete's schedule. Nullable: manually-created events have no uid. A PARTIAL
    unique index on (athlete_id, uid) WHERE uid IS NOT NULL enforces dedup at the
    DB layer (defense-in-depth behind the client-side skip) while letting an
    athlete keep many NULL-uid manual events. Idempotent — safe every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "uid" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN uid TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_athlete_uid "
        "ON events(athlete_id, uid) WHERE uid IS NOT NULL"
    )


def _add_intensity_to_daily_targets(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_targets)").fetchall()]
    if "intensity" not in cols:
        conn.execute("ALTER TABLE daily_targets ADD COLUMN intensity TEXT")


def _fix_daily_targets_unique_constraint():
    """
    daily_targets had no UNIQUE(athlete_id, target_date) — its only key was an
    autoincrement id the route's INSERT OR REPLACE never supplied, so every
    recalculation for the same athlete/day inserted a brand-new row instead of
    replacing it. Downstream readers all do a plain .fetchone() with no
    ORDER BY, so once duplicates existed the row returned was unspecified.

    Dedupes existing rows (keeping the highest id — the most recently computed
    row — per athlete_id/target_date) and rebuilds the table with the missing
    UNIQUE constraint so the route's write can become a real upsert.

    Runs on a dedicated connection after the batch has committed. Idempotent:
    returns immediately once the new constraint exists.
    """
    conn = get_conn()
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_targets'"
        ).fetchone():
            return

        for idx in conn.execute("PRAGMA index_list(daily_targets)").fetchall():
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
            if set(cols) == {"athlete_id", "target_date"}:
                return  # Already correct — nothing to do

        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN")
            conn.execute("""
                DELETE FROM daily_targets
                WHERE id NOT IN (
                    SELECT MAX(id) FROM daily_targets GROUP BY athlete_id, target_date
                )
            """)
            conn.execute("""
                CREATE TABLE daily_targets_new (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id        INTEGER REFERENCES athletes(id),
                    target_date       TEXT NOT NULL,
                    event_type        TEXT,
                    total_calories    INTEGER,
                    carbs_g_min       INTEGER,
                    carbs_g_max       INTEGER,
                    protein_g_min     INTEGER,
                    protein_g_max     INTEGER,
                    fat_g_min         INTEGER,
                    fat_g_max         INTEGER,
                    iron_mg           INTEGER,
                    calcium_mg        INTEGER,
                    hydration_oz_min  INTEGER,
                    hydration_oz_max  INTEGER,
                    lea_alert         BOOLEAN,
                    targets_raw       TEXT,
                    intensity         TEXT,
                    UNIQUE (athlete_id, target_date)
                )
            """)
            conn.execute("""
                INSERT INTO daily_targets_new
                SELECT id, athlete_id, target_date, event_type, total_calories,
                       carbs_g_min, carbs_g_max, protein_g_min, protein_g_max,
                       fat_g_min, fat_g_max, iron_mg, calcium_mg,
                       hydration_oz_min, hydration_oz_max, lea_alert, targets_raw, intensity
                FROM daily_targets
            """)
            conn.execute("DROP TABLE daily_targets")
            conn.execute("ALTER TABLE daily_targets_new RENAME TO daily_targets")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.isolation_level = ""
    finally:
        conn.close()


def _create_problem_reports(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS problem_reports (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            description    TEXT NOT NULL,
            screenshot_url TEXT,
            app_version    TEXT,
            platform       TEXT,
            role_hint      TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _add_category_to_problem_reports(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(problem_reports)").fetchall()]
    if "category" not in cols:
        conn.execute("ALTER TABLE problem_reports ADD COLUMN category TEXT")


def _add_calendar_sync_to_athletes(conn):
    """Recurring calendar sync: store the BYGA / PlayMetrics .ics subscription URL
    per athlete. Both nullable — an athlete may connect zero, one, or both feeds.
    SQLite has no `ADD COLUMN IF NOT EXISTS` and only allows ONE column per ALTER,
    so guard each add with a PRAGMA check (same pattern as _add_uid_to_events).
    Idempotent — safe every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "byga_ics_url" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN byga_ics_url TEXT")
    if "playmetrics_ics_url" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN playmetrics_ics_url TEXT")


def _add_source_to_events(conn):
    """Tag each event with its origin so the calendar-sync reconcile can tell
    synced events apart from manually-added ones. `source` defaults to 'manual'
    (existing rows + parent-created events); the sync job writes 'byga' /
    'playmetrics'. `synced_at` records the last time the sync touched the row
    (TEXT ISO, NULL for manual events) — useful for debugging + sync-status UI.
    The delete phase only ever removes rows whose source matches the feed, so a
    manual event is never wiped. Idempotent — safe every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "source" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN source TEXT DEFAULT 'manual'")
    if "synced_at" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN synced_at TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_athlete_source "
        "ON events(athlete_id, source)"
    )


def _add_last_login_to_parents(conn):
    """Beta login alerts: track each parent's most recent login so we can tell a
    first-ever login (new signup) from a returning one. Nullable. Existing
    parents at migration time are backfilled to created_at so they're never
    mislabeled as brand-new the first time they sign in post-deploy — only rows
    created afterward start NULL. Idempotent — safe every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(parents)").fetchall()]
    if "last_login_at" not in cols:
        conn.execute("ALTER TABLE parents ADD COLUMN last_login_at TEXT")
        conn.execute("UPDATE parents SET last_login_at = created_at WHERE last_login_at IS NULL")


def _add_blueprint_viewed_to_parents(conn):
    """Track the first time a parent opens the Blueprint screen so we can send a
    one-time onboarding summary email. Nullable — NULL means never viewed. Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(parents)").fetchall()]
    if "blueprint_first_viewed_at" not in cols:
        conn.execute("ALTER TABLE parents ADD COLUMN blueprint_first_viewed_at TEXT")


def _add_phone_to_athletes(conn):
    """Athlete contact phone for SMS reminders, emergency contact, and account
    recovery. Nullable — optional at onboarding and in edit-profile. Stored as the
    client-formatted string (e.g. '(408) 555-1234'); 10-digit US validated server-
    side before write. Idempotent — safe every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "phone" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN phone TEXT DEFAULT NULL")


def _add_phone_to_parents(conn):
    """Parent contact phone, editable from Settings. Nullable. Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(parents)").fetchall()]
    if "phone" not in cols:
        conn.execute("ALTER TABLE parents ADD COLUMN phone TEXT DEFAULT NULL")


def _add_wind_down_dismissed_to_athletes(conn):
    """Permanent 'Skip forever' flag for the Evening Wind-Down card (day_layout.py,
    behind DAY_LAYOUT_V2). Set via PATCH /athletes/:id/dismiss-wind-down. Idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(athletes)").fetchall()]
    if "wind_down_dismissed" not in cols:
        conn.execute("ALTER TABLE athletes ADD COLUMN wind_down_dismissed INTEGER DEFAULT 0")


def _create_account_deletion_requests(conn):
    """Delete Account no longer deletes anything in-app — it records the
    request and notifies the team, who complete the deletion out-of-band.
    See api/routes/parents.py::delete_parent_account."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_deletion_requests (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id      INTEGER NOT NULL REFERENCES parents(id),
            parent_name    TEXT NOT NULL,
            parent_email   TEXT NOT NULL,
            athlete_names  TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _create_dietitian_bookings(conn):
    """'Talk to a Dietitian' session requests (app/(app)/coach/dietitian.tsx).
    Previously written only to on-device AsyncStorage and never sent anywhere —
    this table + the emailed notification are the real persistence."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dietitian_bookings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id     INTEGER NOT NULL REFERENCES athletes(id),
            session_type   TEXT NOT NULL,
            about_athlete  TEXT NOT NULL,
            reason         TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _create_admin_audit_log(conn):
    # Admin Module audit trail. This schema intentionally matches the richer table
    # already present in production from the earlier FuelUp-Admin deployment (46
    # historical rows on the volume) so both coexist and CREATE IF NOT EXISTS is a
    # no-op there. actor_*/action/target_type/target_id are NOT NULL; the detail
    # blob (cascade counts, changed fields) is stored as JSON text in after_state.
    # No parent/athlete FK — rows must survive after the target is hard-deleted.
    # Idempotent — safe every startup.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id     INTEGER NOT NULL,
            actor_email  TEXT NOT NULL,
            actor_role   TEXT NOT NULL,
            action       TEXT NOT NULL,
            target_type  TEXT NOT NULL,
            target_id    INTEGER NOT NULL,
            target_email TEXT,
            before_state TEXT,
            after_state  TEXT,
            request_ip   TEXT,
            user_agent   TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_audit_created "
        "ON admin_audit_log(created_at)"
    )


_HEALTH_CHECK_NAMES = [
    "bedrock_ping", "bedrock_inference", "gmail_smtp", "db_writable", "disk_space",
    "scheduler_notifications", "scheduler_calendar_sync", "calendar_sync_systemic",
    "expo_push",
]


def _create_health_tables(conn):
    # System Health monitoring: current state per check, append-only transition
    # history, scheduler heartbeats, expo-send outcomes, and a scratch table the
    # db_writable probe writes/deletes a row in. last_alerted_at powers the alert
    # cooldown (survives restart). Idempotent — safe every startup.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_checks (
            check_name      TEXT PRIMARY KEY,
            status          TEXT NOT NULL DEFAULT 'unknown',
            detail          TEXT,
            metric_value    REAL,
            last_checked_at TEXT,
            last_green_at   TEXT,
            last_red_at     TEXT,
            last_alerted_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_incidents (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            check_name TEXT NOT NULL,
            from_status TEXT,
            to_status  TEXT,
            detail     TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_incidents_created ON health_incidents(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_incidents_check ON health_incidents(check_name, created_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_heartbeats (
            job_name        TEXT PRIMARY KEY,
            last_run_at     TEXT,
            last_success_at TEXT,
            last_error      TEXT,
            meta            TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expo_push_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            success    INTEGER NOT NULL,
            detail     TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expo_push_log_created ON expo_push_log(created_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_scratch (
            id INTEGER PRIMARY KEY,
            v  TEXT
        )
    """)
    # Seed a row per check so the admin shows all 9 as 'unknown' before the first run.
    conn.executemany(
        "INSERT OR IGNORE INTO health_checks (check_name, status) VALUES (?, 'unknown')",
        [(n,) for n in _HEALTH_CHECK_NAMES],
    )


def _create_recipe_selections(conn):
    """Recipe Selection: records which recipe an athlete has chosen for a
    specific fueling window on a specific date. Drives the weekly grocery
    list aggregation — ingredients from selected recipes are written to
    shopping_list_items with source='recipe'. One selection per athlete
    per date per fueling window — UNIQUE enforces this at the DB layer.
    Idempotent — safe to run on every startup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipe_selections (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id          INTEGER NOT NULL REFERENCES athletes(id),
            week_start          TEXT    NOT NULL,
            selection_date      TEXT    NOT NULL,
            fueling_window_key  TEXT    NOT NULL,
            recipe_id           TEXT    NOT NULL,
            servings            INTEGER NOT NULL DEFAULT 1,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, selection_date, fueling_window_key)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_recipe_selections_athlete_week
            ON recipe_selections (athlete_id, week_start)
    """)


def _create_recipe_lists(conn):
    """Recipe Lists: one grocery list per athlete per week, scoped to recipe
    selections rather than pantry suggestions. Separate from shopping_lists so
    recipe-derived items can be managed independently. UNIQUE enforces one list
    per athlete per week at the DB layer. Idempotent — safe to run on every startup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipe_lists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL REFERENCES athletes(id),
            week_start  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, week_start)
        )
    """)


def _create_recipe_list_items(conn):
    """Recipe List Items: ingredients derived from recipe selections, one row per
    ingredient name per list. Separate from shopping_list_items so recipe-sourced
    items have their own checked state and lifecycle. Idempotent — safe to run on
    every startup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipe_list_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id     INTEGER NOT NULL REFERENCES recipe_lists(id),
            name        TEXT    NOT NULL,
            checked     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (list_id, name)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recipe_list_items_list "
        "ON recipe_list_items (list_id)"
    )


def _add_category_to_recipe_list_items(conn):
    """Add category column to recipe_list_items for grouped grocery display.
    Values match pantryCategories.ts: produce, protein, carb, fat, hydration, other.
    Idempotent — safe to run on every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(recipe_list_items)").fetchall()]
    if "category" not in cols:
        conn.execute(
            "ALTER TABLE recipe_list_items ADD COLUMN category TEXT NOT NULL DEFAULT 'other'"
        )


def _add_ingredient_type_to_recipe_list_items(conn):
    """Add ingredient_type column to recipe_list_items.
    Values: 'main' (needs shopping) or 'staple' (pantry item, pre-checked).
    Idempotent — safe to run on every startup."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(recipe_list_items)").fetchall()]
    if "ingredient_type" not in cols:
        conn.execute(
            "ALTER TABLE recipe_list_items ADD COLUMN ingredient_type TEXT NOT NULL DEFAULT 'main'"
        )


def _create_recipe_list_item_sources(conn):
    """Track which recipes contributed each grocery list ingredient.
    Enables source display in UI and correct removal behavior when
    a recipe is deselected. Idempotent — safe to run on every startup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipe_list_item_sources (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            list_item_id INTEGER NOT NULL REFERENCES recipe_list_items(id) ON DELETE CASCADE,
            recipe_id    TEXT    NOT NULL,
            recipe_name  TEXT    NOT NULL,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (list_item_id, recipe_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_recipe_list_item_sources_item
            ON recipe_list_item_sources (list_item_id)
    """)


def _create_feature_requests(conn):
    # "What's Coming" → Suggest a Feature submissions. Each row also triggers a
    # best-effort email to the team (see api/routes/feedback.py). reason is
    # nullable — it's an optional field on the form.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_requests (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT,
            athlete_id   INTEGER,
            suggestion   TEXT NOT NULL,
            reason       TEXT,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _create_instacart_handoff_feedback(conn):
    # Instacart grocery-handoff MVP feedback (Return & Feedback step). High-volume,
    # no email — same shape as coach_feedback. comment is unused by the MVP UI (no
    # free-text field) but kept nullable so adding one later is a pure frontend change.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instacart_handoff_feedback (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id      INTEGER,
            outcome         TEXT NOT NULL,
            would_use_again TEXT NOT NULL,
            comment         TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _create_coach_feedback(conn):
    # Thumbs up/down telemetry on coach answers. High-volume, no email. `reason`
    # is nullable now so adding reason chips later is a pure frontend change.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coach_feedback (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            rating         TEXT NOT NULL,
            question       TEXT,
            answer_excerpt TEXT,
            window_key     TEXT,
            recipe_intent  INTEGER,
            role_hint      TEXT,
            reason         TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _create_pantry_list_items(conn):
    """Weekly Prep storage. Columns match pantry_service INSERT/SELECT; UNIQUE backs
    the INSERT OR IGNORE dedup. Idempotent."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pantry_list_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id    INTEGER NOT NULL,
            week_start    TEXT    NOT NULL,
            food_id       TEXT    NOT NULL,
            name          TEXT    NOT NULL,
            cue_label     TEXT,
            purchase_unit TEXT,
            role          TEXT,
            meal_context  TEXT,
            must_have     INTEGER NOT NULL DEFAULT 0,
            checked       INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, week_start, food_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pantry_athlete_week "
        "ON pantry_list_items (athlete_id, week_start)"
    )


def _create_fueliq_tables(conn):
    """Fuel IQ: gamified nutrition-education tab (lessons, myths, quiz, score,
    badges). Lessons and myths share one table (`is_myth` discriminates); a myth
    has `verdict`/`science_text` instead of `fact_body`/`takeaway`. Score/streak
    live in `fueliq_athlete_progress`, one row per athlete, created lazily on
    first read (see fueliq_service.get_progress). Idempotent — safe every startup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_lessons (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            level           INTEGER NOT NULL,
            order_in_level  INTEGER NOT NULL,
            is_myth         INTEGER NOT NULL DEFAULT 0,
            title           TEXT NOT NULL,
            hook            TEXT NOT NULL,
            fact_body       TEXT,
            visual_ref      TEXT,
            takeaway        TEXT,
            verdict         TEXT,
            science_text    TEXT,
            category        TEXT,
            source_citation TEXT NOT NULL,
            points          INTEGER NOT NULL DEFAULT 10,
            review_status   TEXT NOT NULL DEFAULT 'draft',
            reviewed_by     TEXT,
            review_date     TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_questions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id         INTEGER NOT NULL REFERENCES fueliq_lessons(id),
            question_text     TEXT NOT NULL,
            option_a          TEXT NOT NULL,
            option_b          TEXT NOT NULL,
            option_c          TEXT,
            correct_option    TEXT NOT NULL,
            explanation       TEXT NOT NULL,
            misconception_tag TEXT,
            order_in_lesson   INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_athlete_progress (
            athlete_id                INTEGER PRIMARY KEY REFERENCES athletes(id),
            score                     INTEGER NOT NULL DEFAULT 50,
            current_streak            INTEGER NOT NULL DEFAULT 0,
            best_streak               INTEGER NOT NULL DEFAULT 0,
            freeze_tokens             INTEGER NOT NULL DEFAULT 1,
            last_activity_date        TEXT,
            last_celebrated_milestone INTEGER NOT NULL DEFAULT 0,
            updated_at                TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_lesson_completions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id     INTEGER NOT NULL REFERENCES athletes(id),
            lesson_id      INTEGER NOT NULL REFERENCES fueliq_lessons(id),
            perfect_quiz   INTEGER NOT NULL DEFAULT 0,
            points_earned  INTEGER NOT NULL,
            completed_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, lesson_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_quiz_attempts (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id        INTEGER NOT NULL REFERENCES athletes(id),
            question_id       INTEGER NOT NULL REFERENCES fueliq_questions(id),
            selected_option   TEXT NOT NULL,
            correct           INTEGER NOT NULL,
            misconception_tag TEXT,
            answered_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_badges_earned (
            athlete_id  INTEGER NOT NULL REFERENCES athletes(id),
            badge_key   TEXT NOT NULL,
            earned_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, badge_key)
        )
    """)


def _create_fueliq_daily_challenge_tables(conn):
    """Daily Challenge: one global myth-style challenge published per calendar
    day (PST — see fueliq_daily_challenge_service._today_pst), same for every
    athlete (no per-athlete personalization/rotation). Deliberately a fully
    separate feature from the old Myth Buster pool it replaces — its own
    content table, its own answers table, and its own streak (NOT folded into
    fueliq_athlete_progress/fueliq_streak.py, which track lesson activity)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_daily_challenges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_date  TEXT NOT NULL UNIQUE,
            title           TEXT NOT NULL,
            hook            TEXT NOT NULL,
            verdict         TEXT NOT NULL,
            science_text    TEXT NOT NULL,
            source_citation TEXT,
            points          INTEGER NOT NULL DEFAULT 10,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_daily_challenge_answers (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id     INTEGER NOT NULL REFERENCES athletes(id),
            challenge_date TEXT NOT NULL,
            guess          TEXT NOT NULL,
            correct        INTEGER NOT NULL,
            answered_at    TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, challenge_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_daily_challenge_streak (
            athlete_id          INTEGER PRIMARY KEY REFERENCES athletes(id),
            current_streak      INTEGER NOT NULL DEFAULT 0,
            best_streak         INTEGER NOT NULL DEFAULT 0,
            last_completed_date TEXT,
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _add_push_sent_to_daily_challenges(conn):
    """Dedup guard for the daily 5pm-PST push job — one column on the
    challenge row itself (not a separate log table) since there's exactly
    one challenge per day, so "has today's push gone out" is naturally a
    property of that row. NULL = not sent yet."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(fueliq_daily_challenges)").fetchall()]
    if "push_sent_at" not in cols:
        conn.execute("ALTER TABLE fueliq_daily_challenges ADD COLUMN push_sent_at TEXT")


def _create_notification_prefs(conn):
    """Per-profile fuel-window notification controls (Training/Game Day
    toggles + Quiet Hours from Settings). One row per (profile_type,
    profile_id) — an athlete and their parent set these independently,
    since each is silencing their OWN phone. Defaults match
    DEFAULT_NOTIF_PREFS on the mobile side (both day types on, quiet
    hours 22:00-07:00) so a profile that's never opened Settings gets
    the same behavior as today's hardcoded-everyone-gets-reminders
    system. UPSERTED by PATCH /api/notifications/prefs."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_prefs (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type         TEXT    NOT NULL,
            profile_id           INTEGER NOT NULL,
            training_days        INTEGER NOT NULL DEFAULT 1,
            game_days            INTEGER NOT NULL DEFAULT 1,
            quiet_hours_enabled  INTEGER NOT NULL DEFAULT 1,
            quiet_start          TEXT    NOT NULL DEFAULT '22:00',
            quiet_end            TEXT    NOT NULL DEFAULT '07:00',
            updated_at           TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(profile_type, profile_id)
        )
    """)


def _create_fueliq_notification_prefs(conn):
    """Per-athlete opt-in flags for the two Fuel IQ §2.1 push triggers.
    Defaults to both enabled. UPSERTED by PATCH /api/notifications/fueliq-prefs."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_notification_prefs (
            athlete_id       INTEGER PRIMARY KEY REFERENCES athletes(id),
            morning_enabled  INTEGER NOT NULL DEFAULT 1,
            pregame_enabled  INTEGER NOT NULL DEFAULT 1,
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _create_fueliq_push_events(conn):
    """Audit trail for Fuel IQ notification sends and skips. Queryable for
    skip-rate analysis (e.g. pregame trigger skipped due to no start_time).
    INSERT OR IGNORE — at most one event per (athlete, trigger, outcome, date)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueliq_push_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL,
            trigger    TEXT    NOT NULL,
            outcome    TEXT    NOT NULL,
            event_date TEXT    NOT NULL,
            logged_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, trigger, outcome, event_date)
        )
    """)


def _drop_fueliq_lessons_drop_week(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(fueliq_lessons)").fetchall()]
    if "drop_week" in cols:
        conn.execute("ALTER TABLE fueliq_lessons DROP COLUMN drop_week")


def _fix_recipe_selections_unique_constraint():
    """
    Replace UNIQUE (athlete_id, selection_date, fueling_window_key) with
    UNIQUE (athlete_id, week_start, fueling_window_key, recipe_id) so parents
    can select multiple recipes per fueling window per week — only the exact
    same recipe in the same window is blocked as a duplicate.

    Runs on a dedicated connection after the batch has committed. Idempotent:
    returns immediately once the new constraint exists.
    """
    conn = get_conn()
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recipe_selections'"
        ).fetchone():
            return

        for idx in conn.execute("PRAGMA index_list(recipe_selections)").fetchall():
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
            if set(cols) == {"athlete_id", "week_start", "fueling_window_key", "recipe_id"}:
                return  # Already correct — nothing to do

        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN")
            conn.execute("""
                CREATE TABLE recipe_selections_new (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id          INTEGER NOT NULL REFERENCES athletes(id),
                    week_start          TEXT    NOT NULL,
                    selection_date      TEXT    NOT NULL,
                    fueling_window_key  TEXT    NOT NULL,
                    recipe_id           TEXT    NOT NULL,
                    servings            INTEGER NOT NULL DEFAULT 1,
                    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE (athlete_id, week_start, fueling_window_key, recipe_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO recipe_selections_new
                SELECT * FROM recipe_selections
            """)
            conn.execute("DROP TABLE recipe_selections")
            conn.execute("ALTER TABLE recipe_selections_new RENAME TO recipe_selections")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_recipe_selections_athlete_week
                ON recipe_selections (athlete_id, week_start)
            """)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.isolation_level = ""
    finally:
        conn.close()


def _create_teamcoach_tables(conn):
    # coaches — auth_provider_id is NULL for MVP password auth; reserved for future SSO.
    # password_hash/salt carry MVP credentials.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coaches (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            email            TEXT    UNIQUE NOT NULL,
            auth_provider_id TEXT    NULL,
            password_hash    TEXT    NULL,
            salt             TEXT    NULL,
            created_at       TEXT    DEFAULT (datetime('now'))
        )
    """)
    # club_id is unused in MVP but kept in schema for future Athletic Director rollup.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            season        TEXT    NOT NULL,
            club_id       INTEGER NULL,
            threshold_pct INTEGER NOT NULL DEFAULT 80,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coach_team_access (
            coach_id INTEGER NOT NULL REFERENCES coaches(id),
            team_id  INTEGER NOT NULL REFERENCES teams(id),
            PRIMARY KEY (coach_id, team_id)
        )
    """)
    # parent_consent_flag stays in schema even though ENFORCE_CONSENT=False in MVP
    # (decision #1) — preserves path to enforcement later without a migration.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roster_membership (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id          INTEGER NOT NULL REFERENCES athletes(id),
            team_id             INTEGER NOT NULL REFERENCES teams(id),
            parent_consent_flag INTEGER NOT NULL DEFAULT 0,
            joined_at           TEXT    DEFAULT (datetime('now')),
            UNIQUE (athlete_id, team_id)
        )
    """)
    # window_slot values: everyday | fuel_before | top_up | during | recharge | rebuild
    # Column is named 'date' per spec (not log_date).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fueling_window_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL REFERENCES athletes(id),
            date        TEXT    NOT NULL,
            window_slot TEXT    NOT NULL,
            applicable  INTEGER NOT NULL DEFAULT 1,
            completed   INTEGER NOT NULL DEFAULT 0,
            logged_at   TEXT    DEFAULT (datetime('now')),
            UNIQUE (athlete_id, date, window_slot)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_engagement_snapshot (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id                 INTEGER NOT NULL REFERENCES teams(id),
            week_start              TEXT    NOT NULL,
            threshold_pct           INTEGER NOT NULL DEFAULT 80,
            players_above_threshold INTEGER NOT NULL DEFAULT 0,
            roster_count            INTEGER NOT NULL DEFAULT 0,
            generated_at            TEXT    DEFAULT (datetime('now')),
            UNIQUE (team_id, week_start)
        )
    """)
def _fix_recipe_selections_unique_constraint():
    """
    Replace UNIQUE (athlete_id, selection_date, fueling_window_key) with
    UNIQUE (athlete_id, week_start, fueling_window_key, recipe_id) so parents
    can select multiple recipes per fueling window per week — only the exact
    same recipe in the same window is blocked as a duplicate.

    Runs on a dedicated connection after the batch has committed. Idempotent:
    returns immediately once the new constraint exists.
    """
    conn = get_conn()
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recipe_selections'"
        ).fetchone():
            return

        for idx in conn.execute("PRAGMA index_list(recipe_selections)").fetchall():
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
            if set(cols) == {"athlete_id", "week_start", "fueling_window_key", "recipe_id"}:
                return  # Already correct — nothing to do

        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN")
            conn.execute("""
                CREATE TABLE recipe_selections_new (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id          INTEGER NOT NULL REFERENCES athletes(id),
                    week_start          TEXT    NOT NULL,
                    selection_date      TEXT    NOT NULL,
                    fueling_window_key  TEXT    NOT NULL,
                    recipe_id           TEXT    NOT NULL,
                    servings            INTEGER NOT NULL DEFAULT 1,
                    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE (athlete_id, week_start, fueling_window_key, recipe_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO recipe_selections_new
                SELECT * FROM recipe_selections
            """)
            conn.execute("DROP TABLE recipe_selections")
            conn.execute("ALTER TABLE recipe_selections_new RENAME TO recipe_selections")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_recipe_selections_athlete_week
                ON recipe_selections (athlete_id, week_start)
            """)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.isolation_level = ""
    finally:
        conn.close()


def _migrate_athlete_logins_unique():
    """
    Add UNIQUE(athlete_id) to athlete_logins — defense-in-depth behind the
    code-level already-claimed guard in routes/auth.py (the guard is the primary
    safety; this stops a duplicate athlete login at the DB layer too).

    Production was created from db/setup.py, which lacked the constraint, so this
    rebuilds the table (SQLite can't ALTER ADD CONSTRAINT). Runs on a DEDICATED
    connection with its own transaction + foreign_keys toggle, because PRAGMA
    foreign_keys cannot change inside a transaction and must not collide with
    run_all()'s batch transaction. Idempotent: once the unique index exists it
    returns immediately, so it's safe on every deploy.
    """
    conn = get_conn()
    try:
        # No-op if the table doesn't exist yet (fresh DBs get UNIQUE from setup.py).
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='athlete_logins'"
        ).fetchone():
            return

        # IDEMPOTENCY: skip if a UNIQUE index on exactly (athlete_id) already exists.
        for idx in conn.execute("PRAGMA index_list(athlete_logins)").fetchall():
            if idx[2]:  # unique flag
                cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
                if cols == ["athlete_id"]:
                    return  # constraint already present — nothing to do

        # REBUILD. athlete_logins has an outgoing ON DELETE CASCADE FK to athletes,
        # so disable FK enforcement around the drop/rename. Toggle in autocommit
        # (isolation_level=None), wrap the rebuild in an explicit BEGIN/COMMIT so it
        # stays atomic, ROLLBACK on error, and always restore foreign_keys=ON.
        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN")
            conn.execute("""
                CREATE TABLE athlete_logins_new (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    email       TEXT UNIQUE NOT NULL,
                    athlete_id  INTEGER NOT NULL UNIQUE REFERENCES athletes(id) ON DELETE CASCADE,
                    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Row-preserving + dedup-safe: keep the earliest login per athlete_id.
            conn.execute("""
                INSERT INTO athlete_logins_new (id, email, athlete_id, created_at)
                SELECT id, email, athlete_id, created_at FROM athlete_logins
                WHERE id IN (SELECT MIN(id) FROM athlete_logins GROUP BY athlete_id)
            """)
            conn.execute("DROP TABLE athlete_logins")
            conn.execute("ALTER TABLE athlete_logins_new RENAME TO athlete_logins")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_athlete_logins_email ON athlete_logins(email)"
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
    finally:
        conn.close()
