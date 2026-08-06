#!/usr/bin/env python3
"""Build bounded Guide caches while preserving the full SQLite corpus."""
from __future__ import annotations
import json, re, sqlite3, sys, time
from collections import Counter, defaultdict
from pathlib import Path

DB_PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/var/lib/hgf-api/hgf.sqlite3")
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'’-]{2,}", re.I)
STOPWORDS = set("the and for that with this from what when where who why how are was were you your about into than then have has had not but can could would should our their they them its it's a an of to in on at by as is be it or if do does did i me my we us a from one two three".split())

def terms(text: str):
    return [t.lower().replace("’", "'") for t in TOKEN_RE.findall(text.lower()) if t.lower() not in STOPWORDS]

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS guide_cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS guide_timeline (
        period TEXT PRIMARY KEY, item_count INTEGER NOT NULL, x REAL NOT NULL, y REAL NOT NULL,
        sources_json TEXT NOT NULL, top_terms_json TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS guide_space_cache (
        bin_id TEXT PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL, item_count INTEGER NOT NULL,
        hits INTEGER NOT NULL, representative_id TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS guide_items_published_idx ON guide_items(published_at, id);
      CREATE INDEX IF NOT EXISTS guide_items_day_idx ON guide_items(day);
    """)
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS guide_items_fts USING fts5(id UNINDEXED, title, body, source)")
    except sqlite3.OperationalError as exc:
        raise SystemExit(f"SQLite FTS5 unavailable: {exc}")

    conn.execute("DELETE FROM guide_items_fts")
    conn.execute("INSERT INTO guide_items_fts(id,title,body,source) SELECT id,title,body,source FROM guide_items")

    periods = defaultdict(lambda: {"count": 0, "x": 0.0, "y": 0.0, "sources": Counter(), "terms": Counter()})
    bins = defaultdict(lambda: {"count": 0, "hits": 0, "rep": None})
    rows = conn.execute("SELECT id,title,body,published_at,day,source,x,y FROM guide_items ORDER BY published_at,id")
    for row in rows:
        period = row[4][:7]
        p = periods[period]
        p["count"] += 1; p["x"] += row[6]; p["y"] += row[7]; p["sources"][row[5]] += 1
        p["terms"].update(terms((row[1] or "") + " " + (row[2] or "")))
        bx = min(11, max(0, int(row[6] * 12))); by = min(7, max(0, int(row[7] * 8)))
        b = bins[f"{bx}:{by}"]; b["count"] += 1
        if row[0]: b["rep"] = row[0] if b["rep"] is None else b["rep"]

    conn.execute("DELETE FROM guide_timeline")
    for period, p in sorted(periods.items()):
        conn.execute("INSERT INTO guide_timeline VALUES (?,?,?,?,?,?)", (period, p["count"], round(p["x"] / p["count"], 5), round(p["y"] / p["count"], 5), json.dumps(p["sources"], sort_keys=True), json.dumps(p["terms"].most_common(8))))
    conn.execute("DELETE FROM guide_space_cache")
    for bin_id, b in sorted(bins.items()):
        bx, by = map(int, bin_id.split(":")); conn.execute("INSERT INTO guide_space_cache VALUES (?,?,?,?,?,?)", (bin_id, (bx + .5) / 12, (by + .5) / 8, b["count"], b["hits"], b["rep"] or ""))
    meta = {"version": "high-level-cache-v1", "item_count": conn.execute("SELECT COUNT(*) FROM guide_items").fetchone()[0], "timeline_periods": len(periods), "space_nodes": len(bins), "built_at": int(time.time())}
    for key, value in meta.items(): conn.execute("INSERT INTO guide_cache_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit(); conn.close(); print(json.dumps(meta, sort_keys=True))

if __name__ == "__main__": main()
