#!/usr/bin/env python3
"""Opaque HGF application sessions and private diary storage.

The service trusts only a server-to-server request from the Pages relay. The
browser never receives the auth preview claim or a reusable service token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv("HGF_API_HOST", "127.0.0.1")
PORT = int(os.getenv("HGF_API_PORT", "8846"))
DATA_DIR = Path(os.getenv("HGF_API_DATA_DIR", "/var/lib/hgf-api"))
DB_PATH = DATA_DIR / "hgf.sqlite3"
AUTH_SERVICE_URL = os.getenv("HGF_AUTH_SERVICE_URL", "https://auth.ideanexusventures.com").rstrip("/")
SERVICE_TOKEN = os.getenv("HGF_API_SERVICE_TOKEN", "").strip()
CHROMA_API_KEY = os.getenv("CHROMA_API_KEY", "").strip()
CHROMA_TENANT = os.getenv("CHROMA_TENANT", "").strip()
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE", "").strip()
CHROMA_HOST = os.getenv("CHROMA_HOST", "api.trychroma.com").strip()
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "hgf_medium_archive_v1").strip()
SESSION_TTL = 60 * 60 * 24 * 14
_CHROMA_COLLECTION = None


def connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            property_id TEXT NOT NULL,
            connection_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS diary_entries (
            id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS guide_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            published_at TEXT NOT NULL,
            day TEXT NOT NULL,
            source TEXT NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS guide_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_hash TEXT NOT NULL,
            query_hash TEXT NOT NULL,
            item_id TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.commit()
    return conn


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'’-]{2,}", re.I)
STOPWORDS = set("the and for that with this from what when where who why how are was were you your about into than then have has had not but can could would should our their they them its it's a an of to in on at by as is be it or if do does did i me my we us a from one two three".split())


def guide_terms(text: str) -> list[str]:
    return [token.lower().replace("’", "'") for token in TOKEN_RE.findall(text.lower()) if token.lower() not in STOPWORDS]


def guide_coord(text: str) -> tuple[float, float]:
    counts = Counter(guide_terms(text))
    x = sum(math.sin(int(hashlib.sha256(term.encode()).hexdigest()[:8], 16)) * count for term, count in counts.items())
    y = sum(math.cos(int(hashlib.sha256(term.encode()).hexdigest()[8:16], 16)) * count for term, count in counts.items())
    scale = max(1.0, math.sqrt(x * x + y * y))
    return round(0.5 + 0.44 * x / scale, 5), round(0.5 + 0.44 * y / scale, 5)


def guide_search(query: str, items: list[sqlite3.Row]) -> list[tuple[float, sqlite3.Row]]:
    query_terms = Counter(guide_terms(query))
    if not query_terms:
        return []
    document_frequency = Counter()
    tokenized = {}
    for item in items:
        terms = set(guide_terms(item["title"] + " " + item["body"]))
        tokenized[item["id"]] = terms
        document_frequency.update(terms)
    total = max(1, len(items))
    scored = []
    for item in items:
        terms = tokenized[item["id"]]
        score = 0.0
        for term, weight in query_terms.items():
            if term in terms:
                score += weight * math.log((total + 1) / (document_frequency[term] + 1))
                if term in guide_terms(item["title"]):
                    score += 1.5 * weight
        if score:
            scored.append((score, item))
    return sorted(scored, key=lambda pair: (-pair[0], pair[1]["published_at"]))[:5]


def chroma_collection():
    global _CHROMA_COLLECTION
    if _CHROMA_COLLECTION is not None:
        return _CHROMA_COLLECTION
    if not CHROMA_API_KEY or not CHROMA_TENANT or not CHROMA_DATABASE:
        return None
    try:
        import chromadb
        client = chromadb.CloudClient(api_key=CHROMA_API_KEY, tenant=CHROMA_TENANT, database=CHROMA_DATABASE, cloud_host=CHROMA_HOST)
        _CHROMA_COLLECTION = client.get_or_create_collection(CHROMA_COLLECTION, metadata={"source": "HGF Medium archive", "embedding_model": "chroma-default-all-MiniLM-L6-v2"})
        return _CHROMA_COLLECTION
    except Exception as exc:
        print(f"hgf-api chroma unavailable: {type(exc).__name__}: {exc}", flush=True)
        return None


def chroma_search(query: str, items: list[sqlite3.Row]) -> list[tuple[float, sqlite3.Row]]:
    collection = chroma_collection()
    if collection is None or not items:
        return []
    result = collection.query(query_texts=[query], n_results=min(5, len(items)), include=["distances"])
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    by_id = {item["id"]: item for item in items}
    return [(1.0 / (1.0 + float(distance)), by_id[item_id]) for item_id, distance in zip(ids, distances) if item_id in by_id]


def result_span(results: list[dict]) -> dict:
    days = sorted(result["day"] for result in results)
    if not days:
        return {"start": None, "end": None, "days": 0, "years": 0.0}
    duration = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days
    return {"start": days[0], "end": days[-1], "days": duration, "years": round(duration / 365.25, 2)}


def service_authorized(handler: BaseHTTPRequestHandler) -> bool:
    expected = f"Bearer {SERVICE_TOKEN}" if SERVICE_TOKEN else ""
    return bool(expected and hmac.compare_digest(handler.headers.get("Authorization", ""), expected))


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 120_000:
        raise ValueError("request body must be 1-120000 bytes")
    value = json.loads(handler.rfile.read(length))
    if not isinstance(value, dict):
        raise ValueError("request body must be an object")
    return value


def auth_redeem(handoff: str) -> dict:
    query = urllib.parse.urlencode({"handoff": handoff})
    request = urllib.request.Request(
        f"{AUTH_SERVICE_URL}/preview/redeem?{query}",
        data=b"",
        headers={"Content-Type": "application/json", "Origin": "https://hitchhikersguidetothefuture.com"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError("auth handoff rejected")
            result = json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError("auth service unavailable or handoff rejected") from exc
    required = ("workspace_id", "property_id", "connection_id")
    if not all(isinstance(result.get(key), str) and result[key] for key in required):
        raise RuntimeError("auth response did not contain a complete identity")
    return result


def session_row(token: str) -> sqlite3.Row | None:
    now = int(time.time())
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
            (digest(token), now),
        ).fetchone()
    return row


class Handler(BaseHTTPRequestHandler):
    server_version = "HGF-API/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"hgf-api {self.address_string()} {format % args}", flush=True)

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(self, 200, {"status": "ok", "service": "hgf-api", "version": "0.1.0", "auth_service": AUTH_SERVICE_URL})
            return
        if not service_authorized(self):
            json_response(self, 401, {"error": "service authorization required"})
            return
        if self.path == "/v1/guide/space":
            with connection() as conn:
                items = conn.execute("SELECT id, title, day, x, y FROM guide_items ORDER BY published_at, id").fetchall()
                heat = {row["item_id"]: row["hits"] for row in conn.execute("SELECT item_id, COUNT(*) AS hits FROM guide_events GROUP BY item_id")}
            json_response(self, 200, {"mode": "deterministic-lexical-v0", "items": [{**dict(item), "hits": heat.get(item["id"], 0)} for item in items]})
            return
        if self.path.startswith("/v1/guide/piece"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            item_id = query.get("id", [""])[0]
            with connection() as conn:
                item = conn.execute("SELECT id, title, body, day, published_at, source FROM guide_items WHERE id=?", (item_id,)).fetchone()
            if item is None:
                json_response(self, 404, {"error": "piece not found"})
            else:
                json_response(self, 200, {"piece": dict(item)})
            return
        if not service_authorized(self):
            json_response(self, 401, {"error": "service authorization required"})
            return
        token = self.headers.get("X-HGF-Session", "")
        row = session_row(token)
        if row is None:
            json_response(self, 401, {"error": "session missing or expired"})
            return
        if self.path == "/v1/session":
            json_response(self, 200, {"actor_id": row["actor_id"], "workspace_id": row["workspace_id"], "property_id": row["property_id"], "node_id": "hgf:guide"})
            return
        if self.path == "/v1/diary/entries":
            with connection() as conn:
                entries = conn.execute(
                    "SELECT id, content, created_at FROM diary_entries WHERE actor_id=? AND node_id=? ORDER BY created_at DESC LIMIT 100",
                    (row["actor_id"], "hgf:guide"),
                ).fetchall()
            json_response(self, 200, {"entries": [dict(entry) for entry in reversed(entries)]})
            return
        json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:
        if not service_authorized(self):
            json_response(self, 401, {"error": "service authorization required"})
            return
        if self.path == "/v1/auth/redeem":
            try:
                body = read_json(self)
                handoff = body.get("handoff")
                if not isinstance(handoff, str) or len(handoff) < 20:
                    raise ValueError("handoff is required")
                identity = auth_redeem(handoff)
                token = secrets.token_urlsafe(32)
                now = int(time.time())
                with connection() as conn:
                    conn.execute(
                        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                        (digest(token), "connection:" + identity["connection_id"], identity["workspace_id"], identity["property_id"], identity["connection_id"], now, now + SESSION_TTL),
                    )
                    conn.commit()
                json_response(self, 200, {"session_token": token, "expires_in": SESSION_TTL, "node_id": "hgf:guide"})
            except (ValueError, RuntimeError, sqlite3.Error) as exc:
                json_response(self, 400, {"error": str(exc)})
            return
        if self.path == "/v1/guide/search":
            try:
                body = read_json(self)
                query = body.get("query")
                visitor = body.get("visitor_id", "")
                if not isinstance(query, str) or not query.strip() or len(query) > 500:
                    raise ValueError("query must be 1-500 characters")
                with connection() as conn:
                    items = conn.execute("SELECT * FROM guide_items ORDER BY published_at, id").fetchall()
                    semantic_matches = chroma_search(query.strip(), items)
                    matches = semantic_matches or guide_search(query.strip(), items)
                    retrieval_mode = "chroma-cloud" if semantic_matches else "deterministic-lexical-v0"
                    if not matches:
                        json_response(self, 200, {"query": query.strip(), "matches": [], "path": []})
                        return
                    results = [{"id": item["id"], "title": item["title"], "day": item["day"], "source": item["source"], "score": round(score, 4), "x": item["x"], "y": item["y"]} for score, item in matches]
                    winner = results[0]
                    visitor_hash = digest(SERVICE_TOKEN + ":visitor:" + str(visitor))
                    query_hash = digest(SERVICE_TOKEN + ":query:" + query.strip().lower())
                    conn.execute("INSERT INTO guide_events(visitor_hash, query_hash, item_id, created_at) VALUES (?, ?, ?, ?)", (visitor_hash, query_hash, winner["id"], int(time.time())))
                    conn.commit()
                path = [{"x": 0.5, "y": 0.5}] + [{"x": result["x"], "y": result["y"]} for result in results[:3]]
                json_response(self, 200, {"query": query.strip(), "matches": results, "result_count": len(results), "date_span": result_span(results), "retrieval_mode": retrieval_mode, "path": path, "privacy": "aggregate-search-event"})
            except (ValueError, sqlite3.Error) as exc:
                json_response(self, 400, {"error": str(exc)})
            return
        token = self.headers.get("X-HGF-Session", "")
        row = session_row(token)
        if row is None:
            json_response(self, 401, {"error": "session missing or expired"})
            return
        if self.path == "/v1/diary/entries":
            try:
                body = read_json(self)
                content = body.get("content")
                if not isinstance(content, str) or not content.strip() or len(content) > 100_000:
                    raise ValueError("content must be 1-100000 characters")
                entry_id = "entry_" + secrets.token_urlsafe(12)
                created_at = int(time.time())
                with connection() as conn:
                    conn.execute("INSERT INTO diary_entries VALUES (?, ?, ?, ?, ?)", (entry_id, row["actor_id"], "hgf:guide", content.strip(), created_at))
                    conn.commit()
                json_response(self, 201, {"entry": {"id": entry_id, "content": content.strip(), "created_at": created_at}})
            except (ValueError, sqlite3.Error) as exc:
                json_response(self, 400, {"error": str(exc)})
            return
        json_response(self, 404, {"error": "not found"})


if __name__ == "__main__":
    connection().close()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
