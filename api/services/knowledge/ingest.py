import re
import json
from datetime import datetime
from pathlib import Path

import yaml

from api.database import get_conn
from api.services.knowledge.embedding_utils import EMBEDDING_MODEL, embed_text, pack_embedding


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from Markdown body. Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return meta, body


def _chunk_markdown(body: str, max_chars: int = 1600) -> list[dict]:
    """
    Split Markdown body at H2/H3 headings.
    Returns list of {"heading": str, "content": str}.
    """
    heading_pattern = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
    chunks = []
    positions = [(m.start(), m.group(2), m.group(0)) for m in heading_pattern.finditer(body)]

    if not positions:
        for i in range(0, len(body), max_chars):
            chunks.append({"heading": None, "content": body[i:i + max_chars].strip()})
        return chunks

    if positions[0][0] > 0:
        intro = body[:positions[0][0]].strip()
        if intro:
            chunks.append({"heading": None, "content": intro})

    for i, (start, heading_text, _) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        section_body = body[start:end].strip()
        section_lines = section_body.split('\n', 1)
        content = section_lines[1].strip() if len(section_lines) > 1 else ""
        if not content:
            continue
        for j in range(0, max(1, len(content)), max_chars):
            chunks.append({
                "heading": heading_text,
                "content": content[j:j + max_chars].strip(),
            })

    return [c for c in chunks if c["content"]]


def ingest_file(file_path: str) -> dict:
    """
    Parse a knowledge Markdown file and store it in the database.
    Returns {"status": "ok"|"skipped"|"error", "slug": str, "chunks": int, "reason": str|None}.
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "reason": f"File not found: {file_path}"}

    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    status = meta.get("review_status", "draft")
    if status != "approved":
        return {
            "status": "skipped",
            "slug": path.stem,
            "chunks": 0,
            "reason": f"review_status is '{status}', only 'approved' files are ingested",
        }

    slug = path.stem
    chunks = _chunk_markdown(body)

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO knowledge_items
               (slug, title, category, source, source_urls, organization, last_reviewed_date,
                applicable_age_range, tags, review_status, version, file_path, ingested_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT(slug) DO UPDATE SET
                 title = excluded.title,
                 category = excluded.category,
                 source = excluded.source,
                 source_urls = excluded.source_urls,
                 organization = excluded.organization,
                 last_reviewed_date = excluded.last_reviewed_date,
                 applicable_age_range = excluded.applicable_age_range,
                 tags = excluded.tags,
                 review_status = excluded.review_status,
                 version = excluded.version,
                 file_path = excluded.file_path,
                 ingested_at = excluded.ingested_at""",
            (
                slug,
                meta.get("title", slug),
                meta.get("category", "general"),
                meta.get("source", ""),
                json.dumps(meta.get("source_urls", [])),
                meta.get("organization"),
                meta.get("last_reviewed_date", ""),
                meta.get("applicable_age_range", "9-17"),
                json.dumps(meta.get("tags", [])),
                status,
                meta.get("version", 1),
                str(path.resolve()),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

        item_row = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = %s", (slug,)
        ).fetchone()
        item_id = item_row["id"]

        conn.execute("DELETE FROM knowledge_chunks WHERE item_id = %s", (item_id,))
        for i, chunk in enumerate(chunks):
            embedding_json = None
            try:
                embedding_json = pack_embedding(embed_text(chunk["content"]))
            except Exception:
                pass
            conn.execute(
                """INSERT INTO knowledge_chunks
                   (item_id, chunk_index, heading, content, embedding, embedding_model)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    item_id,
                    i,
                    chunk["heading"],
                    chunk["content"],
                    embedding_json,
                    EMBEDDING_MODEL if embedding_json else None,
                ),
            )
        conn.commit()

    finally:
        conn.close()

    return {"status": "ok", "slug": slug, "chunks": len(chunks), "reason": None}


def ingest_all(knowledge_dir: str = "knowledge") -> list[dict]:
    """Ingest all .md files in the knowledge directory."""
    results = []
    for md_file in sorted(Path(knowledge_dir).glob("*.md")):
        results.append(ingest_file(str(md_file)))
    return results
