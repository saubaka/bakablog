"""Smoke test against a RUNNING server (stdlib only).  The "is the thing I am looking at the thing I think it is" check.

    python scripts/live_check.py http://127.0.0.1:5311                       # read-only: public pages, headers, versions
    python scripts/live_check.py http://127.0.0.1:5311 --owner NAME --password PW --write    # also logs in, writes and cleans up

Exit status 0 = everything passed.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import io
import json
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor

PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {PASS if ok else FAIL} {what}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(what)


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect())
        self.csrf: str | None = None

    def request(self, method: str, path: str, body=None, headers=None, raw: bytes | None = None):
        data, h = raw, dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if self.csrf and method != "GET":
            h.setdefault("X-CSRF-Token", self.csrf)
        req = urllib.request.Request(self.base + urllib.parse.quote(path, safe="/?&=:%+,"), data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=20) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def get_json(self, path: str, **kw):
        status, headers, body = self.request("GET", path, **kw)
        return status, headers, (json.loads(body) if body and headers.get("Content-Type", "").startswith("application/json") else None)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def png(width=60, height=40, color=(120, 170, 220)) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes(color) * width
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")


def multipart(field: str, filename: str, payload: bytes, mime: str) -> tuple[bytes, str]:
    boundary = "----bblive" + str(int(time.time() * 1000))
    body = io.BytesIO()
    body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    body.write(payload)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def read_only(c: Client) -> dict:
    print("read-only checks")
    status, h, health = c.get_json("/api/health")
    check(status == 200 and health and health["ok"], "GET /api/health", str(status))
    print(f"    version {health['version']}  build {health['build']}  site_version {health['site_version']}")
    status, h, site = c.get_json("/api/site")
    check(status == 200 and bool(site["name"]), f"GET /api/site -> {site and site['name']}")
    check(site["version"] == health["version"], "site and health report the same version")
    etag = h.get("ETag")
    check(bool(etag) and c.request("GET", "/api/site", headers={"If-None-Match": etag})[0] == 304, "conditional GET answers 304")
    status, h, posts = c.get_json("/api/posts?per=3")
    check(status == 200 and "items" in posts, f"GET /api/posts ({posts['total']} posts)")
    status, h, body = c.request("GET", "/")
    html = body.decode()
    check(status == 200 and "<title>" in html and 'id="bb-data"' in html, "GET / is a server-rendered page with the inline data block")
    csp = h.get("Content-Security-Policy", "")
    check("script-src 'self'" in csp and "unsafe-inline" not in csp, "CSP is strict")
    check(h.get("X-Content-Type-Options") == "nosniff" and h.get("X-Frame-Options") == "DENY", "security headers present")
    if posts["items"]:
        first = posts["items"][0]
        s, _, page = c.request("GET", first["url"])
        check(s == 200 and first["title"] in page.decode(), f"GET {first['url']}")
        cover = first.get("cover")
        if cover:
            s, h2, img = c.request("GET", cover["src"])
            check(s == 200 and h2.get("Content-Type") == "image/webp" and "immutable" in h2.get("Cache-Control", ""), "pictures are served as immutable WebP")
            m = re.search(r"/media/([0-9a-f]+)/", cover["src"])
            check(bool(m), "picture address carries a content hash")
    check(c.request("GET", "/nowhere-at-all")[0] == 404, "unknown page answers 404")
    s, h, b = c.request("GET", "/api/nothing")
    check(s == 404 and json.loads(b)["error"]["code"] == "not_found", "unknown API path answers a JSON 404")
    check(c.request("GET", "/feed/posts.xml")[0] == 200 and c.request("GET", "/sitemap.xml")[0] == 200 and c.request("GET", "/robots.txt")[0] == 200, "feed, sitemap, robots")
    check(c.request("GET", "/api/admin/auth/me")[0] == 401, "admin API refuses anonymous visitors")
    check(c.request("POST", "/api/admin/posts", body={"title": "x"})[0] in (401, 403), "admin writes refuse anonymous visitors")
    check(c.request("POST", "/api/track", raw=b'{"p": "/"}', headers={"DNT": "1", "Content-Type": "text/plain"})[0] == 204, "visit beacon answers 204")
    return site


def writes(c: Client, owner: str, password: str) -> None:
    print("write checks (everything created here is removed again)")
    status, _, me = c.get_json("/api/admin/auth/status")
    check(status == 200 and me["setup_required"] is False, "setup is closed")
    s, h, body = c.request("POST", "/api/admin/auth/login", body={"username": owner, "password": password})
    check(s == 200, "login", f"{s} {body[:120]!r}")
    if s != 200:
        return
    data = json.loads(body)
    c.csrf = data["csrf_token"]
    cookie = next((ck for ck in c.jar if ck.name == "bb_session"), None)
    check(cookie is not None and cookie.path == "/api/admin", "session cookie is scoped to /api/admin")
    saved, c.csrf = c.csrf, None
    s, _, b = c.request("POST", "/api/admin/posts", body={"title": "no token"})
    check(s == 403 and json.loads(b)["error"]["code"] == "csrf", "a write without the CSRF token is refused")
    c.csrf = saved
    s, _, b = c.request("POST", "/api/admin/posts", body={"title": "实机检查", "content_md": "## 你好\n\n这是一篇检查用的文章。", "status": "published", "tags": ["live-check"]})
    post = json.loads(b)
    check(s == 201 and post["slug"], "create a post", f"{s} {b[:120]!r}")
    s, _, page = c.request("GET", f"/blog/{post['slug']}")
    check(s == 200 and "实机检查" in page.decode() and 'rel="canonical"' in page.decode(), "the new post is live, with SEO tags")
    payload, ctype = multipart("file", "check.png", png(), "image/png")
    s, _, b = c.request("POST", "/api/admin/media", raw=payload, headers={"Content-Type": ctype})
    media = json.loads(b)
    check(s in (200, 201) and media["variants"], "upload a picture", f"{s} {b[:120]!r}")
    bad_payload, bad_type = multipart("file", "evil.svg", b"<svg onload=alert(1)/>", "image/svg+xml")
    s, _, b = c.request("POST", "/api/admin/media", raw=bad_payload, headers={"Content-Type": bad_type})
    check(s in (415, 422), "a non-image upload is refused", str(s))
    run = str(int(time.time()))
    results = []

    def beacon(i: int) -> int:
        cl = Client(c.base)
        return cl.request("POST", "/api/track", raw=json.dumps({"p": f"/blog/{post['slug']}"}).encode(), headers={"Content-Type": "text/plain", "User-Agent": f"Mozilla/5.0 (live-check {i}) Safari/605.1.15"})[0]

    def write(i: int) -> int:
        return c.request("POST", "/api/admin/posts", body={"title": f"并发写入 {run} {i}", "status": "draft", "tags": ["live-check"]})[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(beacon, i) for i in range(40)] + [pool.submit(write, i) for i in range(20)]
        results = [f.result() for f in futures]
    check(all(r in (201, 204) for r in results), "40 beacons and 20 writes in parallel: none failed", str(sorted(set(results))))
    s, _, b = c.request("GET", f"/api/admin/posts?q=并发写入 {run}&per=50")
    drafts = json.loads(b)["items"]
    check(len(drafts) == 20, "all 20 concurrent writes were saved", str(len(drafts)))
    for p in drafts + [post]:
        c.request("DELETE", f"/api/admin/posts/{p['id']}")
        c.request("DELETE", f"/api/admin/posts/{p['id']}/purge")
    c.request("DELETE", f"/api/admin/media/{media['id']}")
    c.request("DELETE", f"/api/admin/media/{media['id']}/purge")
    c.request("POST", "/api/admin/taxonomy/tags/cleanup", body={})
    s, _, b = c.request("GET", "/api/admin/system/status")
    st = json.loads(b)
    check(s == 200 and st["schema_revision"] == st["schema_head"], f"database is at the current schema ({st['schema_revision']})")
    c.request("POST", "/api/admin/auth/logout", body={})
    check(c.request("GET", "/api/admin/auth/me")[0] == 401, "logout ends the session")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--owner")
    ap.add_argument("--password")
    ap.add_argument("--write", action="store_true", help="also log in and exercise the write paths (needs --owner and --password)")
    a = ap.parse_args()
    c = Client(a.base)
    read_only(c)
    if a.write:
        if not (a.owner and a.password):
            print("--write needs --owner and --password")
            return 2
        writes(c, a.owner, a.password)
    print("\nALL CHECKS PASSED" if not failures else f"\n{len(failures)} CHECK(S) FAILED: " + "; ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
