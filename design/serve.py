#!/usr/bin/env python3
"""Tiny static server for the prototype. Everything is sent with Cache-Control: no-store so the browser always shows
the files on disk (a stale cached stylesheet once made earlier work look like it had not changed)."""
import http.server
import os
import socketserver
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5200
HOST = os.environ.get("BB_HOST", "127.0.0.1")   # BB_HOST=0.0.0.0 lets a phone on the same Wi-Fi open the prototype
ROOT = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def guess_type(self, path):
        if str(path).endswith(".js"):
            return "text/javascript; charset=utf-8"
        if str(path).endswith(".css"):
            return "text/css; charset=utf-8"
        if str(path).endswith(".svg"):
            return "image/svg+xml"
        return super().guess_type(path)

    def log_message(self, fmt, *args):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    os.chdir(ROOT)
    print(f"design prototype on http://{HOST}:{PORT}/", flush=True)
    Server((HOST, PORT), Handler).serve_forever()
