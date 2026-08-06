#!/usr/bin/env python3
"""Daily idempotent Community Archive refresh for Leo's public tweets."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import chroma_collection, connection, guide_coord

API_BASE = "https://fabxmporizzqflnftavs.supabase.co/rest/v1/enriched_tweets"
DOCS_URL = "https://www.community-archive.org/llms.txt"
USERNAME = "leo_guinan"
CURSOR_PATH = Path("/var/lib/hgf-api/community_archive_cursor.json")
RECEIPT_DIR = Path("/var/lib/hgf-api/community_archive_receipts")


def anon_key() -> str:
    text = urllib.request.urlopen(DOCS_URL, timeout=30).read().decode("utf-8")
    match = re.search(r"Public anon key:\s*(eyJ[^\s`]+)", text)
    if not match:
        raise RuntimeError("Community Archive anon key not found in canonical docs")
    return match.group(1)


def fetch_rows(since: str, key: str):
    rows = []
    offset = 0
    while True:
        params = {
            "select": "tweet_id,username,created_at,full_text,favorite_count,retweet_count",
            "username": f"ilike.{USERNAME}",
            "created_at": f"gte.{since}",
            "order": "created_at.asc,tweet_id.asc",
            "limit": "1000",
            "offset": str(offset),
        }
        req = urllib.request.Request(API_BASE + "?" + urllib.parse.urlencode(params), headers={"apikey": key, "Authorization": "Bearer " + key})
        page = json.load(urllib.request.urlopen(req, timeout=60))
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += len(page)


def normalize(row):
    tweet_id = str(row.get("tweet_id") or "").strip()
    text = str(row.get("full_text") or "").strip()
    created = str(row.get("created_at") or "").strip()
    if not tweet_id or not text or not created:
        return None
    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return {
        "id": "tw-" + tweet_id,
        "title": f"@leo_guinan · {dt.date().isoformat()} · tweet {tweet_id}",
        "body": text,
        "published_at": dt.isoformat(),
        "day": dt.date().isoformat(),
        "source": "Community Archive current update",
        "source_url": f"https://x.com/leo_guinan/status/{tweet_id}",
        "tweet_id": tweet_id,
    }


def cursor():
    if CURSOR_PATH.exists():
        return json.loads(CURSOR_PATH.read_text())
    with connection() as conn:
        row = conn.execute("select max(published_at) from guide_items where id like 'tw-%'").fetchone()
    latest = row[0] if row and row[0] else "2020-01-01T00:00:00+00:00"
    return {"created_at": latest, "tweet_id": "0"}


def main():
    started = datetime.now(timezone.utc)
    old = cursor()
    since = (datetime.fromisoformat(old["created_at"].replace("Z", "+00:00")) - timedelta(days=2)).isoformat()
    raw = fetch_rows(since, anon_key())
    normalized = []
    seen = set()
    for row in raw:
        item = normalize(row)
        if item and item["id"] not in seen:
            normalized.append(item)
            seen.add(item["id"])
    collection = chroma_collection()
    with connection() as conn:
        for item in normalized:
            x, y = guide_coord(item["title"] + " " + item["body"])
            conn.execute("""INSERT OR REPLACE INTO guide_items
                (id,title,body,published_at,day,source,source_url,x,y)
                VALUES (?,?,?,?,?,?,?,?,?)""", (item["id"],item["title"],item["body"],item["published_at"],item["day"],item["source"],item["source_url"],x,y))
        conn.commit()
    if collection is not None:
        for start in range(0, len(normalized), 100):
            batch = normalized[start:start + 100]
            collection.upsert(ids=[x["id"] for x in batch], documents=[(x["title"]+"\n\n"+x["body"]).encode("utf-8")[:15000].decode("utf-8",errors="ignore") for x in batch], metadatas=[{"title":x["title"],"day":x["day"],"source":x["source"]} for x in batch])
    if normalized:
        latest = max(normalized, key=lambda x: (x["published_at"], x["tweet_id"]))
        new_cursor = {"created_at": latest["published_at"], "tweet_id": latest["tweet_id"]}
    else:
        new_cursor = old
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(new_cursor, indent=2) + "\n")
    receipt = {"started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(), "since": since, "api_rows": len(raw), "normalized_rows": len(normalized), "cursor_before": old, "cursor_after": new_cursor, "retrieval": "chroma-cloud" if collection is not None else "sqlite-only"}
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.joinpath(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
