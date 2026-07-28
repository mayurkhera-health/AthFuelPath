"""Regression test for H25: get_read_conn() used to ignore _test_db_uri and
always hit a fixed shared in-memory DB, so in tests it read a different
(empty) database than whatever get_conn() had just written to — causing
TeamCoach's entire dashboard test suite (including its BOLA and
no-nutrition-leak tests) to fail with "no such table" under the test
suite's real per-module isolation mode (DB_PATH=":memory:")."""
import os
os.environ["DB_PATH"] = ":memory:"

from api import database as _dbmod
from api.database import get_conn, get_read_conn


def test_get_read_conn_honors_test_db_uri_like_get_conn_does():
    _dbmod._test_db_uri = "file:h25_isolation_test?mode=memory&cache=shared"
    try:
        w = get_conn()
        w.execute("CREATE TABLE IF NOT EXISTS h25_probe (id INTEGER)")
        w.execute("INSERT INTO h25_probe (id) VALUES (1)")
        w.commit()

        r = get_read_conn()
        row = r.execute("SELECT id FROM h25_probe").fetchone()
        r.close()
        w.close()

        assert row is not None
        assert row["id"] == 1
    finally:
        _dbmod._test_db_uri = None
