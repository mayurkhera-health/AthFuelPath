import os
os.environ["DB_PATH"] = ":memory:"

from db.setup import init_db
from api.database import get_conn
from api.services.db_migrations import run_all


def test_instacart_handoff_feedback_table_exists():
    keepalive = get_conn()
    init_db()
    run_all()
    row = get_conn().execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'instacart_handoff_feedback'"
    ).fetchone()
    assert row is not None
    keepalive.close()


def test_instacart_handoff_feedback_columns():
    keepalive = get_conn()
    init_db()
    run_all()
    cols = {r["column_name"] for r in get_conn().execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'instacart_handoff_feedback'"
    ).fetchall()}
    assert cols == {"id", "athlete_id", "outcome", "would_use_again", "comment", "created_at"}
    keepalive.close()
