#!/usr/bin/env python3
"""Import published Build In Public University Ghost posts into the HGF guide index."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import chroma_collection, connection, guide_coord  # noqa: E402

SOURCE = "Build In Public University archive"
BASE_URL = "https://buildinpublicuniversity.com"


def stable_id(post: dict) -> str:
    raw = f"bipu:{post.get('id', '')}:{post.get('slug', '')}"
    return "bipu-" + hashlib.sha256(raw.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.export.read_text(encoding="utf-8"))
    posts = payload["db"][0]["data"]["posts"]
    rows = [
        post for post in posts
        if post.get("status") == "published"
        and post.get("type") == "post"
        and str(post.get("plaintext") or "").strip()
        and post.get("id")
    ]
    imported = 0
    with connection() as conn:
        for post in rows:
            title = str(post.get("title") or "(Untitled)").strip()
            body = str(post.get("plaintext") or "").strip()
            published = str(post.get("published_at") or post.get("created_at") or "1970-01-01")
            day = published[:10]
            slug = str(post.get("slug") or "").strip()
            source_url = f"{BASE_URL}/{slug}/" if slug else BASE_URL
            item_id = stable_id(post)
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
        for post in rows:
            title = str(post.get("title") or "(Untitled)").strip()
            body = str(post.get("plaintext") or "").strip()
            document = (title + "\n\n" + body).encode("utf-8")[:15000].decode("utf-8", errors="ignore")
            collection.upsert(
                ids=[stable_id(post)],
                documents=[document],
                metadatas=[{
                    "title": title,
                    "day": str(post.get("published_at") or post.get("created_at") or "")[:10],
                    "source": SOURCE,
                    "embedding_truncated": len(document) < len(title + "\n\n" + body),
                }],
            )
    print(json.dumps({
        "imported": imported,
        "published_posts_selected": len(rows),
        "excluded_non_posts_or_unpublished": len(posts) - len(rows),
        "chroma": collection is not None,
        "collection": os.getenv("CHROMA_COLLECTION", "hgf_medium_archive_v1"),
        "source": str(args.export),
        "mode": "chroma-cloud" if collection is not None else "deterministic-lexical-v0",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
