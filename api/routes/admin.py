"""
Admin Module — auth + family-centric Users management.

Every route except /login is guarded by the require_admin dependency (applied on
the router via dependencies=[...] in main.py is NOT possible here because /login
must stay open, so guards are applied per-route below).

Delete strategy: HARD delete. There is no is_deleted column anywhere in the
schema and ~20 tables reference athlete_id/parent_id, so a soft-delete flag would
require filtering every user-facing query app-wide. Instead we hard-delete every
child row across all referencing tables inside a single transaction, after
showing the operator an accurate cascade preview. Missing tables (schema drift
across environments, e.g. account_athlete only exists post phase-0 migration) are
skipped defensively via _table_exists.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.database import get_conn
from api.services import admin_auth, streak_service
from api.services.admin_auth import require_admin, write_audit

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tables holding rows keyed by a single athlete_id column. Deleted when an
# athlete (or its parent) is removed. Order doesn't matter (no enforced FKs
# between them) — all are deleted before the athlete row itself.
ATHLETE_CHILD_TABLES = [
    "events", "meal_logs", "meal_plans", "meal_plan_selections", "daily_targets",
    "water_logs", "push_subscriptions", "expo_push_tokens", "athlete_article_picks",
    "athlete_logins", "athlete_food_prefs", "notification_log", "window_logs",
    "confirmations", "streak_state", "pantry_list_items", "account_athlete",
    "feature_requests",
]

# Parent-level tables keyed directly by the parent's id (child athletes are
# cascaded separately). account_athlete uses account_id = the parent account id.
PARENT_CHILD_TABLES = [
    ("otp_codes", "parent_id"),
    ("expo_push_tokens", "parent_id"),
    ("account_athlete", "account_id"),
]


# ── Request models (declared inline, matching auth.py / feedback.py) ─────────
class AdminLoginRequest(BaseModel):
    password: str


class ParentUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None


class AthleteUpdate(BaseModel):
    first_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    weight_lbs: Optional[float] = None
    height_ft: Optional[int] = None
    height_in: Optional[float] = None
    position: Optional[str] = None
    competition_level: Optional[str] = None
    date_of_birth: Optional[str] = None
    byga_ics_url: Optional[str] = None
    playmetrics_ics_url: Optional[str] = None


class DeleteConfirm(BaseModel):
    confirm: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────
def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (name,),
    ).fetchone() is not None


def _has_col(conn, table: str, col: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
        (table, col),
    ).fetchone() is not None


def _calendar_status(byga_url, playmetrics_url, imported_count, event_count) -> str:
    """Derive the athlete's calendar state for the admin badge:
      byga / playmetrics — recurring auto-sync connected (an .ics subscription URL)
      imported           — parent uploaded a one-time .ics file (events carry a uid)
      manual             — has events but all hand-entered (uid NULL)
      none               — no schedule at all
    `source` can't be used — it was backfilled to 'manual' for every pre-existing
    row — so the .ics-import signal is the iCalendar uid on the event."""
    if byga_url:
        return "byga"
    if playmetrics_url:
        return "playmetrics"
    if (imported_count or 0) > 0:
        return "imported"
    if (event_count or 0) > 0:
        return "manual"
    return "none"


def _active_parent_clause(conn, alias: str) -> str:
    """Exclude anonymized tombstones left by the old AthFuelPath-Admin soft-delete
    (parents.account_status = 'hard_deleted'). The column only exists in
    production (added by that deployment), so this is a no-op on fresh/test DBs."""
    if _has_col(conn, "parents", "account_status"):
        return f"({alias}.account_status IS NULL OR {alias}.account_status != 'hard_deleted')"
    return ""


def _count(conn, table: str, where: str, params) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", params).fetchone()
    return row["count"] if row else 0


def _athlete_ids(conn, parent_id: int) -> list[int]:
    rows = conn.execute("SELECT id FROM athletes WHERE parent_id = %s", (parent_id,)).fetchall()
    return [r["id"] for r in rows]


# ── Cascade preview + delete ─────────────────────────────────────────────────
def _preview_athlete(conn, athlete_id: int) -> dict:
    counts = {}
    for table in ATHLETE_CHILD_TABLES:
        n = _count(conn, table, "athlete_id = %s", (athlete_id,))
        if n:
            counts[table] = n
    # shopping_list_items via list_id → shopping_lists.athlete_id
    if _table_exists(conn, "shopping_lists"):
        list_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM shopping_lists WHERE athlete_id = %s", (athlete_id,)).fetchall()]
        if list_ids and _table_exists(conn, "shopping_list_items"):
            q = ",".join(["%s"] * len(list_ids))
            n = conn.execute(
                f"SELECT COUNT(*) AS count FROM shopping_list_items WHERE list_id IN ({q})", list_ids
            ).fetchone()["count"]
            if n:
                counts["shopping_list_items"] = n
        if list_ids:
            counts["shopping_lists"] = len(list_ids)
    return counts


def _delete_athlete(conn, athlete_id: int) -> None:
    """Delete every child row for one athlete, then the athlete. Caller owns the
    transaction/commit."""
    if _table_exists(conn, "shopping_lists"):
        list_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM shopping_lists WHERE athlete_id = %s", (athlete_id,)).fetchall()]
        if list_ids and _table_exists(conn, "shopping_list_items"):
            q = ",".join(["%s"] * len(list_ids))
            conn.execute(f"DELETE FROM shopping_list_items WHERE list_id IN ({q})", list_ids)
        conn.execute("DELETE FROM shopping_lists WHERE athlete_id = %s", (athlete_id,))
    for table in ATHLETE_CHILD_TABLES:
        if _table_exists(conn, table):
            conn.execute(f"DELETE FROM {table} WHERE athlete_id = %s", (athlete_id,))
    conn.execute("DELETE FROM athletes WHERE id = %s", (athlete_id,))


def _merge_counts(dst: dict, src: dict) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


# ── Auth ─────────────────────────────────────────────────────────────────────
@router.post("/login")
def admin_login(data: AdminLoginRequest, request: Request):
    ip = _client_ip(request)
    admin_auth.check_rate_limit(ip)
    if not admin_auth.password_configured():
        raise HTTPException(503, "Admin login is not configured.")
    if not admin_auth.verify_password(data.password):
        admin_auth.record_failed_login(ip)
        raise HTTPException(401, "Incorrect password.")
    admin_auth.clear_failed_logins(ip)
    return {"token": admin_auth.mint_token(), "expires_in": admin_auth.TOKEN_TTL_SECONDS}


# ── Users list ───────────────────────────────────────────────────────────────
@router.get("/users")
def list_families(
    _: bool = Depends(require_admin),
    page: int = 1,
    limit: int = 25,
    search: str = "",
    calendar: str = "any",       # any | byga | playmetrics | none
    has_athletes: str = "any",   # any | yes | no
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort: str = "newest",        # newest | name | last_active
):
    page = max(1, page)
    limit = max(1, min(100, limit))
    offset = (page - 1) * limit
    stale_cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()

    conn = get_conn()
    where = []
    params: list = []
    active_clause = _active_parent_clause(conn, "p")
    if active_clause:
        where.append(active_clause)
    if search:
        like = f"%{search.strip()}%"
        where.append(
            "(p.full_name LIKE %s OR p.email LIKE %s OR EXISTS("
            "SELECT 1 FROM athletes a2 WHERE a2.parent_id = p.id AND a2.first_name LIKE %s))"
        )
        params += [like, like, like]
    if calendar == "byga":
        where.append("EXISTS(SELECT 1 FROM athletes a3 WHERE a3.parent_id = p.id AND a3.byga_ics_url IS NOT NULL)")
    elif calendar == "playmetrics":
        where.append("EXISTS(SELECT 1 FROM athletes a3 WHERE a3.parent_id = p.id AND a3.playmetrics_ics_url IS NOT NULL)")
    elif calendar == "none":
        where.append("NOT EXISTS(SELECT 1 FROM athletes a3 WHERE a3.parent_id = p.id AND "
                     "(a3.byga_ics_url IS NOT NULL OR a3.playmetrics_ics_url IS NOT NULL))")
    if date_from:
        where.append("p.created_at >= %s")
        params.append(date_from)
    if date_to:
        where.append("p.created_at <= %s")
        params.append(date_to)

    having = ""
    if has_athletes == "yes":
        having = "HAVING COUNT(a.id) > 0"
    elif has_athletes == "no":
        having = "HAVING COUNT(a.id) = 0"

    order = {
        "name": "LOWER(p.full_name) ASC",
        "last_active": "last_active DESC",
        "newest": "p.created_at DESC",
    }.get(sort, "p.created_at DESC")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    base = f"""
        SELECT p.id, p.full_name, p.email, p.created_at,
               COUNT(a.id) AS athlete_count,
               SUM(CASE WHEN a.byga_ics_url IS NOT NULL OR a.playmetrics_ics_url IS NOT NULL
                        THEN 1 ELSE 0 END) AS connected_count,
               SUM(CASE WHEN a.byga_ics_url IS NOT NULL THEN 1 ELSE 0 END) AS byga_count,
               SUM(CASE WHEN a.playmetrics_ics_url IS NOT NULL THEN 1 ELSE 0 END) AS playmetrics_count,
               (SELECT COUNT(*) FROM events e JOIN athletes aa ON aa.id = e.athlete_id
                 WHERE aa.parent_id = p.id AND e.synced_at IS NOT NULL AND e.synced_at > %s) AS recent_synced_count,
               (SELECT COUNT(*) FROM events e2 JOIN athletes ab ON ab.id = e2.athlete_id
                 WHERE ab.parent_id = p.id AND e2.uid IS NOT NULL AND e2.uid != '') AS imported_count,
               (SELECT MAX(ts) FROM (
                    SELECT MAX(ml.logged_at) AS ts FROM meal_logs ml JOIN athletes aa ON aa.id = ml.athlete_id WHERE aa.parent_id = p.id
                    UNION ALL
                    SELECT MAX(wl.created_at) FROM window_logs wl JOIN athletes aa ON aa.id = wl.athlete_id WHERE aa.parent_id = p.id
                    UNION ALL
                    SELECT MAX(w.updated_at) FROM water_logs w JOIN athletes aa ON aa.id = w.athlete_id WHERE aa.parent_id = p.id
               )) AS last_active
        FROM parents p
        LEFT JOIN athletes a ON a.parent_id = p.id
        {where_sql}
        GROUP BY p.id
        {having}
    """
    try:
        # recent_synced_count subquery param comes first in the SELECT param order
        select_params = [stale_cutoff] + params
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM ({base})", select_params
        ).fetchone()["count"]
        rows = conn.execute(
            f"{base} ORDER BY {order} LIMIT %s OFFSET %s",
            select_params + [limit, offset],
        ).fetchall()

        cutoff_3d = (datetime.utcnow() - timedelta(days=3)).isoformat()
        items = []
        for r in rows:
            d = dict(r)
            athlete_count = d["athlete_count"] or 0
            connected = d["connected_count"] or 0
            imported = d["imported_count"] or 0
            # Nested athlete summaries for the row (name, sport/position, age).
            # event_count/imported_count drive the smarter calendar badge.
            aths = conn.execute(
                "SELECT a.id, a.first_name, a.age, a.position, a.competition_level, "
                "a.byga_ics_url, a.playmetrics_ics_url, "
                "(SELECT COUNT(*) FROM events e WHERE e.athlete_id = a.id) AS event_count, "
                "(SELECT COUNT(*) FROM events e WHERE e.athlete_id = a.id AND e.uid IS NOT NULL AND e.uid != '') AS imported_count "
                "FROM athletes a WHERE a.parent_id = %s ORDER BY a.id",
                (d["id"],),
            ).fetchall()
            chips = []
            if athlete_count == 0:
                chips.append("no_athletes")
            else:
                # "never connected" now means no auto-sync AND no uploaded .ics file
                # (manual-only or empty). Families who uploaded a calendar file count
                # as connected and are not flagged.
                if connected == 0 and imported == 0 and d["created_at"] and d["created_at"] < cutoff_3d:
                    chips.append("never_connected")
                if connected > 0 and (d["recent_synced_count"] or 0) == 0:
                    chips.append("sync_stale")
            items.append({
                "id": d["id"],
                "full_name": d["full_name"],
                "email": d["email"],
                "created_at": d["created_at"],
                "last_active": d["last_active"],
                "athlete_count": athlete_count,
                "byga_count": d["byga_count"] or 0,
                "playmetrics_count": d["playmetrics_count"] or 0,
                "athletes": [
                    {
                        "id": a["id"], "first_name": a["first_name"], "age": a["age"],
                        "position": a["position"], "competition_level": a["competition_level"],
                        "calendar": _calendar_status(a["byga_ics_url"], a["playmetrics_ics_url"],
                                                     a["imported_count"], a["event_count"]),
                        "event_count": a["event_count"] or 0,
                        "imported_count": a["imported_count"] or 0,
                    } for a in aths
                ],
                "chips": chips,
            })
        return {"items": items, "total": total, "page": page, "limit": limit}
    finally:
        conn.close()


# ── Family detail ────────────────────────────────────────────────────────────
def _athlete_engagement(athlete: dict, conn) -> dict:
    """Is the app actually being used by / reaching this athlete? All reads come
    from tables the app already writes — no new instrumentation."""
    aid = athlete["id"]
    meals = conn.execute(
        "SELECT COUNT(*) AS n, MAX(logged_at) AS last FROM meal_logs WHERE athlete_id = %s",
        (aid,)).fetchone()
    water = conn.execute(
        "SELECT COUNT(*) AS n, MAX(log_date) AS last FROM water_logs WHERE athlete_id = %s",
        (aid,)).fetchone()
    pantry = conn.execute(
        "SELECT week_start, COUNT(*) AS n, SUM(checked) AS done FROM pantry_list_items "
        "WHERE athlete_id = %s GROUP BY week_start ORDER BY week_start DESC LIMIT 1",
        (aid,)).fetchone()
    login = conn.execute(
        "SELECT email, created_at FROM athlete_logins WHERE athlete_id = %s", (aid,)).fetchone()
    push_tokens = conn.execute(
        "SELECT COUNT(*) AS count FROM expo_push_tokens WHERE athlete_id = %s", (aid,)).fetchone()["count"]
    last_push = conn.execute(
        "SELECT MAX(sent_at) AS max_sent_at FROM notification_log WHERE athlete_id = %s", (aid,)).fetchone()["max_sent_at"]
    try:
        streak = streak_service.compute_current_streak(aid, conn)["current"]
    except Exception:   # engagement is informational — never fail the page over it
        streak = None
    return {
        "meal_logs":  {"total": meals["n"], "last_at": meals["last"]},
        "water_logs": {"total": water["n"], "last_date": water["last"]},
        "streak": streak,
        "pantry": {
            "latest_week_start": pantry["week_start"] if pantry else None,
            "item_count":        pantry["n"] if pantry else 0,
            "checked_count":     int(pantry["done"] or 0) if pantry else 0,
        },
        "blueprint_generated": bool(athlete.get("blueprint_json")),
        "athlete_login": {
            "exists": login is not None,
            "email": login["email"] if login else None,
            "created_at": login["created_at"] if login else None,
        },
        "push": {"tokens": push_tokens, "last_push_at": last_push},
    }


@router.get("/users/{parent_id}")
def family_detail(parent_id: int, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        prow = conn.execute("SELECT * FROM parents WHERE id = %s", (parent_id,)).fetchone()
        if not prow:
            raise HTTPException(404, "Parent not found.")
        parent = dict(prow)
        parent["push_devices"] = [dict(r) for r in conn.execute(
            "SELECT platform, timezone, created_at FROM expo_push_tokens "
            "WHERE parent_id = %s ORDER BY created_at DESC", (parent_id,)).fetchall()]
        parent["push_tokens"] = len(parent["push_devices"])

        athletes = []
        for a in conn.execute("SELECT * FROM athletes WHERE parent_id = %s ORDER BY id", (parent_id,)).fetchall():
            ad = dict(a)
            stats = conn.execute(
                "SELECT source, COUNT(*) AS n, "
                "SUM(CASE WHEN event_date >= sqlite_today() THEN 1 ELSE 0 END) AS upcoming "
                "FROM events WHERE athlete_id = %s GROUP BY source",
                (ad["id"],),
            ).fetchall()
            by_source, total_events, upcoming_events = {}, 0, 0
            for s in stats:
                sd = dict(s)
                by_source[sd["source"] or "manual"] = sd["n"]
                total_events += sd["n"]
                upcoming_events += sd["upcoming"] or 0
            last_synced = conn.execute(
                "SELECT MAX(synced_at) AS max_synced_at FROM events WHERE athlete_id = %s AND synced_at IS NOT NULL",
                (ad["id"],),
            ).fetchone()["max_synced_at"]
            imported_events = conn.execute(
                "SELECT COUNT(*) AS count FROM events WHERE athlete_id = %s AND uid IS NOT NULL AND uid != ''",
                (ad["id"],),
            ).fetchone()["count"]
            ad["event_stats"] = {
                "total": total_events, "upcoming": upcoming_events, "by_source": by_source,
                "imported": imported_events, "manual": total_events - imported_events,
            }
            ad["last_synced_at"] = last_synced
            ad["calendar"] = _calendar_status(
                ad.get("byga_ics_url"), ad.get("playmetrics_ics_url"), imported_events, total_events)
            ad["engagement"] = _athlete_engagement(ad, conn)
            athletes.append(ad)

        athlete_ids = [a["id"] for a in athletes]
        upcoming = []
        recent_ideas = []
        if athlete_ids:
            q = ",".join(["%s"] * len(athlete_ids))
            upcoming = [dict(e) for e in conn.execute(
                f"SELECT * FROM events WHERE athlete_id IN ({q}) AND event_date >= sqlite_today() "
                f"ORDER BY event_date, start_time LIMIT 5", athlete_ids
            ).fetchall()]
        # Feature ideas: match by any family athlete_id OR the parent's email.
        if _table_exists(conn, "feature_requests"):
            if athlete_ids:
                q = ",".join(["%s"] * len(athlete_ids))
                recent_ideas = [dict(f) for f in conn.execute(
                    f"SELECT * FROM feature_requests WHERE athlete_id IN ({q}) OR lower(email) = lower(%s) "
                    f"ORDER BY submitted_at DESC LIMIT 10", athlete_ids + [parent["email"]]
                ).fetchall()]
            else:
                recent_ideas = [dict(f) for f in conn.execute(
                    "SELECT * FROM feature_requests WHERE lower(email) = lower(%s) "
                    "ORDER BY submitted_at DESC LIMIT 10", (parent["email"],)
                ).fetchall()]

        return {
            "parent": parent,
            "athletes": athletes,
            "activity": {
                "upcoming_events": upcoming,
                "feature_ideas": recent_ideas,
                # problem_reports has no parent/athlete column in the schema, so it
                # cannot be scoped to a family — shown only as a global count on the
                # analytics dashboard, not here.
            },
        }
    finally:
        conn.close()


# ── Edit parent ──────────────────────────────────────────────────────────────
@router.put("/parents/{parent_id}")
def update_parent(parent_id: int, data: ParentUpdate, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM parents WHERE id = %s", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        fields, values, changed = [], [], {}
        new_email = None
        if data.full_name is not None:
            fields.append("full_name = %s"); values.append(data.full_name); changed["full_name"] = data.full_name
        if data.email is not None:
            new_email = data.email.strip().lower()
            if not _EMAIL_RE.match(new_email):
                raise HTTPException(400, "Invalid email format.")
            fields.append("email = %s"); values.append(new_email); changed["email"] = new_email
        if not fields:
            return dict(row)
        try:
            conn.execute("BEGIN")
            conn.execute(f"UPDATE parents SET {', '.join(fields)} WHERE id = %s", values + [parent_id])
            if new_email is not None:
                # auth v2.1 Phase 6 corrective fix (production audit): this
                # admin edit used to touch only parents.email, leaving that
                # parent's provider='email' auth_identities row's
                # provider_subject pointing at the OLD email. Since
                # resolve_identity() treats (provider, provider_subject) as
                # authoritative and only auto-links by email when there is
                # NO existing row for the provider, that stale row meant the
                # parent's NEXT ordinary login (via the NEW email) would miss
                # the exact-match lookup, fall into resolve_identity()'s
                # auto-link path, and try to INSERT a second provider='email'
                # row for the same parent -- which migration 004's
                # UNIQUE(provider, parent_id) partial index rejects, breaking
                # that login with an unrelated-looking 409. Updating the
                # existing row's provider_subject in the SAME transaction as
                # the parents.email UPDATE keeps them in sync atomically and
                # guarantees at most one provider='email' row per parent —
                # this is always an UPDATE, never an INSERT.
                #
                # If no provider='email' row exists yet for this parent, this
                # UPDATE simply matches zero rows -- NOT an error. Read
                # api/services/identity_resolver.py and api/routes/
                # onboarding.py: auth_identities rows are created lazily, by
                # resolve_identity()'s auto-link step on first login, not at
                # parent-creation time -- so a parent who has never logged in
                # yet legitimately has zero auth_identities rows. In that
                # case there's nothing to keep in sync here; that parent's
                # first login will auto-link correctly using the
                # just-updated parents.email.
                #
                # Cross-owner collision (new email already belongs to a
                # DIFFERENT parent/athlete's provider='email' identity): not
                # re-checked here by hand -- auth_identities already carries
                # CONSTRAINT auth_identities_provider_subject_uniq UNIQUE
                # (provider, provider_subject) (db/postgres/003_auth_identities
                # .sql), so this UPDATE raises the same psycopg.errors.
                # UniqueViolation caught below, and the whole transaction
                # (both writes) rolls back together -- exactly the established
                # catch-and-rollback idiom used elsewhere (identity_resolver.
                # py, auth.py's corrective pass), not a separate pre-check-
                # then-write race.
                conn.execute(
                    "UPDATE auth_identities SET provider_subject = %s, email = %s, "
                    "updated_at = sqlite_now() WHERE provider = 'email' AND parent_id = %s",
                    (new_email, new_email, parent_id),
                )
            conn.commit()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(409, "Another parent already uses that email.")
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, str(e))
        write_audit("update_parent", "parent", parent_id, changed)
        return dict(conn.execute("SELECT * FROM parents WHERE id = %s", (parent_id,)).fetchone())
    finally:
        conn.close()


# ── Edit athlete ─────────────────────────────────────────────────────────────
@router.put("/athletes/{athlete_id}")
def update_athlete(athlete_id: int, data: AthleteUpdate, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        allowed = ["first_name", "age", "gender", "weight_lbs", "height_ft", "height_in",
                   "position", "competition_level", "date_of_birth",
                   "byga_ics_url", "playmetrics_ics_url"]
        fields, values, changed = [], [], {}
        payload = data.model_dump(exclude_unset=True)
        for key in allowed:
            if key in payload:
                fields.append(f"{key} = %s"); values.append(payload[key]); changed[key] = payload[key]
        if not fields:
            return dict(row)
        conn.execute(f"UPDATE athletes SET {', '.join(fields)} WHERE id = %s", values + [athlete_id])
        conn.commit()
        write_audit("update_athlete", "athlete", athlete_id, changed)
        return dict(conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone())
    finally:
        conn.close()


# ── Delete preview + delete: athlete ─────────────────────────────────────────
@router.get("/athletes/{athlete_id}/delete-preview")
def preview_delete_athlete(athlete_id: int, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT first_name FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        return {"athlete_id": athlete_id, "first_name": row["first_name"], "counts": _preview_athlete(conn, athlete_id)}
    finally:
        conn.close()


@router.delete("/athletes/{athlete_id}")
def delete_athlete(athlete_id: int, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT first_name FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        counts = _preview_athlete(conn, athlete_id)
        try:
            conn.execute("BEGIN")
            _delete_athlete(conn, athlete_id)
            write_audit("delete_athlete", "athlete", athlete_id,
                        {"first_name": row["first_name"], "cascade": counts}, conn=conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, str(e))
        return {"deleted": True, "athlete_id": athlete_id, "cascade": counts}
    finally:
        conn.close()


# ── Delete preview + delete: parent (full family) ────────────────────────────
def _preview_parent(conn, parent_id: int) -> dict:
    athlete_ids = _athlete_ids(conn, parent_id)
    counts: dict = {"athletes": len(athlete_ids)}
    for aid in athlete_ids:
        _merge_counts(counts, _preview_athlete(conn, aid))
    for table, col in PARENT_CHILD_TABLES:
        n = _count(conn, table, f"{col} = %s", (parent_id,))
        if n:
            counts[f"{table}:{col}"] = counts.get(f"{table}:{col}", 0) + n
    return counts


@router.get("/parents/{parent_id}/delete-preview")
def preview_delete_parent(parent_id: int, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT full_name FROM parents WHERE id = %s", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        return {"parent_id": parent_id, "full_name": row["full_name"], "counts": _preview_parent(conn, parent_id)}
    finally:
        conn.close()


@router.delete("/parents/{parent_id}")
def delete_parent(parent_id: int, data: DeleteConfirm, _: bool = Depends(require_admin)):
    if (data.confirm or "").strip() != "DELETE":
        raise HTTPException(400, "Type DELETE to confirm parent deletion.")
    conn = get_conn()
    try:
        row = conn.execute("SELECT full_name FROM parents WHERE id = %s", (parent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Parent not found.")
        counts = _preview_parent(conn, parent_id)
        try:
            conn.execute("BEGIN")
            for aid in _athlete_ids(conn, parent_id):
                _delete_athlete(conn, aid)
            for table, col in PARENT_CHILD_TABLES:
                if _table_exists(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE {col} = %s", (parent_id,))
            conn.execute("DELETE FROM parents WHERE id = %s", (parent_id,))
            write_audit("delete_parent", "parent", parent_id,
                        {"full_name": row["full_name"], "cascade": counts}, conn=conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, str(e))
        return {"deleted": True, "parent_id": parent_id, "cascade": counts}
    finally:
        conn.close()
