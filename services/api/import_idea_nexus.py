#!/usr/bin/env python3
"""Import a verified normalized Idea Nexus Ventures archive into the HGF guide index."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import chroma_collection, connection, guide_coord  # noqa: E402

SOURCE = "Idea Nexus Ventures archive"


def stable_id(row: dict) -> str:
    canonical = str(row.get("canonical_url") or "").strip()
    raw = f"inv:{canonical}:{row.get('id', '')}"
    return "inv-" + hashlib.sha256(raw.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.archive.read_text(encoding="utf-8"))
    selected = []
    for row in rows:
        title = str(row.get("title") or "").strip()
        body = str(row.get("text") or "").strip()
        source_url = str(row.get("canonical_url") or "").strip()
        if title and body and source_url and row.get("pub_date"):
            selected.append((row, title, body, source_url))

    imported = 0
    with connection() as conn:
        for row, title, body, source_url in selected:
            published = str(row["pub_date"])
            day = published[:10]
            item_id = stable_id(row)
            x, y = guide_coord(title + " " + body)
            conn.execute(
                """INSERT OR REPLACE INTO guide_items
                (id, title, body, published_at, day, source, source_url, x, y)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_id, title, body, published, day, SOURCE, source_url, x, y),
            )
            imported += 1
        conn.commit()

    collection = chroma_collection()
    if collection is not None:
        for row, title, body, source_url in selected:
            document = (title + "\n\n" + body).encode("utf-8")[:15000].decode("utf-8", errors="ignore")
            collection.upsert(
                ids=[stable_id(row)],
                documents=[document],
                metadatas=[{
                    "title": title,
                    "day": str(row["pub_date"])[:10],
                    "source": SOURCE,
                    "embedding_truncated": len(document) < len(title + "\n\n" + body),
                }],
            )
    print(json.dumps({
        "imported": imported,
        "records_seen": len(rows),
        "records_excluded": len(rows) - len(selected),
        "chroma": collection is not None,
        "collection": os.getenv("CHROMA_COLLECTION", "hgf_medium_archive_v1"),
        "source": str(args.archive),
        "mode": "chroma-cloud" if collection is not None else "deterministic-lexical-v0",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
