"""
One-shot SQLite -> PostgreSQL DATA migration (migration/postgres-cloud-run).

Copies real production rows from the Fly SQLite database into the already-
migrated Postgres schema (db/postgres/001_baseline.sql). This is separate
from — and runs after — the schema migration (db/postgres_migrate.py) and
the catalog seeds (db/postgres_seeds.py), both of which must already have
been applied to the target database.

Design:
  - Table order is computed from Postgres's own FK graph (topological sort),
    not hand-maintained, so it stays correct if the schema changes.
  - Catalog/self-seeding tables (fueling_foods, report_config,
    legal_documents) are skipped — they're keyed by name/key, not id, and
    are already populated fresh by postgres_seeds.py; copying SQLite's
    id-keyed rows over them would misalign ids against what's already there.
  - admin_sessions (SQLite-only, dead — zero references in current backend
    code, superseded by the stateless HMAC admin-auth token) is skipped:
    it isn't in the Postgres schema at all, so it's naturally excluded.
  - Identity ("id") primary keys are preserved via OVERRIDING SYSTEM VALUE
    (required so FK references between tables stay valid), then every
    identity sequence is realigned to MAX(id)+1 after loading.
  - The two real Postgres BOOLEAN columns (parents.consent_confirmed,
    daily_targets.lea_alert) are coerced from SQLite's 0/1 INTEGER
    representation; every other column is copied as-is (TEXT timestamp
    columns are already SQLite-format-compatible — see sqlite_now()/
    sqlite_today() in 001_baseline.sql).
  - Safety guard: refuses to run if ANY table being migrated already has
    rows in the target — prevents an accidental double-run from duplicating
    data. Bypassable only with --force (never use against a database that
    already has real user data).
  - Whole run is one transaction. Default is a DRY RUN: everything executes
    and is verified, then rolled back. Pass --execute to actually commit.

Usage:
    # Dry run (default) — executes + verifies, then rolls back. Safe to run
    # against any target, including a database with real data (it only ever
    # reads from SQLite and rolls back the Postgres side).
    python -m db.migrate_sqlite_data --sqlite-path /path/to/fuelup.db

    # Real run — commits.
    python -m db.migrate_sqlite_data --sqlite-path /path/to/fuelup.db --execute

DATABASE_URL (or DB_USER/DB_NAME/INSTANCE_UNIX_SOCKET/DB_PASS) must already
point at the target Postgres database, same as every other script in db/.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict

from api.database import get_conn

# Catalog/reference tables that are already correctly seeded in Postgres by
# db/postgres_seeds.py, keyed by a natural key (name/key) rather than id.
# Copying SQLite's rows here would duplicate/misalign against the existing
# seed, not add real user data.
#
# health_checks, health_incidents, scheduler_heartbeats, knowledge_items,
# and knowledge_chunks are here for a related but distinct reason: they're
# state Cloud Run *generates itself* the moment it starts running (health
# probes, per-job heartbeats, and api/startup.py's automatic
# ensure_knowledge_ingested() re-ingesting the same bundled knowledge/*.md
# files SQLite's copy came from in the first place — confirmed live:
# Cloud SQL already has identical knowledge_items/knowledge_chunks counts
# to the SQLite snapshot). Copying Fly's historical snapshot of any of
# these over Cloud Run's own live-generated state would be actively wrong,
# not just redundant.
_SKIP_TABLES = {
    "fueling_foods", "report_config", "legal_documents",
    "health_checks", "health_incidents", "scheduler_heartbeats",
    "knowledge_items", "knowledge_chunks",
}

# The only two real `BOOLEAN` columns in the Postgres schema; every other
# column is copied through unchanged. (See db/postgres/001_baseline.sql —
# everything else is TEXT/INTEGER/REAL, matching SQLite's own storage.)
_BOOLEAN_COLUMNS = {
    ("parents", "consent_confirmed"),
    ("daily_targets", "lea_alert"),
}


def _pg_tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name != 'schema_migrations' "
        "ORDER BY table_name"
    ).fetchall()
    return [r["table_name"] for r in rows]


def _pg_columns(conn, table: str) -> list[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s "
        "ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    return [r["column_name"] for r in rows]


def _pg_identity_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND is_identity = 'YES'",
        (table,),
    ).fetchall()
    return {r["column_name"] for r in rows}


def _pg_fk_details(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _pg_fk_graph(fk_details: list[dict]) -> dict[str, set[str]]:
    """table -> set of tables it has a FK to (must be loaded first)."""
    graph: dict[str, set[str]] = defaultdict(set)
    for r in fk_details:
        if r["table_name"] != r["foreign_table"]:
            graph[r["table_name"]].add(r["foreign_table"])
    return graph


def _pg_fk_columns(fk_details: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """table -> [(local_column, foreign_table), ...]. Every FK target in this
    schema has 'id' as its primary key (verified — the handful of tables with
    a non-'id' PK are all leaf tables, never a FK target), so the referenced
    column is assumed to be 'id'."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in fk_details:
        out[r["table_name"]].append((r["column_name"], r["foreign_table"]))
    return out


def _topological_order(all_tables: list[str], graph: dict[str, set[str]]) -> list[str]:
    """Tables with no unresolved FK dependency first. Stable (alphabetical
    within a dependency tier) so re-runs produce identical, reviewable order."""
    remaining = set(all_tables)
    depends_on = {t: set(graph.get(t, set())) & remaining for t in remaining}
    ordered: list[str] = []
    while remaining:
        ready = sorted(t for t in remaining if not depends_on[t])
        if not ready:
            raise RuntimeError(f"FK cycle detected among: {sorted(remaining)}")
        for t in ready:
            ordered.append(t)
            remaining.discard(t)
        for t in remaining:
            depends_on[t] -= set(ready)
    return ordered


def _sqlite_table_names(sconn: sqlite3.Connection) -> set[str]:
    rows = sconn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'sqlite_sequence'"
    ).fetchall()
    return {r[0] for r in rows}


def run(sqlite_path: str, *, execute: bool, force: bool) -> None:
    sconn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    sconn.row_factory = sqlite3.Row
    sqlite_tables = _sqlite_table_names(sconn)

    pconn = get_conn()
    try:
        all_pg_tables = _pg_tables(pconn)
        fk_details = _pg_fk_details(pconn)
        graph = _pg_fk_graph(fk_details)
        fk_columns = _pg_fk_columns(fk_details)
        order = _topological_order(all_pg_tables, graph)
        plan = [t for t in order if t not in _SKIP_TABLES and t in sqlite_tables]
        skipped_no_sqlite = [t for t in order if t not in _SKIP_TABLES and t not in sqlite_tables]

        print(f"Source: {sqlite_path}")
        print(f"Tables to migrate ({len(plan)}): {', '.join(plan)}")
        print(f"Skipped (catalog/self-seeded): {', '.join(sorted(_SKIP_TABLES))}")
        if skipped_no_sqlite:
            print(f"Skipped (no matching SQLite table — Postgres-only): {', '.join(skipped_no_sqlite)}")
        print()

        # Safety guard: refuse if the target already has data in any table
        # we're about to load, unless --force.
        if not force:
            non_empty = []
            for t in plan:
                n = pconn.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()["n"]
                if n:
                    non_empty.append((t, n))
            if non_empty:
                detail = ", ".join(f"{t} ({n} rows)" for t, n in non_empty)
                raise RuntimeError(
                    f"Refusing to run — target already has data in: {detail}. "
                    "This looks like a re-run risking duplicate rows. Pass --force "
                    "only if you've confirmed that's actually intended."
                )

        sqlite_counts: dict[str, int] = {}
        inserted_counts: dict[str, int] = {}
        orphan_counts: dict[str, int] = {}
        loaded_ids: dict[str, set] = {}

        for table in plan:
            pg_cols = _pg_columns(pconn, table)
            identity_cols = _pg_identity_columns(pconn, table)
            table_fks = [(col, ft) for col, ft in fk_columns.get(table, []) if ft in loaded_ids]

            sqlite_col_rows = sconn.execute(f'PRAGMA table_info("{table}")').fetchall()
            sqlite_cols = {r[1] for r in sqlite_col_rows}
            cols = [c for c in pg_cols if c in sqlite_cols]
            missing = [c for c in pg_cols if c not in sqlite_cols]
            if missing:
                print(f"  NOTE {table}: Postgres-only columns left NULL (no SQLite source): {missing}")

            rows = sconn.execute(f'SELECT {", ".join(cols)} FROM "{table}"').fetchall()
            sqlite_counts[table] = len(rows)
            if not rows:
                inserted_counts[table] = 0
                orphan_counts[table] = 0
                if "id" in cols:
                    loaded_ids[table] = set()
                continue

            # Orphan guard: SQLite never enforced FK constraints, so a row can
            # reference a parent that was later deleted (confirmed live in
            # prod — e.g. shopping_list_items pointing at a since-deleted
            # shopping_lists row). Skip those rather than crash the whole run.
            good_rows = []
            skipped = 0
            for row in rows:
                orphaned = False
                for col, foreign_table in table_fks:
                    if col in cols:
                        v = row[col]
                        if v is not None and v not in loaded_ids[foreign_table]:
                            orphaned = True
                            break
                if orphaned:
                    skipped += 1
                else:
                    good_rows.append(row)
            orphan_counts[table] = skipped

            col_list = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            overriding = " OVERRIDING SYSTEM VALUE" if identity_cols & set(cols) else ""
            sql = f'INSERT INTO "{table}" ({col_list}){overriding} VALUES ({placeholders})'

            values = []
            for row in good_rows:
                out = []
                for c in cols:
                    v = row[c]
                    if (table, c) in _BOOLEAN_COLUMNS and v is not None:
                        v = bool(v)
                    out.append(v)
                values.append(tuple(out))

            if values:
                cur = pconn.cursor()
                cur.executemany(sql, values)
            inserted_counts[table] = len(values)

            if "id" in cols:
                id_idx = cols.index("id")
                loaded_ids[table] = {v[id_idx] for v in values}

            note = f", {skipped} orphaned (skipped)" if skipped else ""
            print(f"  {table}: {len(values)} rows{note}")

        total_orphaned = sum(orphan_counts.values())
        if total_orphaned:
            print(f"Orphaned rows skipped (FK pointed at a since-deleted parent — pre-existing "
                  f"data issue in the source SQLite DB, not introduced by this migration):")
            for t in plan:
                if orphan_counts.get(t):
                    print(f"  {t}: {orphan_counts[t]} of {sqlite_counts[t]}")
            print()

        print("Verifying row counts...")
        mismatches = []
        for table in plan:
            actual = pconn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"]
            expected = sqlite_counts[table] - orphan_counts.get(table, 0)
            if actual != expected:
                mismatches.append((table, expected, actual))
        if mismatches:
            raise RuntimeError(
                "Row count mismatch after load: "
                + ", ".join(f"{t} expected {e} got {a}" for t, e, a in mismatches)
            )
        print("All row counts match (accounting for skipped orphans above).")

        print()
        print("Realigning identity sequences...")
        for table in plan:
            identity_cols = _pg_identity_columns(pconn, table)
            for col in identity_cols:
                pconn.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence(%s, %s),
                        GREATEST(COALESCE((SELECT MAX("{col}") FROM "{table}"), 0), 1),
                        (SELECT MAX("{col}") FROM "{table}") IS NOT NULL
                    )
                    """,
                    (table, col),
                )
                print(f"  {table}.{col}")

        total = sum(inserted_counts.values())
        print()
        print(f"Total rows loaded: {total}")

        if execute:
            pconn.commit()
            print("COMMITTED.")
        else:
            pconn.rollback()
            print("DRY RUN — rolled back. Nothing was persisted. Pass --execute to commit for real.")
    finally:
        pconn.close()
        sconn.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", required=True, help="Path to the SQLite database file (read-only).")
    parser.add_argument("--execute", action="store_true", help="Actually commit. Default is dry-run (rollback).")
    parser.add_argument("--force", action="store_true", help="Bypass the non-empty-target safety guard.")
    args = parser.parse_args(argv)
    run(args.sqlite_path, execute=args.execute, force=args.force)


if __name__ == "__main__":
    main()
