import pytest
from db.setup import init_db
from api.database import get_conn


def test_teamcoach_tables_exist():
    init_db()
    conn = get_conn()
    try:
        tables = {r["table_name"] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()}
        for t in ["coaches", "teams", "coach_team_access",
                  "roster_membership", "fueling_window_log",
                  "team_engagement_snapshot"]:
            assert t in tables, f"Missing table: {t}"
    finally:
        conn.close()


def test_coaches_has_auth_columns():
    conn = get_conn()
    try:
        cols = {r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'coaches'"
        ).fetchall()}
        for c in ["id", "name", "email", "auth_provider_id", "password_hash", "salt"]:
            assert c in cols, f"coaches missing column: {c}"
    finally:
        conn.close()


def test_teams_has_threshold_and_club_id():
    conn = get_conn()
    try:
        cols = {r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'teams'"
        ).fetchall()}
        assert "threshold_pct" in cols
        assert "club_id" in cols
    finally:
        conn.close()


def test_fueling_window_log_uses_date_column():
    conn = get_conn()
    try:
        cols = {r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'fueling_window_log'"
        ).fetchall()}
        assert "date" in cols
        assert "log_date" not in cols
    finally:
        conn.close()
