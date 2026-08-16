# Admin Module — Phase 1 (User Administration + Analytics Emit Helper) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an internal admin console + guarded `/api/admin/*` API that replaces SSH-SQL for user administration (users, families/relationships, invites, status changes, audit log), plus a non-blocking `analytics.emit()` helper that starts accruing product-analytics data immediately.

**Architecture:** Additive only. New tables created via the existing idempotent `db_migrations._create_*` pattern; one new `api/routes/admin.py` router behind a single `require_admin` dependency; admin identity via email-OTP login issuing a revocable server-side session token (`admin_sessions` row keyed by `sha256(token)`); a new `/admin` SPA console reusing the existing `window.location.pathname` admin-route precedent. No new infrastructure — same FastAPI process, same SQLite file, same Fly.io VM.

**Tech Stack:** FastAPI, raw `sqlite3` (no ORM), Pydantic, APScheduler (existing), Gmail SMTP via `email_service.send_email`, React (Vite) SPA, pytest + `fastapi.testclient.TestClient`.

**Scope:** This plan is **Phase 1 + the emit helper** from [docs/ADMIN_MODULE_DESIGN.md](../../ADMIN_MODULE_DESIGN.md). The analytics **dashboards/AI-insights** (Phase 2) and **extra roles/MFA** (Phase 3) are separate follow-on plans. The `analytics_events` table and `emit()` helper land here (cheap; starts data flowing), but no analytics dashboards are built yet.

---

## File Structure

**Backend — new files**
| File | Responsibility |
|---|---|
| `api/services/admin_auth.py` | OTP hash, token mint/verify, `require_admin` + `require_role` FastAPI dependencies, env bootstrap of first admins |
| `api/services/admin_service.py` | User/family/invite reads, relationship-flag derivation, status writes, `audit()` helper |
| `api/services/analytics_service.py` | `emit()` non-blocking event insert |
| `api/routes/admin.py` | All `/api/admin/*` endpoints + the public `/api/events` collector |
| `tests/test_admin_migrations.py` | Schema/column creation tests |
| `tests/test_admin_auth.py` | OTP + token + guard unit/integration tests |
| `tests/test_admin_service.py` | User/family/invite/status/audit logic tests |
| `tests/test_admin_routes.py` | End-to-end route tests through `TestClient` |
| `tests/test_analytics_service.py` | `emit()` behavior + failure isolation tests |

**Backend — modified files**
| File | Change |
|---|---|
| `api/services/db_migrations.py` | New `_create_*` functions + additive `status` columns; wire into `run_all()` |
| `api/models.py` | New Pydantic request/response models for admin |
| `api/main.py` | Register `admin.router`; call admin env-bootstrap at startup |

**Frontend — new files**
| File | Responsibility |
|---|---|
| `frontend/src/pages/admin/AdminApp.jsx` | Admin SPA entry: auth gate + tab shell |
| `frontend/src/pages/admin/adminApi.js` | Fetch wrapper that attaches the bearer token + handles 401 |
| `frontend/src/pages/admin/AdminLogin.jsx` | Email-OTP login form |
| `frontend/src/pages/admin/Dashboard.jsx` | KPI tiles + "needs attention" |
| `frontend/src/pages/admin/Users.jsx` | Users table + filters + detail modal |
| `frontend/src/pages/admin/Families.jsx` | Master–detail relationship view |
| `frontend/src/pages/admin/Invites.jsx` | Invites table + resend |
| `frontend/src/pages/admin/AuditLog.jsx` | Audit table |

**Frontend — modified files**
| File | Change |
|---|---|
| `frontend/src/App.jsx` | Add `/admin` path → render `AdminApp` (alongside existing `/admin/library`) |

---

## Conventions for every backend task (read once)

- DB access: `conn = get_conn()` … `try: … conn.commit() … finally: conn.close()`. Always `?`-parameterized.
- Tests that need the full app use this fixture pattern (mirrors `tests/test_support_route.py`):
  ```python
  import os
  os.environ["DB_PATH"] = ":memory:"
  import pytest
  from fastapi.testclient import TestClient
  from db.setup import init_db
  from api.services.db_migrations import run_all
  from api.database import get_conn
  from api.main import app
  ```
- Migration unit tests use a bare `sqlite3.connect(":memory:")` and call the `_create_*(conn)` function directly (mirrors `tests/test_streak_service.py::test_streak_state_table_is_created`).
- Run the whole suite with: `source venv/bin/activate && pytest -q`.

---

## Task 1: Migrations — admin & analytics tables

**Files:**
- Modify: `api/services/db_migrations.py` (add functions; wire into `run_all()`)
- Test: `tests/test_admin_migrations.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_migrations.py`:
```python
import sqlite3
from api.services.db_migrations import (
    _create_admin_users, _create_admin_otp_codes, _create_admin_sessions,
    _create_invites, _create_admin_audit_log, _create_analytics_events,
    _add_status_columns,
)


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_admin_users_table():
    c = _conn(); _create_admin_users(c)
    assert _cols(c, "admin_users") == {
        "id", "email", "full_name", "role", "is_active", "last_login_at", "created_at"}


def test_admin_otp_codes_table():
    c = _conn(); _create_admin_users(c); _create_admin_otp_codes(c)
    assert _cols(c, "admin_otp_codes") == {
        "id", "admin_id", "code_hash", "expires_at", "used", "created_at"}


def test_admin_sessions_table():
    c = _conn(); _create_admin_users(c); _create_admin_sessions(c)
    assert _cols(c, "admin_sessions") == {
        "token_hash", "admin_id", "expires_at", "created_at"}


def test_invites_table():
    c = _conn(); _create_invites(c)
    assert _cols(c, "invites") == {
        "id", "kind", "parent_id", "athlete_id", "email", "status",
        "sent_at", "accepted_at", "expires_at", "reminder_count",
        "last_reminded_at", "created_at"}


def test_audit_log_table():
    c = _conn(); _create_admin_users(c); _create_admin_audit_log(c)
    assert _cols(c, "admin_audit_log") == {
        "id", "actor_admin_id", "action", "target_type", "target_id",
        "reason", "meta_json", "created_at"}


def test_analytics_events_table():
    c = _conn(); _create_analytics_events(c)
    assert _cols(c, "analytics_events") == {
        "id", "event_name", "ts", "actor_role", "parent_id", "athlete_id",
        "session_id", "screen", "feature", "props_json"}


def test_add_status_columns_is_idempotent():
    c = _conn()
    c.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY, email TEXT)")
    c.execute("CREATE TABLE athletes (id INTEGER PRIMARY KEY, parent_id INTEGER)")
    _add_status_columns(c)
    _add_status_columns(c)  # second call must not raise
    assert {"status", "deactivated_at"} <= _cols(c, "parents")
    assert {"status", "deactivated_at"} <= _cols(c, "athletes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_admin_migrations.py -q`
Expected: FAIL — `ImportError: cannot import name '_create_admin_users'`.

- [ ] **Step 3: Add the migration functions**

Append to `api/services/db_migrations.py` (after `_create_coach_feedback`):
```python
def _create_admin_users(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT    NOT NULL UNIQUE,
            full_name     TEXT,
            role          TEXT    NOT NULL DEFAULT 'admin',
            is_active     INTEGER NOT NULL DEFAULT 1,
            last_login_at TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _create_admin_otp_codes(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_otp_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            code_hash  TEXT    NOT NULL,
            expires_at TEXT    NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_admin_otp
            ON admin_otp_codes (admin_id, used, expires_at)
    """)


def _create_admin_sessions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            token_hash TEXT    PRIMARY KEY,
            admin_id   INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            expires_at TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _create_invites(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invites (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kind            TEXT    NOT NULL,
            parent_id       INTEGER REFERENCES parents(id),
            athlete_id      INTEGER REFERENCES athletes(id),
            email           TEXT,
            status          TEXT    NOT NULL DEFAULT 'pending',
            sent_at         TEXT,
            accepted_at     TEXT,
            expires_at      TEXT,
            reminder_count  INTEGER NOT NULL DEFAULT 0,
            last_reminded_at TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _create_admin_audit_log(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_admin_id INTEGER REFERENCES admin_users(id),
            action         TEXT    NOT NULL,
            target_type    TEXT,
            target_id      INTEGER,
            reason         TEXT,
            meta_json      TEXT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _create_analytics_events(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name  TEXT    NOT NULL,
            ts          TEXT    NOT NULL DEFAULT (datetime('now')),
            actor_role  TEXT,
            parent_id   INTEGER,
            athlete_id  INTEGER,
            session_id  TEXT,
            screen      TEXT,
            feature     TEXT,
            props_json  TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ae_name_ts ON analytics_events (event_name, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ae_athlete_ts ON analytics_events (athlete_id, ts)")


def _add_status_columns(conn):
    """Additive nullable status columns on parents + athletes. Idempotent: guarded
    by PRAGMA table_info, same pattern as _add_intensity_to_events."""
    for table in ("parents", "athletes"):
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "status" not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN status TEXT")
        if "deactivated_at" not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN deactivated_at TEXT")
```

- [ ] **Step 4: Wire into `run_all()`**

In `api/services/db_migrations.py`, inside `run_all()`'s `try:` block, after `_create_coach_feedback(conn)` and before `conn.commit()`, add:
```python
        _create_admin_users(conn)
        _create_admin_otp_codes(conn)
        _create_admin_sessions(conn)
        _create_invites(conn)
        _create_admin_audit_log(conn)
        _create_analytics_events(conn)
        _add_status_columns(conn)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_admin_migrations.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `source venv/bin/activate && pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add api/services/db_migrations.py tests/test_admin_migrations.py
git commit -m "feat(admin): additive admin + analytics tables and status columns"
```

---

## Task 2: Analytics emit helper (non-blocking)

**Files:**
- Create: `api/services/analytics_service.py`
- Test: `tests/test_analytics_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_analytics_service.py`:
```python
import os
os.environ["DB_PATH"] = ":memory:"

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import analytics_service as a


def _setup():
    keep = get_conn()
    init_db(); run_all()
    return keep


def test_emit_inserts_row():
    keep = _setup()
    a.emit("signup_completed", actor_role="parent", parent_id=7)
    conn = get_conn()
    row = conn.execute("SELECT event_name, actor_role, parent_id FROM analytics_events").fetchone()
    assert row["event_name"] == "signup_completed"
    assert row["actor_role"] == "parent"
    assert row["parent_id"] == 7
    conn.close(); keep.close()


def test_emit_serializes_props():
    keep = _setup()
    a.emit("feature_used", feature="photo_meal_log", props={"items": 3})
    conn = get_conn()
    row = conn.execute("SELECT feature, props_json FROM analytics_events").fetchone()
    assert row["feature"] == "photo_meal_log"
    assert '"items": 3' in row["props_json"]
    conn.close(); keep.close()


def test_emit_never_raises(monkeypatch):
    keep = _setup()
    # Force the DB call to blow up; emit must swallow it and return False.
    monkeypatch.setattr(a, "get_conn", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert a.emit("app_opened") is False
    keep.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_analytics_service.py -q`
Expected: FAIL — `ModuleNotFoundError: api.services.analytics_service`.

- [ ] **Step 3: Implement the helper**

Create `api/services/analytics_service.py`:
```python
"""Product-analytics event sink. emit() is best-effort and MUST NEVER raise into
a request path — analytics failure can never break a user action."""

import json
import logging

from api.database import get_conn

logger = logging.getLogger(__name__)


def emit(event_name, *, actor_role=None, parent_id=None, athlete_id=None,
         session_id=None, screen=None, feature=None, props=None):
    """Insert one analytics event. Returns True on success, False on any failure."""
    try:
        props_json = json.dumps(props) if props is not None else None
        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO analytics_events
                       (event_name, actor_role, parent_id, athlete_id,
                        session_id, screen, feature, props_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_name, actor_role, parent_id, athlete_id,
                 session_id, screen, feature, props_json),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        logger.warning("analytics emit failed for %s", event_name, exc_info=True)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_analytics_service.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add api/services/analytics_service.py tests/test_analytics_service.py
git commit -m "feat(admin): non-blocking analytics emit helper"
```

---

## Task 3: Admin auth — OTP, tokens, env bootstrap

**Files:**
- Create: `api/services/admin_auth.py`
- Test: `tests/test_admin_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_auth.py`:
```python
import os
os.environ["DB_PATH"] = ":memory:"

from datetime import datetime, timedelta
import pytest

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_auth as aa


def _setup():
    keep = get_conn()
    init_db(); run_all()
    return keep


def test_bootstrap_seeds_admins(monkeypatch):
    keep = _setup()
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAILS", "a@x.com, B@x.com")
    aa.seed_admins_from_env()
    aa.seed_admins_from_env()  # idempotent
    conn = get_conn()
    emails = {r["email"] for r in conn.execute("SELECT email FROM admin_users").fetchall()}
    assert emails == {"a@x.com", "b@x.com"}
    conn.close(); keep.close()


def test_mint_and_verify_token():
    keep = _setup()
    conn = get_conn()
    conn.execute("INSERT INTO admin_users (email, role) VALUES ('a@x.com','admin')")
    conn.commit(); aid = conn.execute("SELECT id FROM admin_users").fetchone()["id"]; conn.close()
    token = aa.mint_token(aid)
    admin = aa.verify_token(f"Bearer {token}")
    assert admin["id"] == aid and admin["role"] == "admin"


def test_verify_rejects_bad_token():
    keep = _setup()
    assert aa.verify_token("Bearer nope") is None
    assert aa.verify_token(None) is None
    assert aa.verify_token("garbage") is None


def test_verify_rejects_expired_session():
    keep = _setup()
    conn = get_conn()
    conn.execute("INSERT INTO admin_users (email) VALUES ('a@x.com')")
    conn.commit(); aid = conn.execute("SELECT id FROM admin_users").fetchone()["id"]
    raw = "expiredtoken"
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    conn.execute("INSERT INTO admin_sessions (token_hash, admin_id, expires_at) VALUES (?,?,?)",
                 (aa.hash_secret(raw), aid, past))
    conn.commit(); conn.close()
    assert aa.verify_token(f"Bearer {raw}") is None


def test_inactive_admin_cannot_verify():
    keep = _setup()
    conn = get_conn()
    conn.execute("INSERT INTO admin_users (email, is_active) VALUES ('a@x.com', 0)")
    conn.commit(); aid = conn.execute("SELECT id FROM admin_users").fetchone()["id"]; conn.close()
    token = aa.mint_token(aid)
    assert aa.verify_token(f"Bearer {token}") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_admin_auth.py -q`
Expected: FAIL — `ModuleNotFoundError: api.services.admin_auth`.

- [ ] **Step 3: Implement admin_auth**

Create `api/services/admin_auth.py`:
```python
"""Admin identity: env-bootstrapped admin accounts, email-OTP login, and a
revocable server-side session token (admin_sessions row keyed by sha256(token))."""

import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta

from fastapi import Header, HTTPException

from api.database import get_conn

logger = logging.getLogger(__name__)

OTP_TTL_MIN = 10
SESSION_TTL_HOURS = 12


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def seed_admins_from_env():
    """Upsert admins listed in ADMIN_BOOTSTRAP_EMAILS (comma-separated). Idempotent."""
    raw = os.getenv("ADMIN_BOOTSTRAP_EMAILS", "").strip()
    if not raw:
        return
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    conn = get_conn()
    try:
        for email in emails:
            conn.execute(
                "INSERT OR IGNORE INTO admin_users (email, role, is_active) VALUES (?, 'admin', 1)",
                (email,),
            )
        conn.commit()
    finally:
        conn.close()


def get_admin_by_email(email: str):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM admin_users WHERE lower(email) = lower(?)", (email.strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_otp(admin_id: int) -> str:
    """Generate, hash, and store a 6-digit OTP. Returns the raw code (caller emails it)."""
    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = (datetime.utcnow() + timedelta(minutes=OTP_TTL_MIN)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO admin_otp_codes (admin_id, code_hash, expires_at) VALUES (?, ?, ?)",
            (admin_id, hash_secret(code), expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    return code


def recently_sent(admin_id: int, seconds: int = 60) -> bool:
    cutoff = (datetime.utcnow() - timedelta(seconds=seconds)).isoformat()
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT 1 FROM admin_otp_codes WHERE admin_id = ? AND created_at > ? AND used = 0",
            (admin_id, cutoff),
        ).fetchone() is not None
    finally:
        conn.close()


def consume_otp(admin_id: int, code: str) -> bool:
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id FROM admin_otp_codes
               WHERE admin_id = ? AND code_hash = ? AND used = 0 AND expires_at > ?
               ORDER BY id DESC LIMIT 1""",
            (admin_id, hash_secret(code.strip()), now),
        ).fetchone()
        if not row:
            return False
        conn.execute("UPDATE admin_otp_codes SET used = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        return True
    finally:
        conn.close()


def mint_token(admin_id: int) -> str:
    """Create a session and return the RAW token (only its hash is stored)."""
    raw = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO admin_sessions (token_hash, admin_id, expires_at) VALUES (?, ?, ?)",
            (hash_secret(raw), admin_id, expires_at),
        )
        conn.execute("UPDATE admin_users SET last_login_at = ? WHERE id = ?",
                     (datetime.utcnow().isoformat(), admin_id))
        conn.commit()
    finally:
        conn.close()
    return raw


def verify_token(authorization: str | None):
    """Return the active admin dict for a 'Bearer <token>' header, else None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    raw = authorization[len("Bearer "):].strip()
    if not raw:
        return None
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT u.* FROM admin_sessions s
               JOIN admin_users u ON u.id = s.admin_id
               WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1""",
            (hash_secret(raw), now),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def revoke_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        return
    raw = authorization[len("Bearer "):].strip()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (hash_secret(raw),))
        conn.commit()
    finally:
        conn.close()


def require_admin(authorization: str | None = Header(default=None)):
    """FastAPI dependency: 401 if no valid session. Returns the admin dict."""
    admin = verify_token(authorization)
    if admin is None:
        raise HTTPException(401, "Admin authentication required.")
    return admin


def require_role(*roles):
    """Dependency factory: 403 unless the admin's role is in `roles`."""
    def _dep(authorization: str | None = Header(default=None)):
        admin = require_admin(authorization)
        if admin["role"] not in roles:
            raise HTTPException(403, "Insufficient admin role.")
        return admin
    return _dep
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_admin_auth.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add api/services/admin_auth.py tests/test_admin_auth.py
git commit -m "feat(admin): OTP login + revocable session tokens + role guard"
```

---

## Task 4: Admin service — users, families, invites, status, audit

**Files:**
- Create: `api/services/admin_service.py`
- Test: `tests/test_admin_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_service.py`:
```python
import os
os.environ["DB_PATH"] = ":memory:"

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.services import admin_service as svc


def _setup():
    keep = get_conn()
    init_db(); run_all()
    return keep


def _seed_family(conn):
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P One','p1@x.com',1)")
    pid = conn.execute("SELECT id FROM parents WHERE email='p1@x.com'").fetchone()["id"]
    conn.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs) "
                 "VALUES (?, 'Maya', 14, 'female', 100)", (pid,))
    # A second parent with NO athlete (relationship gap).
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P Two','p2@x.com',0)")
    conn.commit()
    return pid


def test_list_users_returns_parents_and_athletes():
    keep = _setup(); conn = get_conn(); _seed_family(conn); conn.close()
    rows = svc.list_users(limit=50, offset=0)["items"]
    roles = sorted(r["role"] for r in rows)
    assert roles == ["athlete", "parent", "parent"]
    keep.close()


def test_family_flags_detect_missing_athlete_and_consent():
    keep = _setup(); conn = get_conn(); _seed_family(conn); conn.close()
    fams = svc.list_families()["items"]
    p2 = next(f for f in fams if f["email"] == "p2@x.com")
    assert "no_athlete" in p2["flags"]
    assert "consent_pending" in p2["flags"]
    keep.close()


def test_family_flags_detect_unclaimed_athlete():
    keep = _setup(); conn = get_conn(); pid = _seed_family(conn); conn.close()
    fams = svc.list_families()["items"]
    p1 = next(f for f in fams if f["email"] == "p1@x.com")
    # Maya has a profile but no athlete_logins row -> unclaimed.
    assert "profile_unclaimed" in p1["flags"]
    keep.close()


def test_set_status_writes_audit_row():
    keep = _setup(); conn = get_conn(); pid = _seed_family(conn)
    conn.execute("INSERT INTO admin_users (email) VALUES ('admin@x.com')")
    conn.commit(); aid = conn.execute("SELECT id FROM admin_users").fetchone()["id"]; conn.close()
    svc.set_user_status(actor_admin_id=aid, role="parent", user_id=pid,
                        status="suspended", reason="dup account")
    conn = get_conn()
    p = conn.execute("SELECT status, deactivated_at FROM parents WHERE id=?", (pid,)).fetchone()
    assert p["status"] == "suspended" and p["deactivated_at"] is not None
    log = conn.execute("SELECT action, target_type, target_id, reason FROM admin_audit_log").fetchone()
    assert log["action"] == "user.status.suspended"
    assert log["target_type"] == "parent" and log["target_id"] == pid
    assert log["reason"] == "dup account"
    conn.close(); keep.close()


def test_reactivate_clears_deactivated_at():
    keep = _setup(); conn = get_conn(); pid = _seed_family(conn)
    conn.execute("INSERT INTO admin_users (email) VALUES ('a@x.com')")
    conn.commit(); aid = conn.execute("SELECT id FROM admin_users").fetchone()["id"]; conn.close()
    svc.set_user_status(actor_admin_id=aid, role="parent", user_id=pid, status="suspended", reason="x")
    svc.set_user_status(actor_admin_id=aid, role="parent", user_id=pid, status="active", reason="ok")
    conn = get_conn()
    p = conn.execute("SELECT status, deactivated_at FROM parents WHERE id=?", (pid,)).fetchone()
    assert p["status"] == "active" and p["deactivated_at"] is None
    conn.close(); keep.close()


def test_resend_invite_bumps_reminder_history():
    keep = _setup(); conn = get_conn()
    conn.execute("INSERT INTO invites (kind, email, status) VALUES ('parent','p@x.com','pending')")
    conn.commit(); iid = conn.execute("SELECT id FROM invites").fetchone()["id"]; conn.close()
    out = svc.resend_invite(iid)
    assert out["reminder_count"] == 1 and out["last_reminded_at"] is not None
    out2 = svc.resend_invite(iid)
    assert out2["reminder_count"] == 2
    keep.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_admin_service.py -q`
Expected: FAIL — `ModuleNotFoundError: api.services.admin_service`.

- [ ] **Step 3: Implement the service**

Create `api/services/admin_service.py`:
```python
"""Read-mostly admin logic over the existing parents/athletes tables plus the new
invites/audit tables. Writes are limited to status changes and invite resends, each
of which records an admin_audit_log row."""

import json
from datetime import datetime

from api.database import get_conn

# Athlete fields safe to surface in the console (privacy: first name + id, no contact).
_ATHLETE_PUBLIC = "id, parent_id, first_name, age, gender, status, deactivated_at, created_at"


def _now():
    return datetime.utcnow().isoformat()


def audit(conn, *, actor_admin_id, action, target_type=None, target_id=None,
          reason=None, meta=None):
    conn.execute(
        """INSERT INTO admin_audit_log
               (actor_admin_id, action, target_type, target_id, reason, meta_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (actor_admin_id, action, target_type, target_id, reason,
         json.dumps(meta) if meta is not None else None),
    )


def list_users(*, limit=50, offset=0, role=None, status=None, q=None):
    """Unified view across parents (role=parent) and athletes (role=athlete)."""
    conn = get_conn()
    try:
        items = []
        if role in (None, "parent"):
            sql = ("SELECT id, full_name AS name, email, status, created_at, "
                   "consent_confirmed FROM parents WHERE 1=1")
            args = []
            if status:
                sql += " AND status = ?"; args.append(status)
            if q:
                sql += " AND (full_name LIKE ? OR email LIKE ?)"; args += [f"%{q}%", f"%{q}%"]
            for r in conn.execute(sql, args).fetchall():
                d = dict(r); d["role"] = "parent"; items.append(d)
        if role in (None, "athlete"):
            sql = (f"SELECT {_ATHLETE_PUBLIC}, first_name AS name FROM athletes WHERE 1=1")
            args = []
            if status:
                sql += " AND status = ?"; args.append(status)
            if q:
                sql += " AND first_name LIKE ?"; args.append(f"%{q}%")
            for r in conn.execute(sql, args).fetchall():
                d = dict(r); d["role"] = "athlete"; items.append(d)
        total = len(items)
        items = items[offset:offset + limit]
        return {"total": total, "items": items}
    finally:
        conn.close()


def get_user(role, user_id):
    conn = get_conn()
    try:
        if role == "parent":
            row = conn.execute("SELECT * FROM parents WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            d = dict(row); d["role"] = "parent"
            d["athletes"] = [dict(a) for a in conn.execute(
                f"SELECT {_ATHLETE_PUBLIC} FROM athletes WHERE parent_id = ?", (user_id,)).fetchall()]
            return d
        row = conn.execute(f"SELECT {_ATHLETE_PUBLIC} FROM athletes WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        d = dict(row); d["role"] = "athlete"
        d["has_login"] = conn.execute(
            "SELECT 1 FROM athlete_logins WHERE athlete_id = ?", (user_id,)).fetchone() is not None
        return d
    finally:
        conn.close()


def _family_flags(conn, parent):
    flags = []
    if not parent["consent_confirmed"]:
        flags.append("consent_pending")
    athletes = conn.execute(
        "SELECT id FROM athletes WHERE parent_id = ?", (parent["id"],)).fetchall()
    if not athletes:
        flags.append("no_athlete")
    for a in athletes:
        claimed = conn.execute(
            "SELECT 1 FROM athlete_logins WHERE athlete_id = ?", (a["id"],)).fetchone()
        if not claimed:
            flags.append("profile_unclaimed")
            break
    return flags


def list_families(*, broken_only=False):
    conn = get_conn()
    try:
        items = []
        for p in conn.execute("SELECT * FROM parents").fetchall():
            p = dict(p)
            flags = _family_flags(conn, p)
            if broken_only and not flags:
                continue
            items.append({"id": p["id"], "name": p["full_name"], "email": p["email"],
                          "consent_confirmed": p["consent_confirmed"], "flags": flags})
        return {"total": len(items), "items": items}
    finally:
        conn.close()


def get_family(parent_id):
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM parents WHERE id = ?", (parent_id,)).fetchone()
        if not p:
            return None
        p = dict(p)
        athletes = []
        for a in conn.execute(f"SELECT {_ATHLETE_PUBLIC} FROM athletes WHERE parent_id = ?",
                              (parent_id,)).fetchall():
            a = dict(a)
            a["has_login"] = conn.execute(
                "SELECT 1 FROM athlete_logins WHERE athlete_id = ?", (a["id"],)).fetchone() is not None
            athletes.append(a)
        invites = [dict(i) for i in conn.execute(
            "SELECT * FROM invites WHERE parent_id = ? OR athlete_id IN "
            "(SELECT id FROM athletes WHERE parent_id = ?)", (parent_id, parent_id)).fetchall()]
        return {"id": p["id"], "name": p["full_name"], "email": p["email"],
                "consent_confirmed": p["consent_confirmed"],
                "flags": _family_flags(conn, p), "athletes": athletes, "invites": invites}
    finally:
        conn.close()


def set_user_status(*, actor_admin_id, role, user_id, status, reason):
    if role not in ("parent", "athlete"):
        raise ValueError("role must be parent or athlete")
    if status not in ("active", "suspended"):
        raise ValueError("status must be active or suspended")
    table = "parents" if role == "parent" else "athletes"
    deactivated_at = _now() if status == "suspended" else None
    conn = get_conn()
    try:
        exists = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (user_id,)).fetchone()
        if not exists:
            raise LookupError("user not found")
        conn.execute(f"UPDATE {table} SET status = ?, deactivated_at = ? WHERE id = ?",
                     (status, deactivated_at, user_id))
        audit(conn, actor_admin_id=actor_admin_id, action=f"user.status.{status}",
              target_type=role, target_id=user_id, reason=reason)
        conn.commit()
        return {"id": user_id, "role": role, "status": status}
    finally:
        conn.close()


def list_invites(*, status=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM invites"
        args = []
        if status:
            sql += " WHERE status = ?"; args.append(status)
        sql += " ORDER BY id DESC"
        return {"items": [dict(r) for r in conn.execute(sql, args).fetchall()]}
    finally:
        conn.close()


def resend_invite(invite_id, *, actor_admin_id=None):
    conn = get_conn()
    try:
        inv = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        if not inv:
            raise LookupError("invite not found")
        now = _now()
        conn.execute(
            "UPDATE invites SET reminder_count = reminder_count + 1, last_reminded_at = ?, "
            "sent_at = ? WHERE id = ?", (now, now, invite_id))
        if actor_admin_id is not None:
            audit(conn, actor_admin_id=actor_admin_id, action="invite.resend",
                  target_type="invite", target_id=invite_id)
        conn.commit()
        out = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        return dict(out)
    finally:
        conn.close()


def list_audit_logs(*, limit=100, offset=0, action=None):
    conn = get_conn()
    try:
        sql = ("SELECT l.*, u.email AS actor_email FROM admin_audit_log l "
               "LEFT JOIN admin_users u ON u.id = l.actor_admin_id WHERE 1=1")
        args = []
        if action:
            sql += " AND l.action = ?"; args.append(action)
        sql += " ORDER BY l.id DESC LIMIT ? OFFSET ?"; args += [limit, offset]
        return {"items": [dict(r) for r in conn.execute(sql, args).fetchall()]}
    finally:
        conn.close()


def dashboard_summary():
    conn = get_conn()
    try:
        one = lambda q, a=(): conn.execute(q, a).fetchone()[0]
        total_parents = one("SELECT COUNT(*) FROM parents")
        total_athletes = one("SELECT COUNT(*) FROM athletes")
        consent_pending = one("SELECT COUNT(*) FROM parents WHERE consent_confirmed = 0")
        no_athlete = one("SELECT COUNT(*) FROM parents p WHERE NOT EXISTS "
                         "(SELECT 1 FROM athletes a WHERE a.parent_id = p.id)")
        unclaimed = one("SELECT COUNT(*) FROM athletes a WHERE NOT EXISTS "
                        "(SELECT 1 FROM athlete_logins l WHERE l.athlete_id = a.id)")
        pending_invites = one("SELECT COUNT(*) FROM invites WHERE status = 'pending'")
        return {
            "total_users": total_parents + total_athletes,
            "parents": total_parents,
            "athletes": total_athletes,
            "consent_pending": consent_pending,
            "parents_without_athlete": no_athlete,
            "unclaimed_athletes": unclaimed,
            "pending_invites": pending_invites,
        }
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_admin_service.py -q`
Expected: PASS (6 passed).

> If `test_list_users_returns_parents_and_athletes` fails on column availability, confirm Task 1 ran `init_db()`+`run_all()` so the additive `status` columns exist on `parents`/`athletes`.

- [ ] **Step 5: Commit**

```bash
git add api/services/admin_service.py tests/test_admin_service.py
git commit -m "feat(admin): user/family/invite/status/audit service"
```

---

## Task 5: Pydantic models for admin

**Files:**
- Modify: `api/models.py` (append)

- [ ] **Step 1: Append the models**

Add to the end of `api/models.py`:
```python
from pydantic import BaseModel


class AdminOTPRequest(BaseModel):
    email: str


class AdminOTPVerify(BaseModel):
    email: str
    code: str


class AdminStatusUpdate(BaseModel):
    role: str          # "parent" | "athlete"
    status: str        # "active" | "suspended"
    reason: str


class AnalyticsEventIn(BaseModel):
    event_name: str
    actor_role: str | None = None
    athlete_id: int | None = None
    parent_id: int | None = None
    session_id: str | None = None
    screen: str | None = None
    feature: str | None = None
    props: dict | None = None
```

> If `from pydantic import BaseModel` is already imported at the top of `api/models.py`, omit the duplicate import line here.

- [ ] **Step 2: Verify it imports**

Run: `source venv/bin/activate && python -c "import api.models; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add api/models.py
git commit -m "feat(admin): pydantic models for admin endpoints"
```

---

## Task 6: Admin router + public event collector

**Files:**
- Create: `api/routes/admin.py`
- Modify: `api/main.py` (register router + bootstrap admins)
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_routes.py`:
```python
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
import api.routes.admin as admin_routes
from api.services import admin_auth as aa


@pytest.fixture
def client(monkeypatch):
    keep = get_conn()
    init_db(); run_all()
    sent = []
    # Capture OTP emails instead of sending SMTP.
    monkeypatch.setattr(admin_routes, "send_email",
                        lambda subject, body, to, attachment_path=None: sent.append(body) or True)
    with TestClient(app) as c:
        c.sent = sent
        yield c
    keep.close()


def _login(client, email="admin@x.com"):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO admin_users (email, role, is_active) VALUES (?, 'admin', 1)", (email,))
    conn.commit(); conn.close()
    r = client.post("/api/admin/auth/request-otp", json={"email": email})
    assert r.status_code == 200, r.text
    code = client.sent[-1].split("code is ")[1].split(".")[0].strip()  # body format below
    r = client.post("/api/admin/auth/verify-otp", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_requires_auth():
    # Fresh client without fixture monkeypatch is fine; just hit unauthed.
    with TestClient(app) as c:
        assert c.get("/api/admin/users").status_code == 401


def test_login_and_list_users(client):
    token = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    conn = get_conn()
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P','p@x.com',1)")
    conn.commit(); conn.close()
    r = client.get("/api/admin/users", headers=h)
    assert r.status_code == 200
    assert any(u["role"] == "parent" for u in r.json()["items"])


def test_status_patch_requires_reason(client):
    token = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    conn = get_conn()
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P','p@x.com',1)")
    conn.commit(); pid = conn.execute("SELECT id FROM parents").fetchone()["id"]; conn.close()
    bad = client.patch(f"/api/admin/users/{pid}/status",
                       headers=h, json={"role": "parent", "status": "suspended", "reason": ""})
    assert bad.status_code == 422 or bad.status_code == 400
    ok = client.patch(f"/api/admin/users/{pid}/status",
                      headers=h, json={"role": "parent", "status": "suspended", "reason": "dup"})
    assert ok.status_code == 200
    logs = client.get("/api/admin/audit-logs", headers=h).json()["items"]
    assert any(l["action"] == "user.status.suspended" for l in logs)


def test_public_event_collector(client):
    r = client.post("/api/events", json={"event_name": "screen_viewed", "screen": "today"})
    assert r.status_code == 202
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) FROM analytics_events WHERE event_name='screen_viewed'"
                        ).fetchone()[0] == 1
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_admin_routes.py -q`
Expected: FAIL — `ModuleNotFoundError: api.routes.admin`.

- [ ] **Step 3: Implement the router**

Create `api/routes/admin.py`:
```python
"""Admin Module API. Every route except the two auth endpoints and the public
/api/events collector requires a valid admin session (require_admin)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Header

from api.database import get_conn
from api.models import (
    AdminOTPRequest, AdminOTPVerify, AdminStatusUpdate, AnalyticsEventIn,
)
from api.services import admin_auth as aa
from api.services import admin_service as svc
from api.services import analytics_service
from api.services.email_service import send_email

logger = logging.getLogger(__name__)

router = APIRouter()
events_router = APIRouter()  # mounted at /api (public collector)


# ---- Auth ----
@router.post("/auth/request-otp")
def request_otp(body: AdminOTPRequest):
    admin = aa.get_admin_by_email(body.email)
    # Do not reveal whether the email is an admin; behave uniformly.
    if not admin or not admin["is_active"]:
        return {"message": "If that email is an admin, a code has been sent."}
    if aa.recently_sent(admin["id"]):
        raise HTTPException(429, "A code was already sent. Wait 60 seconds.")
    code = aa.create_otp(admin["id"])
    send_email("AthFuelPath Admin login code",
               f"Your AthFuelPath admin login code is {code}. It expires in 10 minutes.",
               [admin["email"]])
    return {"message": "If that email is an admin, a code has been sent."}


@router.post("/auth/verify-otp")
def verify_otp(body: AdminOTPVerify):
    admin = aa.get_admin_by_email(body.email)
    if not admin or not admin["is_active"] or not aa.consume_otp(admin["id"], body.code):
        raise HTTPException(401, "Invalid or expired code.")
    token = aa.mint_token(admin["id"])
    return {"token": token, "admin": {"email": admin["email"], "role": admin["role"]}}


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None), admin=Depends(aa.require_admin)):
    aa.revoke_token(authorization)
    return {"ok": True}


# ---- Users ----
@router.get("/users")
def list_users(limit: int = 50, offset: int = 0, role: str | None = None,
               status: str | None = None, q: str | None = None,
               admin=Depends(aa.require_admin)):
    return svc.list_users(limit=limit, offset=offset, role=role, status=status, q=q)


@router.get("/users/{role}/{user_id}")
def get_user(role: str, user_id: int, admin=Depends(aa.require_admin)):
    user = svc.get_user(role, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    return user


@router.patch("/users/{user_id}/status")
def patch_status(user_id: int, body: AdminStatusUpdate, admin=Depends(aa.require_admin)):
    if not body.reason or len(body.reason.strip()) < 3:
        raise HTTPException(400, "A reason (min 3 chars) is required.")
    try:
        return svc.set_user_status(actor_admin_id=admin["id"], role=body.role,
                                   user_id=user_id, status=body.status,
                                   reason=body.reason.strip())
    except LookupError:
        raise HTTPException(404, "User not found.")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- Families ----
@router.get("/families")
def list_families(broken_only: bool = False, admin=Depends(aa.require_admin)):
    return svc.list_families(broken_only=broken_only)


@router.get("/families/{parent_id}")
def get_family(parent_id: int, admin=Depends(aa.require_admin)):
    fam = svc.get_family(parent_id)
    if not fam:
        raise HTTPException(404, "Family not found.")
    return fam


# ---- Invites ----
@router.get("/invites")
def list_invites(status: str | None = None, admin=Depends(aa.require_admin)):
    return svc.list_invites(status=status)


@router.post("/invites/{invite_id}/resend")
def resend_invite(invite_id: int, admin=Depends(aa.require_admin)):
    try:
        out = svc.resend_invite(invite_id, actor_admin_id=admin["id"])
    except LookupError:
        raise HTTPException(404, "Invite not found.")
    email_sent = False
    if out.get("email"):
        email_sent = send_email(
            "Your AthFuelPath invitation (reminder)",
            "This is a reminder to finish setting up your AthFuelPath account.",
            [out["email"]])
    return {**out, "email_sent": email_sent}


# ---- Audit + dashboard ----
@router.get("/audit-logs")
def audit_logs(limit: int = 100, offset: int = 0, action: str | None = None,
               admin=Depends(aa.require_admin)):
    return svc.list_audit_logs(limit=limit, offset=offset, action=action)


@router.get("/dashboard")
def dashboard(admin=Depends(aa.require_admin)):
    return svc.dashboard_summary()


# ---- Public event collector (no auth; rate-limit-friendly, best-effort) ----
@events_router.post("/events", status_code=202)
def collect_event(body: AnalyticsEventIn):
    analytics_service.emit(
        body.event_name, actor_role=body.actor_role, parent_id=body.parent_id,
        athlete_id=body.athlete_id, session_id=body.session_id, screen=body.screen,
        feature=body.feature, props=body.props)
    return {"accepted": True}
```

- [ ] **Step 4: Register the router and bootstrap admins**

In `api/main.py`, add `admin` to the route import (line 30) so it reads `… support, admin`:
```python
from api.routes import parents, athletes, events, nutrition, meals, recipes, analysis, reports, notifications, meal_plans, meal_plan_selections, today, water, knowledge, legal, library, auth, fuel_report, report_config, coach, shopping, support, admin
```
After the `support.router` registration (line 70), add:
```python
app.include_router(admin.router,        prefix="/api/admin",  tags=["23. Admin"])
app.include_router(admin.events_router, prefix="/api",        tags=["24. Analytics Collector"])
```
In the `lifespan` function (after `db_migrations.run_all()`), seed admins:
```python
        from api.services.admin_auth import seed_admins_from_env
        seed_admins_from_env()
```

- [ ] **Step 5: Align the test's OTP-parsing with the email body**

The test extracts the code from the email body via `split("code is ")[1].split(".")[0]`. The body in `request_otp` is `f"Your AthFuelPath admin login code is {code}. It expires in 10 minutes."` — which matches. No change needed; this step is a verification that the substring contract holds.

- [ ] **Step 6: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_admin_routes.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Run the full suite**

Run: `source venv/bin/activate && pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add api/routes/admin.py api/main.py tests/test_admin_routes.py
git commit -m "feat(admin): /api/admin router, auth endpoints, public event collector"
```

---

## Task 7: Instrument lifecycle analytics events (server-side)

Emit the lifecycle events the funnel needs, at the real moments, in existing routes. Each call is one line and cannot break the request (emit swallows errors).

**Files:**
- Modify: `api/routes/parents.py` (signup + consent)
- Modify: `api/routes/athletes.py` (athlete created; blueprint generated)

- [ ] **Step 1: Write the failing test**

Create `tests/test_lifecycle_events.py`:
```python
import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app


@pytest.fixture
def client():
    keep = get_conn()
    init_db(); run_all()
    with TestClient(app) as c:
        yield c
    keep.close()


def _events(name):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM analytics_events WHERE event_name = ?", (name,)).fetchone()[0]
    conn.close()
    return n


def test_signup_emits_event(client):
    # Mirror the existing parent-create contract used elsewhere in the suite.
    r = client.post("/api/parents/", json={"full_name": "P", "email": "newp@x.com"})
    assert r.status_code in (200, 201), r.text
    assert _events("signup_completed") == 1
```

> Before writing Step 3, open `api/routes/parents.py` and confirm the exact create-parent handler name/signature and its success path (the suite already exercises parent creation). Match the real variable holding the new parent id.

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_lifecycle_events.py -q`
Expected: FAIL — `assert 0 == 1`.

- [ ] **Step 3: Emit on signup + consent**

In `api/routes/parents.py`, add the import near the top:
```python
from api.services.analytics_service import emit
```
In the create-parent handler, immediately after the parent row is committed and its id is known (variable holding the new id — e.g. `parent_id`), add:
```python
    emit("signup_completed", actor_role="parent", parent_id=parent_id)
```
In `confirm_consent`, after the consent UPDATE commits, add:
```python
    emit("consent_confirmed", actor_role="parent", parent_id=parent_id)
```

- [ ] **Step 4: Emit on athlete created + blueprint generated**

In `api/routes/athletes.py`, add `from api.services.analytics_service import emit`. After the athlete INSERT commits (id known as e.g. `athlete_id`), add:
```python
    emit("athlete_created", actor_role="parent", athlete_id=athlete_id)
```
In the background blueprint task, after `UPDATE athletes SET blueprint_json = ?` succeeds with a real (non-error) blueprint, add:
```python
    emit("blueprint_generated", actor_role="system", athlete_id=athlete_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_lifecycle_events.py -q`
Expected: PASS (1 passed).

- [ ] **Step 6: Run the full suite**

Run: `source venv/bin/activate && pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add api/routes/parents.py api/routes/athletes.py tests/test_lifecycle_events.py
git commit -m "feat(admin): emit signup/consent/athlete/blueprint lifecycle events"
```

---

## Task 8: Frontend — admin API client + auth gate + tab shell

> The repo has **no frontend test framework** (all tests are pytest). Per the codebase's established pattern, frontend tasks verify via `npm run build`, `npm run lint`, and manual checks against a running dev server. Follow the existing `LibraryAdmin.jsx` conventions (`const API = import.meta.env.VITE_API_URL ?? ""`).

**Files:**
- Create: `frontend/src/pages/admin/adminApi.js`
- Create: `frontend/src/pages/admin/AdminApp.jsx`
- Create: `frontend/src/pages/admin/AdminLogin.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create the API client**

Create `frontend/src/pages/admin/adminApi.js`:
```js
const API = import.meta.env.VITE_API_URL ?? "";
const TOKEN_KEY = "fuelup_admin_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function req(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API}/api/admin${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    clearToken();
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

export const adminApi = {
  requestOtp: (email) => req("/auth/request-otp", { method: "POST", body: { email } }),
  verifyOtp: (email, code) => req("/auth/verify-otp", { method: "POST", body: { email, code } }),
  logout: () => req("/auth/logout", { method: "POST" }),
  dashboard: () => req("/dashboard"),
  users: (qs = "") => req(`/users${qs}`),
  user: (role, id) => req(`/users/${role}/${id}`),
  setStatus: (id, body) => req(`/users/${id}/status`, { method: "PATCH", body }),
  families: (brokenOnly = false) => req(`/families?broken_only=${brokenOnly}`),
  family: (id) => req(`/families/${id}`),
  invites: (status = "") => req(`/invites${status ? `?status=${status}` : ""}`),
  resendInvite: (id) => req(`/invites/${id}/resend`, { method: "POST" }),
  auditLogs: () => req("/audit-logs"),
};
```

- [ ] **Step 2: Create the login screen**

Create `frontend/src/pages/admin/AdminLogin.jsx`:
```jsx
import { useState } from "react";
import { adminApi, setToken } from "./adminApi";

export default function AdminLogin({ onAuthed }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState("email");
  const [err, setErr] = useState("");

  const requestCode = async () => {
    setErr("");
    try { await adminApi.requestOtp(email); setStage("code"); }
    catch (e) { setErr(e.message); }
  };
  const verify = async () => {
    setErr("");
    try { const { token } = await adminApi.verifyOtp(email, code); setToken(token); onAuthed(); }
    catch (e) { setErr("Invalid or expired code."); }
  };

  return (
    <div style={{ maxWidth: 360, margin: "80px auto", fontFamily: "system-ui" }}>
      <h2>AthFuelPath Admin</h2>
      {stage === "email" ? (
        <>
          <input placeholder="admin email" value={email}
                 onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", padding: 8 }} />
          <button onClick={requestCode} style={{ marginTop: 8 }}>Send code</button>
        </>
      ) : (
        <>
          <input placeholder="6-digit code" value={code}
                 onChange={(e) => setCode(e.target.value)} style={{ width: "100%", padding: 8 }} />
          <button onClick={verify} style={{ marginTop: 8 }}>Verify</button>
        </>
      )}
      {err && <p style={{ color: "crimson" }}>{err}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Create the tab shell**

Create `frontend/src/pages/admin/AdminApp.jsx`:
```jsx
import { useState } from "react";
import { getToken, clearToken, adminApi } from "./adminApi";
import AdminLogin from "./AdminLogin";
import Dashboard from "./Dashboard";
import Users from "./Users";
import Families from "./Families";
import Invites from "./Invites";
import AuditLog from "./AuditLog";

const TABS = {
  Dashboard: Dashboard, Users: Users, Families: Families,
  Invites: Invites, Audit: AuditLog,
};

export default function AdminApp() {
  const [authed, setAuthed] = useState(!!getToken());
  const [tab, setTab] = useState("Dashboard");
  if (!authed) return <AdminLogin onAuthed={() => setAuthed(true)} />;
  const Active = TABS[tab];
  const signOut = async () => { try { await adminApi.logout(); } catch {} clearToken(); setAuthed(false); };
  return (
    <div style={{ fontFamily: "system-ui", padding: 16 }}>
      <header style={{ display: "flex", gap: 12, alignItems: "center", borderBottom: "1px solid #ddd", paddingBottom: 8 }}>
        <strong>AthFuelPath Admin</strong>
        {Object.keys(TABS).map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  style={{ fontWeight: t === tab ? 700 : 400 }}>{t}</button>
        ))}
        <button onClick={signOut} style={{ marginLeft: "auto" }}>Sign out</button>
      </header>
      <main style={{ paddingTop: 16 }}><Active /></main>
    </div>
  );
}
```

- [ ] **Step 4: Wire the `/admin` route**

In `frontend/src/App.jsx`, alongside the existing `/admin/library` check (around line 10), add an `/admin` branch **before** it so the console renders:
```jsx
  if (window.location.pathname === "/admin") {
    const AdminApp = require("./pages/admin/AdminApp").default; // or: import lazily
    return <AdminApp />;
  }
```
> If the project uses ESM `import` (it does — Vite), instead add a top-of-file import `import AdminApp from "./pages/admin/AdminApp";` and use `if (window.location.pathname === "/admin") return <AdminApp />;`. Match the existing import style used for `LibraryAdmin`.

- [ ] **Step 5: Build to verify it compiles (with stub tabs)**

The tab components are created in Task 9; to compile now, create minimal stubs OR do Step 5 after Task 9. If proceeding now, create one-line placeholder default-export components for `Dashboard/Users/Families/Invites/AuditLog`, then:

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/adminApi.js frontend/src/pages/admin/AdminApp.jsx frontend/src/pages/admin/AdminLogin.jsx frontend/src/App.jsx
git commit -m "feat(admin): SPA admin route, OTP login, tab shell, API client"
```

---

## Task 9: Frontend — Dashboard, Users, Families, Invites, Audit tabs

**Files:**
- Create: `frontend/src/pages/admin/Dashboard.jsx`
- Create: `frontend/src/pages/admin/Users.jsx`
- Create: `frontend/src/pages/admin/Families.jsx`
- Create: `frontend/src/pages/admin/Invites.jsx`
- Create: `frontend/src/pages/admin/AuditLog.jsx`

- [ ] **Step 1: Dashboard**

Create `frontend/src/pages/admin/Dashboard.jsx`:
```jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminApi";

const Tile = ({ label, value, warn }) => (
  <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, minWidth: 120 }}>
    <div style={{ fontSize: 28, fontWeight: 700, color: warn ? "crimson" : "inherit" }}>{value}</div>
    <div style={{ color: "#666" }}>{label}</div>
  </div>
);

export default function Dashboard() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { adminApi.dashboard().then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <p style={{ color: "crimson" }}>{err}</p>;
  if (!d) return <p>Loading…</p>;
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      <Tile label="Total users" value={d.total_users} />
      <Tile label="Parents" value={d.parents} />
      <Tile label="Athletes" value={d.athletes} />
      <Tile label="Consent pending" value={d.consent_pending} warn={d.consent_pending > 0} />
      <Tile label="Parents w/o athlete" value={d.parents_without_athlete} warn={d.parents_without_athlete > 0} />
      <Tile label="Unclaimed athletes" value={d.unclaimed_athletes} warn={d.unclaimed_athletes > 0} />
      <Tile label="Pending invites" value={d.pending_invites} />
    </div>
  );
}
```

- [ ] **Step 2: Users**

Create `frontend/src/pages/admin/Users.jsx`:
```jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminApi";

export default function Users() {
  const [data, setData] = useState({ items: [] });
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (role) params.set("role", role);
    adminApi.users(`?${params.toString()}`).then(setData).catch(() => {});
  };
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  const suspend = async (u) => {
    const reason = window.prompt(`Reason to ${u.status === "suspended" ? "reactivate" : "suspend"} ${u.name}?`);
    if (!reason) return;
    setBusy(true);
    try {
      await adminApi.setStatus(u.id, {
        role: u.role,
        status: u.status === "suspended" ? "active" : "suspended",
        reason,
      });
      load();
    } finally { setBusy(false); }
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input placeholder="search" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">all roles</option>
          <option value="parent">parent</option>
          <option value="athlete">athlete</option>
        </select>
        <button onClick={load}>Filter</button>
      </div>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>{["ID", "Name", "Role", "Status", "Action"].map((h) =>
          <th key={h} style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 6 }}>{h}</th>)}</tr></thead>
        <tbody>
          {data.items.map((u) => (
            <tr key={`${u.role}-${u.id}`}>
              <td style={{ padding: 6 }}>{u.id}</td>
              <td style={{ padding: 6 }}>{u.name}</td>
              <td style={{ padding: 6 }}>{u.role}</td>
              <td style={{ padding: 6 }}>{u.status || "—"}</td>
              <td style={{ padding: 6 }}>
                <button disabled={busy} onClick={() => suspend(u)}>
                  {u.status === "suspended" ? "Reactivate" : "Suspend"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Families**

Create `frontend/src/pages/admin/Families.jsx`:
```jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminApi";

export default function Families() {
  const [items, setItems] = useState([]);
  const [sel, setSel] = useState(null);
  const [brokenOnly, setBrokenOnly] = useState(false);

  const load = () => adminApi.families(brokenOnly).then((d) => setItems(d.items)).catch(() => {});
  useEffect(load, [brokenOnly]); // eslint-disable-line react-hooks/exhaustive-deps
  const open = (id) => adminApi.family(id).then(setSel).catch(() => {});

  return (
    <div style={{ display: "flex", gap: 16 }}>
      <div style={{ width: 280 }}>
        <label><input type="checkbox" checked={brokenOnly}
          onChange={(e) => setBrokenOnly(e.target.checked)} /> broken only</label>
        <ul style={{ listStyle: "none", padding: 0 }}>
          {items.map((f) => (
            <li key={f.id}>
              <button onClick={() => open(f.id)} style={{ textAlign: "left", width: "100%" }}>
                {f.name} {f.flags.length ? "⚠" : ""}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div style={{ flex: 1, borderLeft: "1px solid #ddd", paddingLeft: 16 }}>
        {!sel ? <p>Select a family.</p> : (
          <>
            <h3>{sel.name} <small>#{sel.id}</small></h3>
            <p>{sel.email} — consent: {sel.consent_confirmed ? "✓" : "PENDING"}</p>
            <p>Flags: {sel.flags.join(", ") || "none"}</p>
            <h4>Athletes</h4>
            <ul>{sel.athletes.map((a) => (
              <li key={a.id}>{a.first_name} ({a.age}) — account {a.has_login ? "✓" : "✗ unclaimed"}</li>
            ))}{sel.athletes.length === 0 && <li>none ⚠</li>}</ul>
            <h4>Invites</h4>
            <ul>{sel.invites.map((i) => (
              <li key={i.id}>{i.kind} — {i.status} (reminders: {i.reminder_count})</li>
            ))}{sel.invites.length === 0 && <li>none</li>}</ul>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Invites**

Create `frontend/src/pages/admin/Invites.jsx`:
```jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminApi";

export default function Invites() {
  const [items, setItems] = useState([]);
  const load = () => adminApi.invites().then((d) => setItems(d.items)).catch(() => {});
  useEffect(load, []);
  const resend = async (id) => { await adminApi.resendInvite(id); load(); };
  return (
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead><tr>{["ID", "Kind", "For", "Status", "Reminders", ""].map((h) =>
        <th key={h} style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 6 }}>{h}</th>)}</tr></thead>
      <tbody>
        {items.map((i) => (
          <tr key={i.id}>
            <td style={{ padding: 6 }}>{i.id}</td>
            <td style={{ padding: 6 }}>{i.kind}</td>
            <td style={{ padding: 6 }}>{i.email || i.athlete_id || i.parent_id}</td>
            <td style={{ padding: 6 }}>{i.status}</td>
            <td style={{ padding: 6 }}>{i.reminder_count}</td>
            <td style={{ padding: 6 }}><button onClick={() => resend(i.id)}>Resend</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: AuditLog**

Create `frontend/src/pages/admin/AuditLog.jsx`:
```jsx
import { useEffect, useState } from "react";
import { adminApi } from "./adminApi";

export default function AuditLog() {
  const [items, setItems] = useState([]);
  useEffect(() => { adminApi.auditLogs().then((d) => setItems(d.items)).catch(() => {}); }, []);
  return (
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead><tr>{["When", "Admin", "Action", "Target", "Reason"].map((h) =>
        <th key={h} style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 6 }}>{h}</th>)}</tr></thead>
      <tbody>
        {items.map((l) => (
          <tr key={l.id}>
            <td style={{ padding: 6 }}>{l.created_at}</td>
            <td style={{ padding: 6 }}>{l.actor_email || l.actor_admin_id}</td>
            <td style={{ padding: 6 }}>{l.action}</td>
            <td style={{ padding: 6 }}>{l.target_type} #{l.target_id}</td>
            <td style={{ padding: 6 }}>{l.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 6: Build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: build succeeds; lint passes (fix any unused-var/hook warnings inline).

- [ ] **Step 7: Manual smoke test**

In one terminal: `source venv/bin/activate && ADMIN_BOOTSTRAP_EMAILS=you@example.com uvicorn api.main:app --reload --port 8000`.
In another: `cd frontend && npm run dev`. Visit `http://localhost:5173/admin`, log in with the OTP printed to the API logs (or delivered by email if SMTP is configured), and confirm Dashboard/Users/Families/Invites/Audit load and a suspend→reactivate writes an audit row.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/admin/Dashboard.jsx frontend/src/pages/admin/Users.jsx frontend/src/pages/admin/Families.jsx frontend/src/pages/admin/Invites.jsx frontend/src/pages/admin/AuditLog.jsx
git commit -m "feat(admin): dashboard, users, families, invites, audit tabs"
```

---

## Required deliverable sections

### Backend tasks (summary)
Tasks 1–7: migrations & additive columns; analytics emit helper; admin auth (OTP + revocable session token + role guard + env bootstrap); admin service (users/families/invites/status/audit/dashboard); Pydantic models; admin router + public event collector; lifecycle event instrumentation.

### Frontend tasks (summary)
Tasks 8–9: API client with bearer-token handling and 401 logout; OTP login; tab shell behind `/admin`; Dashboard, Users, Families, Invites, Audit tabs. Verified by `npm run build` + `npm run lint` + manual smoke (no FE test framework exists — matches repo convention).

### Database changes (summary)
New tables: `admin_users`, `admin_otp_codes`, `admin_sessions`, `invites`, `admin_audit_log`, `analytics_events` (+2 indexes). Additive nullable columns: `parents.status`, `parents.deactivated_at`, `athletes.status`, `athletes.deactivated_at`. All via idempotent `_create_*`/`_add_*` functions in `db_migrations.run_all()` — no destructive changes, no rewrite of existing tables.

### APIs (catalog)
| Method · Path | Auth | Notes |
|---|---|---|
| `POST /api/admin/auth/request-otp` | public | uniform response; 1/60s rate limit |
| `POST /api/admin/auth/verify-otp` | public→token | returns `{token, admin}` |
| `POST /api/admin/auth/logout` | admin | revokes session |
| `GET /api/admin/users` | admin | filters: role, status, q; pagination |
| `GET /api/admin/users/{role}/{id}` | admin | detail + relationships |
| `PATCH /api/admin/users/{id}/status` | admin | reason required; audited |
| `GET /api/admin/families` | admin | `broken_only` flag |
| `GET /api/admin/families/{id}` | admin | parent+athletes+invites+flags |
| `GET /api/admin/invites` | admin | filter: status |
| `POST /api/admin/invites/{id}/resend` | admin | bumps reminder history; audited |
| `GET /api/admin/audit-logs` | admin | filter: action; pagination |
| `GET /api/admin/dashboard` | admin | KPI summary |
| `POST /api/events` | public | best-effort analytics collector → 202 |

### Testing strategy
- **Unit (pytest, in-memory SQLite):** migrations (Task 1), emit isolation incl. forced-failure (Task 2), auth token/OTP/expiry/inactive (Task 3), service relationship-flag derivation + status/audit + invite reminders (Task 4).
- **Integration (`TestClient`):** unauthed 401, OTP login round-trip, status PATCH reason-validation + audit write, public collector insert (Task 6), lifecycle emit on real signup (Task 7).
- **Regression gate:** `pytest -q` runs green after every task (existing 20+ test modules must stay green; admin changes are purely additive).
- **Frontend:** `npm run build` + `npm run lint` + the Task 9 manual smoke script. No FE unit framework is introduced (none exists; introducing one is out of scope).
- **Security checks to include:** assert no `/api/admin/*` route responds without a valid token; assert tokens are stored only as hashes (`admin_sessions.token_hash`); assert OTP codes are stored only as hashes.

### Rollout strategy
1. **Merge to `main`** → CI auto-deploys to Fly.io (`.github/workflows/fly-deploy.yml`).
2. **Run migrations on the server** (manual step per HLD §13): `fly ssh console -a fuelup-youth -C "python db/setup.py"`. Migrations are idempotent and additive — zero downtime, safe to re-run.
3. **Set the bootstrap secret:** `fly secrets set ADMIN_BOOTSTRAP_EMAILS="founder1@…,founder2@…" -a fuelup-youth`. On next boot, `seed_admins_from_env()` upserts those admins.
4. **Smoke on prod:** hit `/admin`, complete OTP login (code emailed via existing Gmail SMTP), verify Dashboard loads and one suspend→reactivate writes an audit row.
5. **Backfill status (optional, low-risk):** a one-off SQL pass can set `parents.status='active'` where `consent_confirmed=1`; left null otherwise (the console derives display). Defer until the console is in daily use.
6. **Rollback:** revert the merge; the additive tables/columns can remain (unused) — no destructive rollback needed. Sessions can be invalidated by `DELETE FROM admin_sessions`.

### AI agent execution plan
- **Mode:** subagent-driven-development — one fresh subagent per task, two-stage review (does it follow the plan? is the code correct?) between tasks.
- **Order & parallelism:** Tasks 1→2→3→4 are sequential (each builds on the prior schema/service). Task 5 (models) can run anytime after Task 1. Task 6 depends on 3+4+5. Task 7 depends on 2+6. Tasks 8–9 (frontend) depend only on the API contract from Task 6 and can proceed in parallel with Task 7.
- **Per-task contract:** the subagent must (a) write the failing test first, (b) show it fail, (c) implement, (d) show it pass, (e) run full `pytest -q`, (f) commit with the given message. No task is "done" until `pytest -q` is green.
- **Guardrails for the agent:** additive-only (never `DROP`/`ALTER … DROP`); never log raw OTP/token/PII; `emit()` calls must never be wrapped in a way that can raise; match existing import/style conventions in each touched file (verify the real handler names in `parents.py`/`athletes.py` before editing — Task 7 Step 1 note).
- **Review checkpoints:** after Task 1 (schema shape), after Task 6 (full API reachable + guarded), after Task 9 (console usable end-to-end).

### Acceptance criteria
- [ ] `pytest -q` is green, including all new admin/analytics test modules.
- [ ] No `/api/admin/*` endpoint (except the two auth routes) returns anything but 401 without a valid bearer token.
- [ ] An admin can log in via email OTP and receive a session token; logout revokes it; expired/inactive sessions are rejected.
- [ ] Users list shows parents + athletes with status; Families view surfaces `consent_pending`, `no_athlete`, and `profile_unclaimed` flags for the three relationship-gap cases.
- [ ] A status change (suspend/reactivate) requires a reason, updates the row, and writes an `admin_audit_log` entry with actor, action, target, and reason.
- [ ] Resend invite bumps `reminder_count` + `last_reminded_at` and (when an email is present) attempts delivery.
- [ ] `POST /api/events` and server-side lifecycle emits write `analytics_events` rows; a forced DB failure in `emit()` does not break the originating request.
- [ ] OTP codes and session tokens are persisted only as SHA-256 hashes (verified by inspecting `admin_otp_codes.code_hash` / `admin_sessions.token_hash`).
- [ ] Migrations are idempotent: running `python db/setup.py` twice and booting twice produces no errors and no duplicate columns.
- [ ] `npm run build` and `npm run lint` pass; `/admin` renders login then the five tabs.

---

## Self-Review

**Spec coverage** (against [ADMIN_MODULE_DESIGN.md](../../ADMIN_MODULE_DESIGN.md) Phase 1 + emit):
- Users (parents/athletes/admins) → Tasks 1,4,6,9 ✓
- User status (active/suspended + derived) → Tasks 1,4 (stored active/suspended; invited/inactive derivation deferred to read-time, noted) ✓
- Parent↔athlete relationships + 3 gap cases → Task 4 `_family_flags` + tests ✓
- Invites (pending/accepted/expired) + resend + reminder history → Tasks 1,4,6 ✓
- Safe support actions (resend/deactivate/reactivate/view) → Tasks 4,6,9 ✓; no destructive actions ✓
- Audit logging on every write → Task 4 `audit()` + tests ✓
- RBAC seam (`role` + `require_role`) → Tasks 1,3 ✓
- Admin auth replacing static key → Task 3 (token), Task 6 (endpoints) ✓
- Analytics emit spine (Phase-1 portion) → Tasks 2,6,7 ✓
- Privacy (athlete first-name-only projection) → Task 4 `_ATHLETE_PUBLIC` ✓
- Founder daily email / analytics dashboards → **out of this plan by design** (Phase 2); explicitly scoped out.

**Placeholder scan:** No "TBD/implement later/add validation" left; every code step shows full code. Two explicit "verify the real handler name" notes in Task 7 are intentional (they depend on existing code the worker must read) and are accompanied by the exact emit lines to add.

**Type/name consistency:** `hash_secret` used in both `admin_auth.py` and `tests/test_admin_auth.py`; `emit(...)` signature identical across `analytics_service.py`, Task 6 collector, and Task 7 call sites; `set_user_status(actor_admin_id, role, user_id, status, reason)` identical in service, route, and tests; `require_admin` returns the admin dict consumed as `admin["id"]` everywhere. Router exposes both `router` and `events_router`, matched by the two `include_router` calls in Task 6 Step 4.

**Gaps fixed inline:** added the explicit "verify existing handler names" note in Task 7 so the worker doesn't guess `parents.py`/`athletes.py` internals; clarified the App.jsx ESM-import variant in Task 8 Step 4.
