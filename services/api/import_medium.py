#!/usr/bin/env python3
"""Import normalized Medium items into the private HGF guide index.

The source JSONL is intentionally not committed to this public repository.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import connection, guide_coord  # noqa: E402


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
    print(json.dumps({"imported": imported, "source": str(args.items), "mode": "deterministic-lexical-v0"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
