"""
db/postgres_migrate.py — PostgreSQL migration runner (migration/postgres-cloud-run).

Applies db/postgres/NNN_*.sql files in ascending version order, tracked in a
schema_migrations table. Does NOT run the legacy SQLite api/services/
db_migrations.py — that file is retired for PostgreSQL entirely. All future
schema changes are new 002_*.sql, 003_*.sql, ... files in db/postgres/.

Guarantees:
  - each migration file runs inside its own transaction; a failure rolls
    back that file's changes and stops immediately (never continues past a
    failed migration)
  - already-applied versions are skipped — safe to run repeatedly
  - a Postgres advisory lock serializes concurrent runs (e.g. two deploys
    racing, or a deploy racing a manual invocation)

Usage:
    python -m db.postgres_migrate
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from api.database import get_conn

MIGRATIONS_DIR = Path(__file__).resolve().parent / "postgres"

# Arbitrary fixed 32-bit key for this app's migration advisory lock. Only
# needs to be unique within a Postgres instance/session-lock namespace, not
# globally — any stable constant is fine.
ADVISORY_LOCK_KEY = 727384910

_FILE_RE = re.compile(r"^(\d+)_.*\.sql$")


class MigrationError(RuntimeError):
    pass


def _discover_migrations() -> list[tuple[int, Path]]:
    if not MIGRATIONS_DIR.is_dir():
        raise MigrationError(f"Migrations directory not found: {MIGRATIONS_DIR}")

    files: list[tuple[int, Path]] = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _FILE_RE.match(p.name)
        if not m:
            raise MigrationError(
                f"Migration file does not match the required 'NNN_name.sql' "
                f"naming pattern: {p.name}"
            )
        files.append((int(m.group(1)), p))

    files.sort(key=lambda t: t[0])
    versions = [v for v, _ in files]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"Duplicate migration version numbers in {MIGRATIONS_DIR}")
    if not files:
        raise MigrationError(f"No migration files found in {MIGRATIONS_DIR}")
    return files


def _ensure_schema_migrations_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            filename   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def run_migrations(*, quiet: bool = False) -> list[int]:
    """Apply all pending migrations in order. Returns the list of versions
    applied during this call (empty list if the database was already up to
    date). Raises MigrationError (or re-raises the underlying DB error) and
    stops on the first failure — a failed migration is never silently
    skipped or continued past."""

    def log(msg: str) -> None:
        if not quiet:
            print(msg)

    migrations = _discover_migrations()

    conn = get_conn()
    applied_this_run: list[int] = []
    try:
        _ensure_schema_migrations_table(conn)

        conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        conn.commit()
        try:
            already = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }

            for version, path in migrations:
                if version in already:
                    continue

                log(f"Applying {path.name} ...")
                sql = path.read_text()
                try:
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s)",
                        (version, path.name),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    log(f"FAILED applying {path.name} — rolled back. Stopping; no later migrations were run.")
                    raise
                applied_this_run.append(version)
                log(f"Applied {path.name} (version {version})")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
            conn.commit()
    finally:
        conn.close()

    return applied_this_run


def latest_applied_version() -> int | None:
    """Highest applied migration version, or None if the schema_migrations
    table doesn't exist yet / is empty. Used by GET /ready."""
    try:
        conn = get_conn()
    except Exception:
        return None
    try:
        row = conn.execute(
            """
            SELECT max(version) AS v FROM schema_migrations
            WHERE EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'schema_migrations'
            )
            """
        ).fetchone()
        return row["v"] if row else None
    except Exception:
        return None
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        applied = run_migrations()
    except Exception as exc:
        print(f"Migration run FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    if applied:
        print(f"Done. Applied {len(applied)} migration(s): {applied}")
    else:
        print("Already up to date. No migrations applied.")
