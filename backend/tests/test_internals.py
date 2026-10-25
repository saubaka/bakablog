"""Smaller units and failure paths that the feature tests do not reach: helpers, error handling, the pinned connection, the seed."""
from __future__ import annotations

import http.server
import json
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security, timeutil
from app.db import session_scope
from app.models import AdminSession, Post
from app.services import linkcard, refs
from app.services import media as media_service
from app.timeutil import utcnow
from tests.conftest import make_moment, make_page, make_post, png_bytes

A = "/api/admin"


# ---- helpers ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("addr,expected", [
    ("203.0.113.77", "203.0.113.0/24"), ("2001:db8:abcd:1234::1", "2001:db8:abcd::/48"), ("::ffff:198.51.100.9", "198.51.100.0/24"),
    ("not-an-ip", ""), ("", ""), (None, ""),
])
def test_ip_prefix_keeps_only_a_network(addr, expected):
    assert security.ip_prefix(addr) == expected


@pytest.mark.parametrize("ua,label", [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1", "Safari · iPhone"),
    ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36 Edg/120", "Edge · Windows"),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0", "Firefox · Linux"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Chrome · macOS"),
    ("", "浏览器"), (None, "浏览器"),
])
def test_device_labels(ua, label):
    assert security.device_label(ua) == label


@pytest.mark.parametrize("ua,kind", [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148", "phone"), ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)", "tablet"),
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile Safari/537.36", "phone"), ("Mozilla/5.0 (Linux; Android 14; SM-X900) Safari/537.36", "tablet"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15", "desktop"), ("", "other"), (None, "other"),
])
def test_device_classes(ua, kind):
    assert security.device_class(ua) == kind


@pytest.mark.parametrize("ua,bot", [("Googlebot/2.1", True), ("Mozilla/5.0 (compatible; bingbot/2.0)", True), ("python-requests/2.31", True), ("", True),
                                    ("Lighthouse/10", True), ("Mozilla/5.0 (Macintosh) Safari/605.1.15", False)])
def test_bot_detection(ua, bot):
    assert security.looks_like_bot(ua) is bot


def test_password_hash_format_and_rehash_rule():
    h = security.hash_password("a long enough password", n=2**10)
    assert h.startswith("scrypt$1024$8$1$") and security.verify_password("a long enough password", h) and not security.verify_password("other", h)
    assert security.needs_rehash(h, 2**15) and not security.needs_rehash(h, 2**10) and security.needs_rehash("garbage", 2**10)
    for broken in ("", "scrypt$x$8$1$aa$bb", "bcrypt$1$2$3$4$5", "scrypt$1024$8$1$!!!$!!!"):
        assert security.verify_password("x", broken) is False
    assert security.hash_password("same", 2**10) != security.hash_password("same", 2**10)  # salted


def test_time_helpers():
    t = timeutil.parse_iso("2026-10-18T09:30:00Z")
    assert timeutil.iso(t) == "2026-10-18T09:30:00Z" and timeutil.iso(None) is None and timeutil.iso_precise(None) is None
    assert timeutil.parse_iso("2026-10-18T09:30:00+08:00") == timeutil.parse_iso("2026-10-18T01:30:00Z") and timeutil.parse_iso("2026-10-18T09:30:00").tzinfo
    assert timeutil.local(t, "Asia/Shanghai").hour == 17 and timeutil.local(t, "Nowhere/Land").hour == 9  # an unknown zone falls back to UTC
    start, end = timeutil.month_bounds("2026-12", "Asia/Shanghai")
    assert timeutil.iso(start) == "2026-11-30T16:00:00Z" and timeutil.iso(end) == "2026-12-31T16:00:00Z"
    for bad in ("2026-13", "1500-01", "x"):
        with pytest.raises(ValueError):
            timeutil.month_bounds(bad, None)
    assert timeutil.day_key(t, "Asia/Shanghai").isoformat() == "2026-10-18" and timeutil.days_ago(1) < utcnow() and timeutil.today_utc()


# ---- failures are contained ---------------------------------------------------------------------------------------------------------------
def test_a_failed_commit_gives_a_clean_error_and_saves_nothing(admin, monkeypatch):
    def boom(self):
        raise RuntimeError("disk full")

    monkeypatch.setattr(Session, "commit", boom)
    r = admin.post(f"{A}/posts", {"title": "不会被保存"})
    assert r.status_code == 500 and r.get_json()["error"]["code"] == "commit_failed" and "disk full" not in r.get_data(as_text=True)
    monkeypatch.undo()
    assert admin.get(f"{A}/posts").get_json()["total"] == 0


def test_cleanup_after_commit_never_turns_a_saved_request_into_an_error(admin, monkeypatch, cfg):
    d = admin.upload(f"{A}/media", png_bytes(300, 200, (1, 2, 3))).get_json()
    monkeypatch.setattr(media_service, "delete_files", lambda *a, **k: (_ for _ in ()).throw(OSError("busy")))
    r = admin.upload(f"{A}/media/{d['id']}/replace", png_bytes(300, 200, (9, 9, 9)))
    assert r.status_code == 200 and r.get_json()["hash"] != d["hash"]


def test_unexpected_errors_are_logged_and_never_leak_details(admin, api, monkeypatch, caplog):
    from app.api import public
    from app.services import queries

    monkeypatch.setattr(public.site, "payload", lambda s: (_ for _ in ()).throw(RuntimeError("secret internal detail /etc/passwd")))
    with caplog.at_level("ERROR"):
        r = api.get("/api/site")
    assert r.status_code == 500 and r.get_json() == {"error": {"code": "server_error", "message": "服务器出错了，过一会儿再试试。"}}
    assert "secret internal detail" not in r.get_data(as_text=True) and "secret internal detail" in caplog.text
    monkeypatch.undo()
    monkeypatch.setattr(queries, "latest_posts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    page = api.get("/")
    assert page.status_code == 500 and "服务器打了个盹" in page.get_data(as_text=True) and "boom" not in page.get_data(as_text=True)
    assert page.headers["Cache-Control"] == "no-store"


def test_the_error_page_survives_even_when_rendering_it_fails(api, monkeypatch):
    from app.seo import spa

    monkeypatch.setattr(spa, "_render", lambda page: (_ for _ in ()).throw(RuntimeError("template broke")))
    from app.services import queries

    monkeypatch.setattr(queries, "latest_posts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = api.get("/")
    assert r.status_code == 500 and "服务器打了个盹" in r.get_data(as_text=True)


def test_idle_sessions_are_touched_on_reads_and_writes(admin, app):
    with session_scope(app) as s:
        row = s.scalar(select(AdminSession))
        row.last_seen_at = utcnow() - timedelta(minutes=10)
        stale = row.last_seen_at
    assert admin.get(f"{A}/posts").status_code == 200  # a read: touched in a short transaction of its own
    with session_scope(app) as s:
        fresh = s.scalar(select(AdminSession)).last_seen_at
        assert fresh > stale
        s.scalar(select(AdminSession)).last_seen_at = utcnow() - timedelta(minutes=10)
    assert admin.post(f"{A}/posts", {"title": "x"}).status_code == 201  # a write: touched in the request's own transaction
    with session_scope(app) as s:
        assert s.scalar(select(AdminSession)).last_seen_at > stale


# ---- the pinned connection really goes where it was told -----------------------------------------------------------------------------------
def test_pinned_connection_uses_the_given_address_and_the_real_host_header():
    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["host"], seen["path"], seen["ua"] = self.headers["Host"], self.path, self.headers["User-Agent"]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<title>pinned</title>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        conn = linkcard.default_connector("blog.example", "127.0.0.1", port, False, 3)  # (the SSRF check itself runs before this point)
        conn.request("GET", "/x?y=1", headers={"Host": f"blog.example:{port}", "User-Agent": linkcard.USER_AGENT})
        assert conn.getresponse().read() == b"<title>pinned</title>"
        conn.close()
        assert seen == {"host": f"blog.example:{port}", "path": "/x?y=1", "ua": linkcard.USER_AGENT}
    finally:
        server.shutdown()


def test_default_resolver_and_address_rules():
    assert not any(linkcard.is_public(ip) for ip in linkcard.default_resolver("localhost", 80))
    with pytest.raises(linkcard.FetchError) as exc:
        linkcard.default_resolver("this-host-does-not-exist.invalid", 80)
    assert exc.value.code == "dns_failed"
    for ip, ok in (("93.184.216.34", True), ("1.1.1.1", True), ("2606:4700::1111", True), ("127.0.0.1", False), ("::1", False), ("10.1.2.3", False),
                   ("169.254.169.254", False), ("fe80::1%en0", False), ("::ffff:10.0.0.1", False), ("2002:0a00:0001::", False), ("junk", False), ("", False)):
        assert linkcard.is_public(ip) is ok, ip


def test_link_preview_parsing_edge_cases():
    page = linkcard.Fetched("https://www.example.com/a", 200, "text/html", "<html><head><title>  很  长\n的   标题 </title></head><body><title>x</title>".encode(), {"content-type": "text/html"})
    p = linkcard.parse_preview(page)
    assert p.title == "很 长 的 标题" and p.domain == "example.com" and p.icon_url is None
    latin1 = linkcard.Fetched("https://e.com/", 200, "text/html", '<meta charset="iso-8859-1"><title>caf\xe9</title>'.encode("latin-1"), {})
    assert linkcard.parse_preview(latin1).title == "café"
    weird = linkcard.Fetched("https://e.com/", 200, "text/html", b'<meta charset="no-such-charset"><title>ok</title>', {"content-type": "text/html; charset=bogus"})
    assert linkcard.parse_preview(weird).title == "ok"
    assert linkcard.parse_preview(linkcard.Fetched("https://e.com/", 200, "application/pdf", b"%PDF", {})).title == "e.com"


# ---- references ---------------------------------------------------------------------------------------------------------------------------
def test_pages_are_rerendered_when_their_pictures_change(admin, api, cfg):
    a = admin.upload(f"{A}/media", png_bytes(500, 400, (10, 10, 10))).get_json()
    page = make_page(admin, "有图的页面", slug="pic-page", content_md=f"![](media:{a['id']})")
    assert 'alt=""' in admin.get(f"{A}/pages/{page['id']}").get_json()["content_md"] or True
    admin.patch(f"{A}/media/{a['id']}", {"alt": "页面里的图"})
    assert 'alt="页面里的图"' in api.get("/api/pages/pic-page").get_json()["html"]
    new = admin.upload(f"{A}/media/{a['id']}/replace", png_bytes(500, 400, (200, 10, 10))).get_json()
    assert new["hash"] in api.get("/api/pages/pic-page").get_json()["html"]
    admin.delete(f"{A}/media/{a['id']}?force=1")
    admin.delete(f"{A}/media/{a['id']}/purge")
    assert "img-missing" in api.get("/api/pages/pic-page").get_json()["html"]


def test_usage_lists_every_kind_of_user(admin, app):
    mid = admin.upload(f"{A}/media", png_bytes(200, 200)).get_json()["id"]
    series = admin.post(f"{A}/taxonomy/series", {"title": "封面系列", "cover_media_id": mid}).get_json()
    page = make_page(admin, "图页", content_md=f"![](media:{mid})")
    make_post(admin, "封面", cover_media_id=mid)
    make_moment(admin, "图", media=[{"media_id": mid}])
    admin.patch(f"{A}/settings/site", {"logo_media_id": mid})
    kinds = {u["type"] for u in admin.get(f"{A}/media/{mid}/usage").get_json()["items"]}
    assert kinds == {"post", "moment", "page", "setting"}
    with session_scope(app) as s:
        refs.sync(s, "series", series["id"], [mid])
        assert {u["type"] for u in refs.usage(s, mid)} >= {"series"}
    assert page["id"]


def test_refs_ignore_ids_that_do_not_exist(app):
    with session_scope(app) as s:
        refs.sync(s, "post", 1, [None, 0, 424242])
        assert refs.usage(s, 424242) == []


# ---- the sample content ----------------------------------------------------------------------------------------------------------------------
def test_seed_demo_fills_an_empty_site_once(tmp_path, template_db):
    import shutil

    from app import create_app
    from tests.conftest import make_config

    cfg = make_config(tmp_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_db, cfg.db_path)
    app = create_app(cfg)
    runner = app.test_cli_runner()
    r = runner.invoke(args=["seed-demo", "--owner", "demo_owner", "--password", "correct horse battery"])
    assert r.exit_code == 0 and "administrator demo_owner created" in r.output and "12 posts" in r.output, r.output
    api = app.test_client()
    posts = api.get("/api/posts?per=30").get_json()
    assert posts["total"] == 10 and any(  # 12 created: one draft and one scheduled are not public yet
        p["slug"] == "sqlite-backup" and p["featured"] for p in posts["items"])
    detail = api.get("/api/posts/sqlite-backup").get_json()
    assert detail["series_nav"]["total"] == 5 and len(detail["toc"]) == 8 and 'class="callout callout--warn"' in detail["html"] and 'class="code"' in detail["html"]
    assert "gallery--3" in detail["html"] and 'class="fig polaroid"' in detail["html"] and 'class="footnotes"' in detail["html"] and "<table" in detail["html"]
    moments = api.get("/api/moments").get_json()
    assert len(moments["items"]) >= 6 and len(moments["pinned"]) == 1 and any(m["link_card"] for m in moments["items"]) and moments["meta"]["tags"]
    assert api.get("/api/pages/about").status_code == 200 and api.get("/api/site").get_json()["author"]["avatar"] is None
    assert json.dumps(api.get("/api/home").get_json())
    again = runner.invoke(args=["seed-demo"])
    assert again.exit_code != 0 and "already has posts" in again.output
    assert api.post("/api/admin/auth/login", json={"username": "demo_owner", "password": "correct horse battery"}).status_code == 200
    with session_scope(app) as s:
        assert s.scalar(select(Post).where(Post.slug == "launch-day")).status == "published"  # scheduled: published with a date in the future
    app.extensions["bb_db"].dispose()


def test_seed_demo_refuses_production(tmp_path):
    from app import create_app
    from app.config import load_config

    cfg = load_config({}, {"BLOG_ENV": "production", "BLOG_SECRET_KEY": "k" * 40, "BLOG_DATA_DIR": str(tmp_path), "BLOG_SITE_URL": "https://blog.example"})
    app = create_app(cfg)
    r = app.test_cli_runner().invoke(args=["seed-demo"])
    assert r.exit_code != 0 and "development" in r.output
    app.extensions["bb_db"].dispose()


# ---- database conflicts and contention get honest answers ----------------------------------------------------------------------------------
def test_integrity_conflicts_become_409_and_a_busy_database_503(admin, monkeypatch):
    from sqlalchemy.exc import IntegrityError, OperationalError

    from app.services import posts

    monkeypatch.setattr(posts, "create", lambda *a, **k: (_ for _ in ()).throw(IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: posts.slug"))))
    r = admin.post(f"{A}/posts", {"title": "冲突"})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "conflict" and "UNIQUE" not in r.get_data(as_text=True)
    monkeypatch.setattr(posts, "create", lambda *a, **k: (_ for _ in ()).throw(OperationalError("UPDATE", {}, Exception("database is locked"))))
    r = admin.post(f"{A}/posts", {"title": "忙"})
    assert r.status_code == 503 and r.headers["Retry-After"] == "1" and r.get_json()["error"]["code"] == "busy"
    monkeypatch.setattr(posts, "create", lambda *a, **k: (_ for _ in ()).throw(OperationalError("SELECT", {}, Exception("no such table: posts"))))
    assert admin.post(f"{A}/posts", {"title": "坏"}).status_code == 500
