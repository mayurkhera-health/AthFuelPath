"""
db/postgres_seeds.py — idempotent PostgreSQL data seeds (migration/postgres-cloud-run).

Ports the seed DATA (not the historical migration mechanics) that used to run
via api/services/db_migrations.py::run_all() and db/setup.py on every SQLite
boot:

  - report_config defaults      (was db_migrations.py::_create_report_config)
  - fueling_foods catalog       (was db/setup.py::seed_fueling_foods, from
                                  fueling_foods_seed.csv)
  - health_checks rows          (was db_migrations.py::_create_health_tables —
                                  one 'unknown' row per named check, so the
                                  admin System Health screen shows all checks
                                  before the first scheduled run)
  - launch articles             (db/seed_articles.py — already Postgres-ported
                                  in place; call db.seed_articles.run() directly,
                                  not duplicated here)

Fuel IQ lesson/quiz content is NOT seeded here — it's operator-run via
`python -m scripts.import_fueliq_lessons --file content/... [--approve]`
(that script's SQL lives in api/services/fueliq_service.py::import_lessons,
already ported to psycopg3/Postgres syntax as part of this migration). Content
import is a deliberate, reviewed action (review_status defaults to 'draft'),
not something that should happen silently on every deploy.

db/seed_test.py (fake test personas for local QA) is NOT run from here or from
app startup — it's a manual local-dev tool, not production seed data.

Usage:
    python -m db.postgres_seeds              # report_config + fueling_foods + articles
    python -m db.postgres_seeds --skip-articles
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from api.database import get_conn

_DEFAULT_REPORT_CONFIG = [
    # key, value, description — verbatim from api/services/db_migrations.py::_DEFAULT_CONFIG
    ("load_high_game_days",           3.0, "Game/tournament days per week that qualifies as high load"),
    ("prefuel_rate_low",              0.5, "Pre-fuel confirmation rate below which the safety flag can fire"),
    ("recovery_rate_low",             0.5, "Recovery confirmation rate below which the safety flag can fire"),
    ("hydration_rate_low",            0.5, "Hydration confirmation rate below which the safety flag can fire"),
    ("streak_min_confirms_per_day",   1.0, "Min confirmations in a day to count toward streak"),
    ("fueliq_lesson_points",         10.0, "Fuel IQ: points for completing a lesson"),
    ("fueliq_perfect_quiz_bonus",     5.0, "Fuel IQ: bonus for a 3/3 first-try quiz"),
    ("fueliq_streak_milestone_bonus", 15.0, "Fuel IQ: bonus for a 7-day streak milestone"),
    ("fueliq_review_points",          5.0, "Fuel IQ: points for a Refuel Your Brain review session"),
    ("fueliq_daily_challenge_points", 10.0, "Fuel IQ: points for completing the Daily Challenge"),
]

# Verbatim from api/services/db_migrations.py::_HEALTH_CHECK_NAMES.
_HEALTH_CHECK_NAMES = [
    "bedrock_ping", "bedrock_inference", "gmail_smtp", "db_writable", "disk_space",
    "scheduler_notifications", "scheduler_calendar_sync", "calendar_sync_systemic",
    "expo_push",
]


def seed_report_config(conn) -> int:
    """INSERT OR IGNORE equivalent — never overwrites an operator-tuned value."""
    inserted = 0
    for key, value, description in _DEFAULT_REPORT_CONFIG:
        cur = conn.execute(
            """
            INSERT INTO report_config (key, value, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO NOTHING
            """,
            (key, value, description),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def seed_health_checks(conn) -> int:
    """INSERT OR IGNORE equivalent — one 'unknown' row per named check, so all
    9 show up in the admin System Health screen before the first run."""
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO health_checks (check_name, status) VALUES (%s, 'unknown') "
        "ON CONFLICT (check_name) DO NOTHING",
        [(n,) for n in _HEALTH_CHECK_NAMES],
    )
    inserted = cur.rowcount
    conn.commit()
    return inserted


def seed_fueling_foods(conn=None) -> int:
    """UPSERT fueling_foods from fueling_foods_seed.csv. Idempotent — updates
    existing rows by name (ported from db/setup.py::seed_fueling_foods)."""
    csv_path = Path(__file__).resolve().parent.parent / "fueling_foods_seed.csv"
    if not csv_path.exists():
        print(f"Seeder: {csv_path} not found — skipping.")
        return 0

    _own_conn = conn is None
    if _own_conn:
        conn = get_conn()

    count = 0
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
                    ON CONFLICT (name) DO UPDATE SET
                        category      = EXCLUDED.category,
                        role          = EXCLUDED.role,
                        allergen_tags = EXCLUDED.allergen_tags,
                        soft_hint     = EXCLUDED.soft_hint,
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
                count += 1
        conn.commit()
        print(f"Seeder: fueling_foods upserted from {csv_path.name} ({count} rows)")
    finally:
        if _own_conn:
            conn.close()
    return count


def run_seeds(*, skip_articles: bool = False) -> None:
    conn = get_conn()
    try:
        n = seed_report_config(conn)
        print(f"report_config: {n} new default(s) inserted (existing keys untouched).")
        seed_health_checks(conn)
        seed_fueling_foods(conn)
    finally:
        conn.close()

    if not skip_articles:
        from db.seed_articles import run as seed_articles_run
        seed_articles_run()


if __name__ == "__main__":
    run_seeds(skip_articles="--skip-articles" in sys.argv)
