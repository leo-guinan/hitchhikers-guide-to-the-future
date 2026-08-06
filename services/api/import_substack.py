#!/usr/bin/env python3
"""Import full-text public Substack archives into the HGF guide corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import chroma_collection, connection, guide_coord  # noqa: E402

SOURCE_BY_HOST = {
    "engineeringgenerosity.substack.com": "Engineering Generosity Substack",
    "hitchhikertothefuture.substack.com": "Hitchhiker to the Future Substack",
}


def stable_id(row: dict) -> str:
    source_url = str(row.get("canonical_url") or "").strip()
    raw = f"substack:{source_url}"
    return "sub-" + hashlib.sha256(raw.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    rows = []
    for archive in args.archives:
        rows.extend(json.loads(archive.read_text(encoding="utf-8")))

    selected = []
    for row in rows:
        title = str(row.get("title") or "").strip()
        body = str(row.get("text") or "").strip()
        source_url = str(row.get("canonical_url") or "").strip()
        published = str(row.get("pub_date") or "").strip()
        host = source_url.split("/", 3)[2] if source_url.startswith("https://") else ""
        source = SOURCE_BY_HOST.get(host)
        if title and body and source_url and published and source:
            selected.append((row, title, body, source_url, published, source))

    with connection() as conn:
        for row, title, body, source_url, published, source in selected:
            item_id = stable_id(row)
            day = published[:10]
            x, y = guide_coord(title + " " + body)
            conn.execute(
                """INSERT OR REPLACE INTO guide_items
                (id, title, body, published_at, day, source, source_url, x, y)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_id, title, body, published, day, source, source_url, x, y),
            )
        conn.commit()

    collection = chroma_collection()
    if collection is not None:
        for row, title, body, source_url, published, source in selected:
            document = (title + "\n\n" + body).encode("utf-8")[:15000].decode("utf-8", errors="ignore")
            collection.upsert(
                ids=[stable_id(row)],
                documents=[document],
                metadatas=[{
                    "title": title,
                    "day": published[:10],
                    "source": source,
                    "embedding_truncated": len(document) < len(title + "\n\n" + body),
                }],
            )
    print(json.dumps({
        "imported": len(selected),
        "records_seen": len(rows),
        "records_excluded": len(rows) - len(selected),
        "chroma": collection is not None,
        "collection": os.getenv("CHROMA_COLLECTION", "hgf_medium_archive_v1"),
        "mode": "chroma-cloud" if collection is not None else "deterministic-lexical-v0",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
