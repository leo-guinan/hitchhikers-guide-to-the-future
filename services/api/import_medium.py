#!/usr/bin/env python3
"""Import normalized Medium items into the private HGF guide index.

The source JSONL is intentionally not committed to this public repository.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import chroma_collection, connection, guide_coord  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("items", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.items.read_text(encoding="utf-8").splitlines() if line.strip()]
    imported = 0
    with connection() as conn:
        for row in rows:
            title = str(row.get("title", "")).strip()
            body = str(row.get("text", "")).strip()
            if not title or not body or not row.get("id"):
                continue
            published = str(row.get("publishedAt") or row.get("day") or "1970-01-01")
            day = str(row.get("day") or published[:10])
            x, y = guide_coord(title + " " + body)
            conn.execute(
                """INSERT OR REPLACE INTO guide_items
                (id, title, body, published_at, day, source, x, y)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(row["id"]), title, body, published, day, "Medium archive", x, y),
            )
            imported += 1
        conn.commit()
    collection = chroma_collection()
    if collection is not None:
        for row in rows:
            if not row.get("id") or not row.get("text"):
                continue
            document = str(row["title"]) + "\n\n" + str(row["text"])
            document = document.encode("utf-8")[:15000].decode("utf-8", errors="ignore")
            collection.upsert(
                ids=[str(row["id"])],
                documents=[document],
                metadatas=[{"title": str(row.get("title", "")), "day": str(row.get("day", "")), "source": "Medium archive", "embedding_truncated": len(document) < len(str(row["title"]) + "\n\n" + str(row["text"]))}],
            )
    print(json.dumps({"imported": imported, "chroma": collection is not None, "collection": os.getenv("CHROMA_COLLECTION", "hgf_medium_archive_v1"), "source": str(args.items), "mode": "chroma-cloud" if collection is not None else "deterministic-lexical-v0"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
