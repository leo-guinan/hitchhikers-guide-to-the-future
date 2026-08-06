#!/usr/bin/env python3
"""Import Leo's public Twitter archive into the HGF guide corpus."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from app import chroma_collection, connection, guide_coord

DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def parse_archive(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8").split("=", 1)[1].strip())
    for row in payload:
        tweet = row.get("tweet", {})
        tweet_id = str(tweet.get("id_str") or tweet.get("id") or "").strip()
        text = str(tweet.get("full_text") or "").strip()
        created = str(tweet.get("created_at") or "").strip()
        if not tweet_id or not text or not created:
            continue
        dt = datetime.strptime(created, DATE_FORMAT)
        yield {
            "id": f"tw-{tweet_id}",
            "tweet_id": tweet_id,
            "title": f"@leo_guinan · {dt.date().isoformat()} · tweet {tweet_id}",
            "body": text,
            "published_at": dt.isoformat(),
            "day": dt.date().isoformat(),
            "source": "Leo Twitter archive",
            "source_url": f"https://x.com/leo_guinan/status/{tweet_id}",
        }


def write_rows(rows, collection):
    with connection() as conn:
        for row in rows:
            x, y = guide_coord(row["title"] + " " + row["body"])
            conn.execute(
                """INSERT OR REPLACE INTO guide_items
                (id, title, body, published_at, day, source, source_url, x, y)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["title"], row["body"], row["published_at"], row["day"], row["source"], row["source_url"], x, y),
            )
        conn.commit()
    if collection is not None:
        for start in range(0, len(rows), 100):
            batch = rows[start:start + 100]
            collection.upsert(
                ids=[r["id"] for r in batch],
                documents=[(r["title"] + "\n\n" + r["body"]).encode("utf-8")[:15000].decode("utf-8", errors="ignore") for r in batch],
                metadatas=[{"title": r["title"], "day": r["day"], "source": r["source"]} for r in batch],
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", type=Path)
    args = ap.parse_args()
    rows = list(parse_archive(args.archive))
    collection = chroma_collection()
    write_rows(rows, collection)
    print(json.dumps({"imported": len(rows), "chroma": collection is not None, "mode": os.getenv("HGF_RETRIEVAL_MODE", "auto")}))


if __name__ == "__main__":
    main()
