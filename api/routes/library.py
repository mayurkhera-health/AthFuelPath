import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from api.database import get_conn
from api.services.nutrition_analysis import get_week_start
from api.services.library_service import generate_weekly_picks
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()

_ADMIN_KEY = os.getenv("KNOWLEDGE_ADMIN_KEY", "fuelup-admin")

VALID_CATEGORIES = {"iron", "gameday", "carbs", "recovery", "calcium", "hydration", "parents"}


class ArticleCreate(BaseModel):
    title: str
    summary: str
    body_markdown: str
    category: str
    audience: str = "both"
    read_time_min: int
    author: str = "Purvi Shah MS RDN"
    science_source: Optional[str] = None
    published_date: str
    is_active: int = 1


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    body_markdown: Optional[str] = None
    category: Optional[str] = None
    audience: Optional[str] = None
    read_time_min: Optional[int] = None
    author: Optional[str] = None
    science_source: Optional[str] = None
    published_date: Optional[str] = None
    is_active: Optional[int] = None


def _require_admin(key: Optional[str]):
    if key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin key required")


@router.get("/articles")
def get_articles(category: str = None, search: str = None, audience: str = None):
    conn = get_conn()
    try:
        query = "SELECT * FROM articles WHERE is_active = 1"
        params = []
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        if search:
            query += " AND (title LIKE ? OR summary LIKE ? OR category LIKE ? OR author LIKE ?)"
            params.extend([f"%{search}%"] * 4)
        if audience in ("athlete", "parent"):
            query += " AND audience IN (?, 'both')"
            params.append(audience)
        query += " ORDER BY published_date DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/picks/{athlete_id}")
def get_athlete_picks(athlete_id: int, identity=Depends(require_session)):
    """Ownership is proven by the caller's session token, not a client-supplied
    parent_id — a query-param comparison alone is guessable/spoofable by anyone
    who also knows (or guesses) the real parent_id. Also lazily generates this
    week's picks if they don't exist yet: generate_weekly_picks is idempotent
    (no-ops if a row already exists for the current week) and does no LLM/AI
    call, so it's safe and cheap to call on every read — nothing else in the
    app ever called it, which is why this section never appeared for a real
    athlete before."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        generate_weekly_picks(athlete_id, conn)
        conn.commit()

        week_start = get_week_start()
        rows = conn.execute("""
            SELECT a.*, p.alex_reason
            FROM articles a
            JOIN athlete_article_picks p ON a.id = p.article_id
            WHERE p.athlete_id = ? AND p.week_start = ? AND a.is_active = 1
            ORDER BY p.generated_at ASC
        """, (athlete_id, week_start)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/articles/{article_id}")
def get_article(article_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = ? AND is_active = 1",
            (article_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Article not found")
        return dict(row)
    finally:
        conn.close()


@router.post("/articles")
def create_article(payload: ArticleCreate, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")
    conn = get_conn()
    try:
        cursor = conn.execute("""
            INSERT INTO articles
                (title, summary, body_markdown, category, audience,
                 read_time_min, author, science_source, published_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.title, payload.summary, payload.body_markdown,
            payload.category, payload.audience, payload.read_time_min,
            payload.author, payload.science_source, payload.published_date,
            payload.is_active,
        ))
        conn.commit()
        return {"status": "created", "id": cursor.lastrowid}
    finally:
        conn.close()


@router.put("/articles/{article_id}")
def update_article(
    article_id: int,
    payload: ArticleUpdate,
    x_admin_key: Optional[str] = Header(None),
):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Article not found")
        fields = {k: v for k, v in payload.dict().items() if v is not None}
        if not fields:
            return {"status": "no_change"}
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE articles SET {set_clause} WHERE id = ?",
            list(fields.values()) + [article_id],
        )
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@router.post("/picks/{athlete_id}/generate")
def generate_picks(athlete_id: int, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        generate_weekly_picks(athlete_id, conn)
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.post("/admin/articles/{article_id}/publish")
def publish_article(article_id: int, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Article not found")
        conn.execute("UPDATE articles SET is_active = 1 WHERE id = ?", (article_id,))
        conn.commit()
        return {"status": "published"}
    finally:
        conn.close()


@router.post("/admin/articles/{article_id}/unpublish")
def unpublish_article(article_id: int, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        if not conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Article not found")
        conn.execute("UPDATE articles SET is_active = 0 WHERE id = ?", (article_id,))
        conn.commit()
        return {"status": "unpublished"}
    finally:
        conn.close()


@router.get("/admin/articles")
def admin_list_articles(x_admin_key: Optional[str] = Header(None)):
    """Returns all articles (including drafts) for the admin panel."""
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY published_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
