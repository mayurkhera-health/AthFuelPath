from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import json

from api.database import get_conn
from api.services.knowledge.ingest import ingest_file, ingest_all
from api.services.knowledge.answer import answer_with_knowledge
from api.services.knowledge.approved_sources import list_sources
from api.services.session_auth import require_session, assert_owns_athlete
from api.services.knowledge_admin import require_knowledge_admin_key as _require_admin

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    athlete_id: int
    is_first_message: bool = False
    history: list[dict] = []
    recipe_category: Optional[str] = None
    prefer_recipe: bool = False
    now: Optional[str] = None            # client local ISO timestamp — meal-timing framing
    latitude: Optional[float] = None     # device location — restaurant search only, optional
    longitude: Optional[float] = None
    persona: Optional[str] = None        # "parent" | "athlete" — who's asking, for response tone


class StatusUpdate(BaseModel):
    review_status: str


@router.get("/")
def list_knowledge_items(x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ki.slug, ki.title, ki.category, ki.review_status, ki.version,
                      ki.last_reviewed_date, ki.source, ki.ingested_at,
                      COUNT(kc.id) as chunk_count
               FROM knowledge_items ki
               LEFT JOIN knowledge_chunks kc ON kc.item_id = ki.id
               GROUP BY ki.id ORDER BY ki.review_status, ki.category, ki.slug"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/ingest")
def trigger_ingest(file_path: Optional[str] = None,
                   x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    if file_path:
        return ingest_file(file_path)
    return ingest_all()


@router.get("/sources")
def get_approved_sources():
    """Trusted organizations the Nutrition Coach draws from."""
    return {"sources": list_sources()}


@router.get("/health")
def coach_health(x_admin_key: Optional[str] = Header(None)):
    """Diagnostics for the Nutrition Coach pipeline. Reveals Bedrock config
    status and content counts, so it's gated behind the same knowledge-admin
    key as this file's other management endpoints."""
    _require_admin(x_admin_key)
    from api.services.bedrock_client import is_configured, model_id
    from api.database import get_conn

    conn = get_conn()
    try:
        chunk_count = conn.execute(
            """SELECT COUNT(*) AS count FROM knowledge_chunks kc
               JOIN knowledge_items ki ON kc.item_id = ki.id
               WHERE ki.review_status = 'approved'"""
        ).fetchone()["count"]
        item_count = conn.execute(
            "SELECT COUNT(*) AS count FROM knowledge_items WHERE review_status = 'approved'"
        ).fetchone()["count"]
    except Exception as exc:
        return {
            "status": "degraded",
            "error": str(exc),
            "bedrock_configured": is_configured(),
            "bedrock_model_id": model_id(),
        }
    finally:
        conn.close()

    return {
        "status": "ok" if chunk_count > 0 and is_configured() else "degraded",
        "approved_items": item_count,
        "approved_chunks": chunk_count,
        "bedrock_configured": is_configured(),
        "bedrock_model_id": model_id(),
    }


@router.post("/ask")
def ask_knowledge(body: AskRequest, identity=Depends(require_session)):
    """Nutrition Coach — answers from approved sports nutrition sources with citations."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, body.athlete_id, conn)
        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = %s", (body.athlete_id,)
        ).fetchone()
        if not athlete:
            raise HTTPException(404, "Athlete not found.")
        athlete_dict = dict(athlete)
    finally:
        conn.close()
    return answer_with_knowledge(
        body.question,
        athlete_dict,
        history=body.history,
        is_first_message=body.is_first_message,
        recipe_category=body.recipe_category,
        prefer_recipe=body.prefer_recipe,
        now=body.now,
        latitude=body.latitude,
        longitude=body.longitude,
        persona=body.persona,
    )


@router.get("/{slug}")
def get_knowledge_item(slug: str, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        item = conn.execute(
            "SELECT * FROM knowledge_items WHERE slug = %s", (slug,)
        ).fetchone()
        if not item:
            raise HTTPException(404, f"Knowledge item '{slug}' not found.")
        chunks = conn.execute(
            "SELECT chunk_index, heading, content FROM knowledge_chunks WHERE item_id = %s ORDER BY chunk_index",
            (item["id"],),
        ).fetchall()
        return {
            **dict(item),
            "source_urls": json.loads(item["source_urls"] or "[]"),
            "tags": json.loads(item["tags"] or "[]"),
            "chunks": [dict(c) for c in chunks],
        }
    finally:
        conn.close()


@router.patch("/{slug}/status")
def update_status(slug: str, body: StatusUpdate,
                  x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    allowed = {"draft", "approved", "archived"}
    if body.review_status not in allowed:
        raise HTTPException(400, f"review_status must be one of: {allowed}")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = %s", (slug,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Knowledge item '{slug}' not found.")
        conn.execute(
            "UPDATE knowledge_items SET review_status = %s WHERE slug = %s",
            (body.review_status, slug),
        )
        conn.commit()
        return {"slug": slug, "review_status": body.review_status}
    finally:
        conn.close()


@router.delete("/{slug}")
def archive_item(slug: str, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = %s", (slug,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Knowledge item '{slug}' not found.")
        conn.execute(
            "UPDATE knowledge_items SET review_status = 'archived' WHERE slug = %s",
            (slug,),
        )
        conn.commit()
        return {"slug": slug, "review_status": "archived", "message": "Item archived (not deleted)."}
    finally:
        conn.close()
