#!/usr/bin/env python3
"""Small, fail-closed payment rail for multiple Guide nodes.

The browser never receives the Stripe secret or the service token. Checkout is
service-to-service; Stripe webhooks are the only public mutation path.
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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv("PAYMENTS_HOST", "127.0.0.1")
PORT = int(os.getenv("PAYMENTS_PORT", "8845"))
DATA_DIR = Path(os.getenv("PAYMENTS_DATA_DIR", "/var/lib/ideanexus-payments"))
DB_PATH = DATA_DIR / "payments.sqlite3"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
SERVICE_TOKEN = os.getenv("PAYMENTS_SERVICE_TOKEN", "").strip()
ALLOWED_RETURN_HOSTS = {
    h.strip().lower()
    for h in os.getenv(
        "PAYMENTS_ALLOWED_RETURN_HOSTS",
        "hitchhikersguidetothefuture.com,www.hitchhikersguidetothefuture.com",
    ).split(",")
    if h.strip()
}


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS payment_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            subject_id TEXT,
            node_id TEXT,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            received_at INTEGER NOT NULL
        )"""
    )
    conn.commit()
    return conn


def json_response(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    raw = json.dumps(body, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 64_000:
        raise ValueError("request body must be 1-64000 bytes")
    body = handler.rfile.read(length)
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("request body must be an object")
    return value


def authorized(handler: BaseHTTPRequestHandler) -> bool:
    expected = f"Bearer {SERVICE_TOKEN}" if SERVICE_TOKEN else ""
    return bool(expected and hmac.compare_digest(handler.headers.get("Authorization", ""), expected))


def safe_return_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("return URL is required")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_RETURN_HOSTS:
        raise ValueError("return URL is not an approved HTTPS origin")
    return value


def stripe_checkout(req: dict) -> dict:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("Stripe is not configured")
    price_id = req.get("price_id")
    if not isinstance(price_id, str) or not price_id.startswith("price_"):
        raise ValueError("a Stripe price_id is required")
    node_id = req.get("node_id")
    subject_id = req.get("subject_id")
    if not isinstance(node_id, str) or not node_id or not isinstance(subject_id, str) or not subject_id:
        raise ValueError("node_id and subject_id are required")
    success_url = safe_return_url(req.get("success_url"))
    cancel_url = safe_return_url(req.get("cancel_url"))
    fields = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": subject_id,
        "metadata[node_id]": node_id,
        "metadata[subject_id]": subject_id,
    }
    email = req.get("customer_email")
    if isinstance(email, str) and email.strip():
        fields["customer_email"] = email.strip()
    request = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=urllib.parse.urlencode(fields).encode(),
        headers={
            "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode(errors="replace")
        raise RuntimeError(f"Stripe rejected checkout ({exc.code}): {detail}") from exc
    return {"id": result.get("id"), "url": result.get("url"), "status": result.get("status")}


def verify_signature(raw: bytes, signature: str | None) -> bool:
    if not STRIPE_WEBHOOK_SECRET or not signature:
        return False
    timestamp = None
    signatures: list[str] = []
    for item in signature.split(","):
        key, _, value = item.partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp or abs(time.time() - int(timestamp)) > 300:
        return False
    signed = f"{timestamp}.".encode() + raw
    expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, value) for value in signatures)


class Handler(BaseHTTPRequestHandler):
    server_version = "IdeaNexusPayments/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"payments {self.address_string()} {format % args}", flush=True)

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(self, 200, {
                "status": "ok",
                "service": "ideanexus-payments",
                "version": "0.1.0",
                "stripe_configured": bool(STRIPE_SECRET_KEY),
                "webhook_configured": bool(STRIPE_WEBHOOK_SECRET),
                "checkout_requires_service_token": True,
            })
            return
        if self.path.startswith("/v1/entitlements/"):
            if not authorized(self):
                json_response(self, 401, {"error": "service authorization required"})
                return
            json_response(self, 200, {"subject_id": self.path.rsplit("/", 1)[-1], "entitlements": []})
            return
        json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/v1/checkout/sessions":
            if not authorized(self):
                json_response(self, 401, {"error": "service authorization required"})
                return
            try:
                checkout = stripe_checkout(read_json(self))
                json_response(self, 201, {"checkout": checkout})
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except RuntimeError as exc:
                json_response(self, 503, {"error": str(exc)})
            return
        if self.path == "/v1/webhooks/stripe":
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if not verify_signature(raw, self.headers.get("Stripe-Signature")):
                json_response(self, 400, {"error": "invalid webhook signature"})
                return
            try:
                event = json.loads(raw)
                event_id = event["id"]
                event_type = event["type"]
                obj = event.get("data", {}).get("object", {})
                metadata = obj.get("metadata", {}) if isinstance(obj, dict) else {}
                with db() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO payment_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (event_id, event_type, metadata.get("subject_id"), metadata.get("node_id"), "received", raw.decode(), int(time.time())),
                    )
                    conn.commit()
                json_response(self, 200, {"received": True, "event_id": event_id})
            except (ValueError, KeyError, sqlite3.Error):
                json_response(self, 400, {"error": "invalid webhook payload"})
            return
        json_response(self, 404, {"error": "not found"})


if __name__ == "__main__":
    db().close()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
