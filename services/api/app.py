#!/usr/bin/env python3
"""Opaque HGF application sessions and private diary storage.

The service trusts only a server-to-server request from the Pages relay. The
browser never receives the auth preview claim or a reusable service token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv("HGF_API_HOST", "127.0.0.1")
PORT = int(os.getenv("HGF_API_PORT", "8846"))
DATA_DIR = Path(os.getenv("HGF_API_DATA_DIR", "/var/lib/hgf-api"))
DB_PATH = DATA_DIR / "hgf.sqlite3"
AUTH_SERVICE_URL = os.getenv("HGF_AUTH_SERVICE_URL", "https://auth.ideanexusventures.com").rstrip("/")
SERVICE_TOKEN = os.getenv("HGF_API_SERVICE_TOKEN", "").strip()
SESSION_TTL = 60 * 60 * 24 * 14


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
    conn.commit()
    return conn


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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
