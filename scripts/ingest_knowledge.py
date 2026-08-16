#!/usr/bin/env python3
"""
CLI for ingesting knowledge files into the AthFuelPath knowledge base.

Usage:
  python scripts/ingest_knowledge.py --all
  python scripts/ingest_knowledge.py --file knowledge/iron_magnesium.md
  python scripts/ingest_knowledge.py --retire knowledge/old_guide.md
  python scripts/ingest_knowledge.py --status
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="AthFuelPath knowledge base ingestion")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Ingest all approved files in /knowledge")
    group.add_argument("--file", type=str, help="Ingest a single file")
    group.add_argument("--retire", type=str, help="Archive a knowledge item by slug or file path")
    group.add_argument("--status", action="store_true", help="List all knowledge items and their status")
    args = parser.parse_args()

    if args.all:
        from api.services.knowledge.ingest import ingest_all
        results = ingest_all()
        ok = [r for r in results if r["status"] == "ok"]
        skipped = [r for r in results if r["status"] == "skipped"]
        errors = [r for r in results if r["status"] == "error"]
        print(f"\n✓ Ingested: {len(ok)}")
        for r in ok:
            print(f"  {r['slug']} — {r['chunks']} chunks")
        if skipped:
            print(f"\n⊘ Skipped (not approved): {len(skipped)}")
            for r in skipped:
                print(f"  {r['slug']}: {r['reason']}")
        if errors:
            print(f"\n✗ Errors: {len(errors)}")
            for r in errors:
                print(f"  {r.get('slug', '?')}: {r['reason']}")

    elif args.file:
        from api.services.knowledge.ingest import ingest_file
        result = ingest_file(args.file)
        if result["status"] == "ok":
            print(f"✓ Ingested '{result['slug']}' — {result['chunks']} chunks")
        elif result["status"] == "skipped":
            print(f"⊘ Skipped: {result['reason']}")
        else:
            print(f"✗ Error: {result['reason']}")
            sys.exit(1)

    elif args.retire:
        from api.database import get_conn
        slug = Path(args.retire).stem
        conn = get_conn()
        try:
            row = conn.execute("SELECT id FROM knowledge_items WHERE slug = ?", (slug,)).fetchone()
            if not row:
                print(f"✗ No knowledge item found with slug '{slug}'")
                sys.exit(1)
            conn.execute(
                "UPDATE knowledge_items SET review_status = 'archived' WHERE slug = ?", (slug,)
            )
            conn.commit()
            print(f"✓ Archived '{slug}'")
        finally:
            conn.close()

    elif args.status:
        from api.database import get_conn
        conn = get_conn()
        try:
            rows = conn.execute(
                """SELECT ki.slug, ki.title, ki.review_status, ki.version,
                          ki.last_reviewed_date, COUNT(kc.id) as chunk_count
                   FROM knowledge_items ki
                   LEFT JOIN knowledge_chunks kc ON kc.item_id = ki.id
                   GROUP BY ki.id ORDER BY ki.review_status, ki.slug"""
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            print("No knowledge items found. Run --all to ingest.")
            return
        print(f"\n{'Slug':<25} {'Status':<12} {'v':<4} {'Chunks':<8} {'Last Reviewed'}")
        print("-" * 70)
        for r in rows:
            print(f"{r['slug']:<25} {r['review_status']:<12} {r['version']:<4} {r['chunk_count']:<8} {r['last_reviewed_date']}")


if __name__ == "__main__":
    main()
