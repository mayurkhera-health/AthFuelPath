import json
import logging
from dataclasses import dataclass
from typing import Optional

from api.database import get_conn
from api.services.knowledge.approved_sources import resolve_organization
from api.services.knowledge.embedding_utils import (
    EMBEDDING_MODEL,
    cosine_similarity,
    embed_text,
    pack_embedding,
    unpack_embedding,
)
from api.services.knowledge.web_search import WebSearchResult, search_approved_sites

logger = logging.getLogger(__name__)

MIN_SCORE = 0.25
DEFAULT_TOP_N = 5
WEB_TOP_N = 3


@dataclass
class KnowledgeChunk:
    chunk_id: int
    item_id: int
    slug: str
    title: str
    category: str
    source: str
    source_urls: list
    organization_id: Optional[str]
    organization_name: Optional[str]
    organization_url: Optional[str]
    applicable_age_range: str
    tags: list
    review_status: str
    heading: Optional[str]
    content: str
    score: float
    origin: str = "local"


def _load_local_rows() -> list[tuple]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT kc.id as chunk_id, kc.item_id, kc.heading, kc.content, kc.embedding,
                      ki.slug, ki.title, ki.category, ki.source, ki.source_urls,
                      ki.organization, ki.applicable_age_range, ki.tags, ki.review_status
               FROM knowledge_chunks kc
               JOIN knowledge_items ki ON kc.item_id = ki.id
               WHERE ki.review_status = 'approved'
               ORDER BY kc.item_id, kc.chunk_index"""
        ).fetchall()
    finally:
        conn.close()

    approved_rows = []
    for row in rows:
        source_urls = json.loads(row["source_urls"] or "[]")
        org = resolve_organization(row["source"], source_urls, row["organization"])
        if org:
            approved_rows.append((row, org, source_urls))
    return approved_rows


def _score_local_chunks(query_vec: list[float], approved_rows: list[tuple], top_n: int) -> list[KnowledgeChunk]:
    scored: list[KnowledgeChunk] = []

    for row, org, source_urls in approved_rows:
        vector = unpack_embedding(row["embedding"])
        if vector is None:
            try:
                vector = embed_text(row["content"])
                _persist_chunk_embedding(row["chunk_id"], vector)
            except Exception:
                logger.debug("Skipping chunk %s — embedding unavailable", row["chunk_id"], exc_info=True)
                continue

        score = cosine_similarity(query_vec, vector)
        if score < MIN_SCORE:
            continue

        scored.append(
            KnowledgeChunk(
                chunk_id=row["chunk_id"],
                item_id=row["item_id"],
                slug=row["slug"],
                title=row["title"],
                category=row["category"],
                source=row["source"],
                source_urls=source_urls,
                organization_id=org.id,
                organization_name=org.name,
                organization_url=org.url,
                applicable_age_range=row["applicable_age_range"],
                tags=json.loads(row["tags"] or "[]"),
                review_status=row["review_status"],
                heading=row["heading"],
                content=row["content"],
                score=score,
                origin="local",
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_n]


def _web_result_to_chunk(result: WebSearchResult) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=0,
        item_id=0,
        slug="web",
        title=result.title,
        category="live_web",
        source=result.organization_name,
        source_urls=[result.url],
        organization_id=result.organization_id,
        organization_name=result.organization_name,
        organization_url=result.organization_url,
        applicable_age_range="9-17",
        tags=["live_web"],
        review_status="approved",
        heading=None,
        content=result.content,
        score=result.score,
        origin="web",
    )


def _persist_chunk_embedding(chunk_id: int, vector: list[float]) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE knowledge_chunks SET embedding = %s, embedding_model = %s WHERE id = %s",
            (pack_embedding(vector), EMBEDDING_MODEL, chunk_id),
        )
        conn.commit()
    finally:
        conn.close()


def backfill_missing_embeddings(limit: int = 200) -> int:
    """Embed stored chunks that do not yet have vectors. Returns count updated."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT kc.id, kc.content
               FROM knowledge_chunks kc
               JOIN knowledge_items ki ON kc.item_id = ki.id
               WHERE ki.review_status = 'approved'
                 AND (kc.embedding IS NULL OR kc.embedding = '')
               LIMIT %s""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    updated = 0
    for row in rows:
        try:
            vector = embed_text(row["content"])
            _persist_chunk_embedding(row["id"], vector)
            updated += 1
        except Exception:
            logger.exception("Failed to embed knowledge chunk %s", row["id"])
    return updated


def retrieve(query: str, top_n: int = DEFAULT_TOP_N) -> list[KnowledgeChunk]:
    """
    Hybrid retrieval:
    1. Semantic search over ingested knowledge chunks (Bedrock embeddings)
    2. Live web search limited to approved organization domains
    """
    trimmed = (query or "").strip()
    if not trimmed:
        return []

    query_vec = embed_text(trimmed)
    approved_rows = _load_local_rows()
    local_hits = _score_local_chunks(query_vec, approved_rows, top_n=top_n)

    web_hits: list[KnowledgeChunk] = []
    try:
        web_results = search_approved_sites(trimmed, max_results=WEB_TOP_N)
        web_hits = [_web_result_to_chunk(r) for r in web_results if r.score >= MIN_SCORE]
    except Exception:
        logger.exception("Live approved-domain web retrieval failed")

    combined = local_hits + web_hits
    combined.sort(key=lambda c: c.score, reverse=True)
    return combined[:top_n]
