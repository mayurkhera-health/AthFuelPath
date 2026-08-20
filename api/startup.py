"""
App startup (migration/postgres-cloud-run): DB readiness check + knowledge
ingest. Schema creation/migration is NOT the API's job anymore — the app
ASSUMES db/postgres_migrate.py has already been run successfully against the
target database (by the deploy pipeline / operator), same as any normal
production service. If the schema isn't there, startup fails loudly instead
of silently trying to create it and serving traffic against a wrong/partial
schema.

This intentionally removes the old SQLite-era behavior of
_ensure_knowledge_tables()/PRAGMA-based ALTER TABLE column patching at every
boot — that responsibility now lives entirely in db/postgres/NNN_*.sql.
"""

from __future__ import annotations

import logging
from pathlib import Path

from api.database import get_conn
from db.postgres_migrate import latest_applied_version

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


class StartupError(RuntimeError):
    """Raised when the app cannot safely serve traffic. Startup must fail
    loudly on this — never log-and-continue for a DB/schema problem."""


def verify_db_ready() -> None:
    """Fail loudly if the database is unreachable or hasn't been migrated.
    This is the Cloud Run equivalent of the old 'just create tables if
    missing' behavior — except now a missing schema is treated as a
    deployment error, not something the API process should paper over."""
    try:
        conn = get_conn()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:
        raise StartupError(f"Database is not reachable: {exc}") from exc

    version = latest_applied_version()
    if version is None:
        raise StartupError(
            "No applied migrations found (schema_migrations is empty or missing). "
            "Run `python -m db.postgres_migrate` against this database before starting the API."
        )
    logger.info("Database ready — schema_migrations at version %s", version)


def ensure_knowledge_ingested(force: bool = False) -> None:
    """
    Ingest bundled knowledge/*.md into the database.
    Skips when approved chunks already exist unless force=True.
    Non-critical: a failure here logs and does not block startup (matches
    prior behavior — see run_startup()'s try/except).
    """
    from api.services.knowledge.ingest import ingest_all

    if not KNOWLEDGE_DIR.is_dir():
        logger.warning("Knowledge directory missing: %s", KNOWLEDGE_DIR)
        return

    conn = get_conn()
    try:
        chunk_count = conn.execute(
            """SELECT COUNT(*) AS count FROM knowledge_chunks kc
               JOIN knowledge_items ki ON kc.item_id = ki.id
               WHERE ki.review_status = 'approved'"""
        ).fetchone()["count"]
    finally:
        conn.close()

    if chunk_count > 0 and not force:
        logger.info("Knowledge already ingested (%s approved chunks)", chunk_count)
        return

    results = ingest_all(str(KNOWLEDGE_DIR))
    ok = [r for r in results if r.get("status") == "ok"]
    skipped = [r for r in results if r.get("status") == "skipped"]
    errors = [r for r in results if r.get("status") == "error"]
    total_chunks = sum(r.get("chunks", 0) for r in ok)
    logger.info(
        "Knowledge ingest: %s files, %s chunks (%s skipped, %s errors)",
        len(ok), total_chunks, len(skipped), len(errors),
    )
    for err in errors:
        logger.error("Knowledge ingest error: %s", err)


def ensure_knowledge_embeddings() -> None:
    """Backfill embeddings for ingested chunks missing vectors. Non-critical."""
    from api.services.knowledge.retrieval import backfill_missing_embeddings

    try:
        updated = backfill_missing_embeddings()
        if updated:
            logger.info("Backfilled embeddings for %s knowledge chunks", updated)
    except Exception:
        logger.exception("Knowledge embedding backfill failed")


def run_startup() -> None:
    """Called once when the API process starts.

    verify_db_ready() is CRITICAL — its exception is allowed to propagate and
    stop the process (see api/main.py's lifespan, which no longer swallows
    startup exceptions the way the old SQLite version did). Knowledge
    ingest/embeddings remain best-effort/non-critical, matching prior
    behavior — the app can serve fueling/schedule/etc. traffic even if the
    knowledge base isn't ready yet.
    """
    verify_db_ready()

    try:
        ensure_knowledge_ingested()
        ensure_knowledge_embeddings()
    except Exception:
        logger.exception("Knowledge ingest/embeddings failed — coach knowledge base may be unavailable")
