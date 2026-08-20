"""
PostgreSQL connection layer (migration/postgres-cloud-run).

Replaces the sqlite3-backed api/database.py. Deliberately preserves the
existing calling convention used across ~70 route/service files:

    conn = get_conn()
    row = conn.execute("SELECT ... WHERE id = %s", (id,)).fetchone()
    row["some_column"]
    conn.commit()
    conn.close()

psycopg3's Connection.execute() is itself a convenience method (mirrors
sqlite3.Connection.execute()) that opens a cursor, executes, and returns it —
so callers do not need to switch to an explicit cursor() dance. Combined with
the dict_row row factory (rows come back as real dicts), `row["id"]` and
`dict(row)` keep working unchanged. This is why the migration can stay a
placeholder/construct-syntax port instead of an API-shape rewrite.

Two connection modes, selected at import/call time by environment:

  LOCAL / CI:  DATABASE_URL              (standard libpq connection string /
                                           postgres:// URL)
  CLOUD RUN:   DB_USER, DB_PASS, DB_NAME, INSTANCE_UNIX_SOCKET
               (DB_PASS may be unset for peer/trust local dev setups)

DB_PATH is not used in PostgreSQL mode and is intentionally not read here.
"""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

# Fail fast rather than hang if Cloud SQL / the DB is unreachable.
CONNECT_TIMEOUT_SECONDS = 10


def _conninfo() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    db_user = os.getenv("DB_USER")
    db_name = os.getenv("DB_NAME")
    unix_socket = os.getenv("INSTANCE_UNIX_SOCKET")
    db_pass = os.getenv("DB_PASS")

    if not (db_user and db_name and unix_socket):
        raise RuntimeError(
            "Database is not configured. Set DATABASE_URL (local/CI), or "
            "DB_USER + DB_NAME + INSTANCE_UNIX_SOCKET (+ DB_PASS) for Cloud Run. "
            "DB_PATH/SQLite is no longer supported."
        )

    # libpq accepts a Unix-socket directory as `host=` — psycopg passes this
    # straight through. This matches the documented Cloud Run + Cloud SQL
    # Auth Proxy sidecar / socket-mount pattern:
    #   host=/cloudsql/<project>:<region>:<instance>
    parts = [f"host={unix_socket}", f"dbname={db_name}", f"user={db_user}"]
    if db_pass:
        parts.append(f"password={db_pass}")
    return " ".join(parts)


def get_conn() -> psycopg.Connection:
    """Read/write connection. Rows come back as dicts (psycopg dict_row)."""
    return psycopg.connect(
        _conninfo(),
        row_factory=dict_row,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        autocommit=False,
    )


def get_read_conn() -> psycopg.Connection:
    """Read-only connection for TeamCoach request handlers (mirrors the old
    SQLite ?mode=ro connection). Enforced at the session level via
    default_transaction_read_only, so an accidental write raises instead of
    silently succeeding. Never call conn.commit() on this connection."""
    return psycopg.connect(
        _conninfo(),
        row_factory=dict_row,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        autocommit=False,
        options="-c default_transaction_read_only=on",
    )


def db_is_ready() -> bool:
    """Lightweight liveness check for GET /ready. Returns False instead of
    raising so the route can report status without a 500."""
    try:
        conn = get_conn()
        try:
            conn.execute("SELECT 1")
            return True
        finally:
            conn.close()
    except Exception:
        return False
