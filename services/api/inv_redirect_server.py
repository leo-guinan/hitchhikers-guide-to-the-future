#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAP = {}
with Path(os.environ.get("REDIRECT_MAP", "/app/redirect-map.csv")).open(newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        MAP[row["old_path"]] = row["guide_url"]

GUIDE_ARCHIVE = "https://guide.hitchhikersguidetothefuture.com/guide/"


class Handler(BaseHTTPRequestHandler):
    server_version = "INV-Retirement-Redirect/1.0"

    def do_GET(self):
        self.redirect()

    def do_HEAD(self):
        self.redirect()

    def redirect(self):
        path = urlsplit(self.path).path or "/"
        destination = MAP.get(path, GUIDE_ARCHIVE)
        self.send_response(308)
        self.send_header("Location", destination)
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()

    def log_message(self, format, *args):
        print(format % args, flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
