# db/setup.py
import os
import sqlite3
from pathlib import Path

# When DB_PATH=:memory: (used in tests), the SQLite shared-cache in-memory
# database is destroyed as soon as all connections to it are closed.  We keep
# a module-level connection open so the DB survives across get_conn() calls.
# _persistent_memory_uri tracks which named URI _persistent_memory_conn is open
# against; when tests/conftest.py switches to a new URI per module, init_db()
# closes the old conn and opens a fresh one.
_persistent_memory_conn = None
_persistent_memory_uri = None


def init_db():
    # RETIRED on migration/postgres-cloud-run: api/database.py is
    # PostgreSQL-only now, so the sqlite3.connect() calls below would fail
    # immediately. Kept as a no-op (not deleted) purely so the ~50 test
    # files that still call `from db.setup import init_db; init_db()` keep
    # working unmodified — tests/conftest.py's fixtures own schema/seed
    # setup now (db/postgres_migrate.py + db/postgres_seeds.py).
    return
    global _persistent_memory_conn, _persistent_memory_uri
    db_path = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "fuelup.db"))
    if db_path == ":memory:":
        from api import database as _dbmod
        target_uri = _dbmod._test_db_uri or "file::memory:?cache=shared"
        if _persistent_memory_conn is not None and _persistent_memory_uri != target_uri:
            _persistent_memory_conn.close()
            _persistent_memory_conn = None
            _persistent_memory_uri = None
        if _persistent_memory_conn is None:
            _persistent_memory_conn = sqlite3.connect(
                target_uri, uri=True, check_same_thread=False
            )
            _persistent_memory_uri = target_uri
        conn = _persistent_memory_conn
    else:
        conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS parents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            consent_timestamp TEXT NOT NULL,
            consent_confirmed BOOLEAN DEFAULT FALSE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS athletes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES parents(id),
            first_name TEXT NOT NULL,
            age INTEGER NOT NULL,
            date_of_birth TEXT NULL,
            gender TEXT NOT NULL,
            weight_lbs REAL NOT NULL,
            height_ft INTEGER NOT NULL,
            height_in REAL NOT NULL,
            position TEXT,
            competition_level TEXT,
            sweat_profile TEXT,
            allergies TEXT,
            dietary_restrictions TEXT,
            supplement_use TEXT,
            blueprint_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER REFERENCES athletes(id),
            event_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            start_time TEXT,
            duration_hours REAL,
            city TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER REFERENCES athletes(id),
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            log_method TEXT NOT NULL,
            description TEXT,
            calories REAL,
            carbs_g REAL,
            protein_g REAL,
            fat_g REAL,
            iron_mg REAL,
            calcium_mg REAL,
            water_oz REAL,
            edamam_raw TEXT
        );

        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER REFERENCES athletes(id),
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            remind_pregame_meal INTEGER DEFAULT 1,
            remind_pregame_snack INTEGER DEFAULT 1,
            remind_meal_log INTEGER DEFAULT 1,
            remind_hydration INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, endpoint)
        );

        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            plan_date  TEXT NOT NULL,
            slot_name  TEXT NOT NULL,
            recipe_id  TEXT,
            recipe_name TEXT,
            calories   REAL,
            carbs_g    REAL,
            protein_g  REAL,
            fat_g      REAL,
            is_ai_generated INTEGER DEFAULT 0,
            logged     INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, plan_date, slot_name)
        );

        CREATE INDEX IF NOT EXISTS idx_meal_plans_athlete_date
            ON meal_plans(athlete_id, plan_date);

        CREATE TABLE IF NOT EXISTS daily_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER REFERENCES athletes(id),
            target_date TEXT NOT NULL,
            event_type TEXT,
            total_calories INTEGER,
            carbs_g_min INTEGER,
            carbs_g_max INTEGER,
            protein_g_min INTEGER,
            protein_g_max INTEGER,
            fat_g_min INTEGER,
            fat_g_max INTEGER,
            iron_mg INTEGER,
            calcium_mg INTEGER,
            hydration_oz_min INTEGER,
            hydration_oz_max INTEGER,
            lea_alert BOOLEAN,
            targets_raw TEXT
        );

        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_otp_parent
            ON otp_codes(parent_id, used, expires_at);

        CREATE TABLE IF NOT EXISTS water_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER REFERENCES athletes(id),
            log_date TEXT NOT NULL,
            cups INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, log_date)
        );

        CREATE TABLE IF NOT EXISTS legal_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            source TEXT,
            source_urls TEXT,
            last_reviewed_date TEXT,
            organization TEXT,
            applicable_age_range TEXT,
            tags TEXT,
            review_status TEXT DEFAULT 'draft',
            version INTEGER DEFAULT 1,
            file_path TEXT NOT NULL,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER REFERENCES knowledge_items(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            heading TEXT,
            content TEXT NOT NULL,
            embedding TEXT,
            embedding_model TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_item
            ON knowledge_chunks(item_id);

        CREATE INDEX IF NOT EXISTS idx_knowledge_items_status
            ON knowledge_items(review_status);

        CREATE TABLE IF NOT EXISTS meal_plan_selections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            plan_date   TEXT NOT NULL,
            window_key  TEXT NOT NULL,
            item_text   TEXT NOT NULL,
            recipe_json TEXT,
            added_by    TEXT NOT NULL DEFAULT 'parent',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_meal_plan_selections_athlete_date
            ON meal_plan_selections(athlete_id, plan_date);

        CREATE TABLE IF NOT EXISTS articles (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT NOT NULL,
            summary          TEXT NOT NULL,
            body_markdown    TEXT NOT NULL,
            category         TEXT NOT NULL,
            audience         TEXT DEFAULT 'both',
            read_time_min    INTEGER NOT NULL,
            author           TEXT DEFAULT 'Purvi Shah MS RDN',
            science_source   TEXT,
            published_date   TEXT NOT NULL,
            is_active        INTEGER DEFAULT 1,
            created_at       TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS athlete_article_picks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id       INTEGER NOT NULL REFERENCES athletes(id),
            article_id       INTEGER NOT NULL REFERENCES articles(id),
            week_start       TEXT NOT NULL,
            alex_reason      TEXT NOT NULL,
            generated_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, article_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS athlete_logins (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            athlete_id  INTEGER NOT NULL UNIQUE REFERENCES athletes(id) ON DELETE CASCADE,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_athlete_logins_email
            ON athlete_logins(email);

        CREATE TABLE IF NOT EXISTS fueling_foods (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL UNIQUE,
            category     TEXT NOT NULL,
            role         TEXT,
            allergen_tags TEXT DEFAULT '',
            soft_hint    TEXT DEFAULT '',
            is_active    INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS athlete_food_prefs (
            athlete_id   INTEGER NOT NULL,
            food_name    TEXT NOT NULL,
            preference   TEXT NOT NULL,
            category     TEXT,
            PRIMARY KEY (athlete_id, food_name)
        );

        CREATE TABLE IF NOT EXISTS shopping_lists (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id   INTEGER NOT NULL,
            week_start   TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS shopping_list_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id      INTEGER NOT NULL,
            name         TEXT NOT NULL,
            category     TEXT NOT NULL,
            source       TEXT NOT NULL DEFAULT 'suggested',
            checked      INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (list_id) REFERENCES shopping_lists(id)
        );

        CREATE TABLE IF NOT EXISTS food_submissions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT NOT NULL,
            suggested_category TEXT,
            submitted_by       INTEGER NOT NULL,
            status             TEXT NOT NULL DEFAULT 'pending',
            created_at         TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notification_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL,
            window_key  TEXT NOT NULL,
            send_date   TEXT NOT NULL,
            recipient   TEXT NOT NULL DEFAULT 'athlete',
            token       TEXT NOT NULL,
            sent_at     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (athlete_id, window_key, send_date, recipient)
        );
    """)

    # Lightweight migrations for existing databases
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(knowledge_items)")}
    if "organization" not in cols:
        cursor.execute("ALTER TABLE knowledge_items ADD COLUMN organization TEXT")

    conn.commit()

    # One-time migration: purge meal_plans rows written by the legacy
    # compute_meal_slots engine (slot names used hyphens, e.g. "pre-game-fuel").
    # The canonical window_templates engine uses underscores ("pre_event_meal").
    # Safe to re-run — no-op once all rows are clean.
    conn.execute("DELETE FROM meal_plans WHERE slot_name LIKE '%-%'")
    conn.commit()

    # Seed the curated food catalog (idempotent UPSERT — safe on every startup).
    seed_fueling_foods(conn)

    # Do NOT close _persistent_memory_conn — closing it would destroy the
    # shared-cache in-memory database (used in tests).
    if conn is not _persistent_memory_conn:
        conn.close()
    print("AthFuelPath database initialized.")

def seed_fueling_foods(conn=None):
    """
    UPSERT fueling_foods from fueling_foods_seed.csv.
    Idempotent — safe to re-run; updates existing rows by name.
    Pass an existing conn for tests; omit for production (uses get_conn()).
    """
    import csv
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent / "fueling_foods_seed.csv"
    if not csv_path.exists():
        print(f"Seeder: {csv_path} not found — skipping.")
        return

    _own_conn = conn is None
    if _own_conn:
        from api.database import get_conn as _get_conn
        conn = _get_conn()

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["name"].strip()
                category = row["category"].strip()
                if not name or not category:
                    print(f"Seeder: skipping row with missing name/category: {dict(row)}")
                    continue
                conn.execute(
                    """
                    INSERT INTO fueling_foods (name, category, role, allergen_tags, soft_hint, is_active)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    ON CONFLICT(name) DO UPDATE SET
                        category      = excluded.category,
                        role          = excluded.role,
                        allergen_tags = excluded.allergen_tags,
                        soft_hint     = excluded.soft_hint,
                        is_active     = 1
                    """,
                    (
                        name,
                        category,
                        row.get("role", "").strip() or None,
                        row.get("allergen_tags", "").strip(),
                        row.get("soft_hint", "").strip(),
                    ),
                )
        conn.commit()
        print(f"Seeder: fueling_foods upserted from {csv_path.name}")
    finally:
        if _own_conn:
            conn.close()


if __name__ == "__main__":
    init_db()
