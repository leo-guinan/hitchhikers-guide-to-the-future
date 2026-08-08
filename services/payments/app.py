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
MINCOIN_CAP_CENTS = int(os.getenv("MINCOIN_CAP_CENTS", "5000000"))
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
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mincoin_reservations (
            contribution_id TEXT PRIMARY KEY,
            stripe_session_id TEXT,
            amount_cents INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mincoin_overflow (
            overflow_id TEXT PRIMARY KEY,
            chain TEXT NOT NULL,
            tx_hash TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount_native TEXT NOT NULL,
            confirmations INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            usd_value_cents INTEGER,
            valuation_source TEXT,
            evidence_url TEXT,
            reviewed_by TEXT,
            created_at INTEGER NOT NULL,
            UNIQUE(chain, tx_hash, asset)
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


def _paid_mincoin_cents(conn: sqlite3.Connection) -> int:
    raised_cents = 0
    rows = conn.execute(
        "SELECT payload_json FROM payment_events "
        "WHERE event_type = 'checkout.session.completed'"
    ).fetchall()
    for row in rows:
        try:
            event = json.loads(row["payload_json"])
            obj = event.get("data", {}).get("object", {})
            metadata = obj.get("metadata", {})
            if (
                metadata.get("campaign_id") == "mincoin"
                and obj.get("payment_status") == "paid"
                and isinstance(obj.get("amount_total"), int)
            ):
                raised_cents += obj["amount_total"]
        except (TypeError, ValueError, AttributeError):
            continue
    return raised_cents


def _overflow_summary(conn: sqlite3.Connection) -> dict:
    verified_cents = conn.execute(
        "SELECT COALESCE(SUM(usd_value_cents), 0) FROM mincoin_overflow "
        "WHERE status = 'verified' AND usd_value_cents IS NOT NULL"
    ).fetchone()[0]
    verified_count = conn.execute(
        "SELECT COUNT(*) FROM mincoin_overflow WHERE status = 'verified'"
    ).fetchone()[0]
    unpriced_count = conn.execute(
        "SELECT COUNT(*) FROM mincoin_overflow "
        "WHERE status IN ('observed', 'verified') AND usd_value_cents IS NULL"
    ).fetchone()[0]
    return {
        "overflow_reserve_cents": verified_cents,
        "overflow_verified_count": verified_count,
        "overflow_unpriced_count": unpriced_count,
    }


def mincoin_summary() -> dict:
    now = int(time.time())
    with db() as conn:
        conn.execute(
            "UPDATE mincoin_reservations SET status = 'expired' "
            "WHERE status IN ('pending', 'open') AND created_at < ?",
            (now - 24 * 60 * 60,),
        )
        raised_cents = _paid_mincoin_cents(conn)
        reserved_cents = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM mincoin_reservations "
            "WHERE status IN ('pending', 'open')"
        ).fetchone()[0]
        overflow = _overflow_summary(conn)
    return {
        "campaign_id": "mincoin",
        "cap_cents": MINCOIN_CAP_CENTS,
        "raised_cents": raised_cents,
        "reserved_cents": reserved_cents,
        "available_cents": max(0, MINCOIN_CAP_CENTS - raised_cents - reserved_cents),
        **overflow,
        "status": (
            "closed" if raised_cents >= MINCOIN_CAP_CENTS
            else "full_pending" if raised_cents + reserved_cents >= MINCOIN_CAP_CENTS
            else "open"
        ),
    }


def record_mincoin_overflow(req: dict) -> dict:
    allowed_chains = {"base", "ethereum", "solana", "polygon", "quai"}
    chain = req.get("chain")
    tx_hash = req.get("tx_hash")
    asset = req.get("asset")
    amount_native = req.get("amount_native")
    observed_at = req.get("observed_at")
    confirmations = req.get("confirmations", 0)
    status = req.get("status", "observed")
    if chain not in allowed_chains:
        raise ValueError("chain is not supported")
    if not isinstance(tx_hash, str) or not tx_hash.strip() or len(tx_hash) > 256:
        raise ValueError("tx_hash is required")
    if not isinstance(asset, str) or not asset.strip() or len(asset) > 32:
        raise ValueError("asset is required")
    if (
        not isinstance(amount_native, str)
        or not amount_native.strip()
        or not amount_native.replace(".", "", 1).isdigit()
    ):
        raise ValueError("amount_native must be a non-negative decimal string")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError("observed_at is required")
    if not isinstance(confirmations, int) or confirmations < 0:
        raise ValueError("confirmations must be a non-negative integer")
    if status not in {"observed", "verified"}:
        raise ValueError("status must be observed or verified")
    usd_value_cents = req.get("usd_value_cents")
    valuation_source = req.get("valuation_source")
    evidence_url = req.get("evidence_url")
    reviewed_by = req.get("reviewed_by")
    if status == "verified":
        if not isinstance(usd_value_cents, int) or usd_value_cents < 0:
            raise ValueError("verified overflow requires usd_value_cents")
        if not isinstance(valuation_source, str) or not valuation_source.strip():
            raise ValueError("verified overflow requires valuation_source")
        if not isinstance(evidence_url, str) or not evidence_url.strip():
            raise ValueError("verified overflow requires evidence_url")
        if not isinstance(reviewed_by, str) or not reviewed_by.strip():
            raise ValueError("verified overflow requires reviewed_by")
    overflow_id = hashlib.sha256(f"{chain}:{tx_hash}:{asset}".encode()).hexdigest()
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM mincoin_overflow WHERE overflow_id = ?", (overflow_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO mincoin_overflow VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    overflow_id, chain, tx_hash, asset, amount_native, confirmations,
                    observed_at, status, usd_value_cents, valuation_source, evidence_url,
                    reviewed_by, int(time.time()),
                ),
            )
        elif status == "verified" and existing["status"] != "verified":
            conn.execute(
                "UPDATE mincoin_overflow SET status = 'verified', usd_value_cents = ?, "
                "valuation_source = ?, evidence_url = ?, reviewed_by = ?, confirmations = ? "
                "WHERE overflow_id = ?",
                (usd_value_cents, valuation_source, evidence_url, reviewed_by, confirmations, overflow_id),
            )
        row = conn.execute(
            "SELECT * FROM mincoin_overflow WHERE overflow_id = ?", (overflow_id,)
        ).fetchone()
    return {
        "overflow_id": overflow_id,
        "chain": row["chain"],
        "tx_hash": row["tx_hash"],
        "asset": row["asset"],
        "amount_native": row["amount_native"],
        "confirmations": row["confirmations"],
        "observed_at": row["observed_at"],
        "status": row["status"],
        "usd_value_cents": row["usd_value_cents"],
    }


def reserve_mincoin_amount(contribution_id: str, amount_cents: int) -> None:
    now = int(time.time())
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE mincoin_reservations SET status = 'expired' "
            "WHERE status IN ('pending', 'open') AND created_at < ?",
            (now - 24 * 60 * 60,),
        )
        raised_cents = _paid_mincoin_cents(conn)
        reserved_cents = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM mincoin_reservations "
            "WHERE status IN ('pending', 'open')"
        ).fetchone()[0]
        if raised_cents + reserved_cents + amount_cents > MINCOIN_CAP_CENTS:
            raise ValueError("amount exceeds remaining Mincoin capacity")
        conn.execute(
            "INSERT INTO mincoin_reservations "
            "(contribution_id, stripe_session_id, amount_cents, status, created_at) "
            "VALUES (?, NULL, ?, 'pending', ?)",
            (contribution_id, amount_cents, now),
        )


def update_mincoin_reservation(contribution_id: str, status: str, session_id: str | None = None) -> None:
    if status not in {"open", "completed", "expired", "failed"}:
        raise ValueError("invalid Mincoin reservation status")
    with db() as conn:
        conn.execute(
            "UPDATE mincoin_reservations SET status = ?, stripe_session_id = COALESCE(?, stripe_session_id) "
            "WHERE contribution_id = ?",
            (status, session_id, contribution_id),
        )


def mincoin_contribution_checkout(req: dict) -> dict:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("Stripe is not configured")
    amount_cents = req.get("amount_cents")
    if not isinstance(amount_cents, int) or amount_cents < 1:
        raise ValueError("amount_cents must be a positive integer")
    success_url = safe_return_url(req.get("success_url"))
    cancel_url = safe_return_url(req.get("cancel_url"))
    contribution_id = req.get("contribution_id")
    if not isinstance(contribution_id, str) or not contribution_id.strip():
        raise ValueError("contribution_id is required")
    reserve_mincoin_amount(contribution_id, amount_cents)
    fields = {
        "mode": "payment",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": "Mincoin contribution",
        "line_items[0][price_data][product_data][description]": "A bounded contribution to the Mincoin experiment.",
        "line_items[0][quantity]": "1",
        "submit_type": "donate",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": contribution_id,
        "metadata[campaign_id]": "mincoin",
        "metadata[contribution_id]": contribution_id,
    }
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
        update_mincoin_reservation(contribution_id, "failed")
        detail = exc.read(512).decode(errors="replace")
        raise RuntimeError(f"Stripe rejected contribution checkout ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError):
        update_mincoin_reservation(contribution_id, "failed")
        raise RuntimeError("Stripe contribution checkout could not be reached")
    update_mincoin_reservation(contribution_id, "open", result.get("id"))
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
        if self.path == "/v1/campaigns/mincoin":
            if not authorized(self):
                json_response(self, 401, {"error": "service authorization required"})
                return
            json_response(self, 200, mincoin_summary())
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
        if self.path == "/v1/campaigns/mincoin/checkout":
            if not authorized(self):
                json_response(self, 401, {"error": "service authorization required"})
                return
            try:
                checkout = mincoin_contribution_checkout(read_json(self))
                json_response(self, 201, {"checkout": checkout})
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except RuntimeError as exc:
                json_response(self, 503, {"error": str(exc)})
            return
        if self.path == "/v1/campaigns/mincoin/overflow":
            if not authorized(self):
                json_response(self, 401, {"error": "service authorization required"})
                return
            try:
                overflow = record_mincoin_overflow(read_json(self))
                json_response(self, 201, {"overflow": overflow, "accounting": "reserve_not_cap"})
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except sqlite3.Error:
                json_response(self, 409, {"error": "overflow receipt conflicts with an existing record"})
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
                if metadata.get("campaign_id") == "mincoin":
                    contribution_id = metadata.get("contribution_id")
                    if isinstance(contribution_id, str) and event_type == "checkout.session.completed" and obj.get("payment_status") == "paid":
                        update_mincoin_reservation(contribution_id, "completed", obj.get("id"))
                    elif isinstance(contribution_id, str) and event_type in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
                        update_mincoin_reservation(contribution_id, "expired", obj.get("id"))
                json_response(self, 200, {"received": True, "event_id": event_id})
            except (ValueError, KeyError, sqlite3.Error):
                json_response(self, 400, {"error": "invalid webhook payload"})
            return
        json_response(self, 404, {"error": "not found"})


if __name__ == "__main__":
    db().close()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
