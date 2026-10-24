"""Whole-application security checks: every route is accounted for, nothing admin is reachable without a session + CSRF token,
nothing public leaks hidden content, and the response headers are the same everywhere."""
from __future__ import annotations

import re

import pytest

from tests.conftest import OWNER, Api, make_moment, make_page, make_post

PUBLIC_AUTH = {"/api/admin/auth/status", "/api/admin/auth/setup", "/api/admin/auth/login"}
UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


def concrete(rule) -> str:
    """/api/admin/posts/<int:post_id>/revisions/<int:revision_id> -> /api/admin/posts/1/revisions/1"""
    url = re.sub(r"<int:[^>]+>", "1", rule.rule)
    return re.sub(r"<[^>]+>", "x", url)


def admin_rules(app):
    return [r for r in app.url_map.iter_rules() if r.rule.startswith("/api/admin") and r.rule not in PUBLIC_AUTH]


# ---- the complete list of public endpoints: adding one means adding it here, on purpose ----------------------------------------------------
PUBLIC_ROUTES = {
    ("GET", "/api/health"), ("GET", "/api/site"), ("GET", "/api/home"), ("GET", "/api/posts"), ("GET", "/api/posts/<slug>"), ("GET", "/api/archive"),
    ("GET", "/api/taxonomy"), ("GET", "/api/moments"), ("GET", "/api/moments/<int:moment_id>"), ("GET", "/api/pages/<slug>"), ("GET", "/api/search"),
    ("POST", "/api/track"), ("GET", "/media/<media_hash>/<int:size>.webp"), ("GET", "/feed/posts.xml"), ("GET", "/feed/moments.xml"),
    ("GET", "/sitemap.xml"), ("GET", "/robots.txt"), ("GET", "/assets/<path:filename>"), ("GET", "/<name>"), ("GET", "/<path:path>"), ("GET", "/"),
}


def test_the_public_surface_is_exactly_the_documented_one(app):
    seen = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/admin") and rule.rule not in PUBLIC_AUTH:
            continue
        if rule.rule == "/static/<path:filename>":
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            seen.add((method, rule.rule))
    pre_auth = {("GET", "/api/admin/auth/status"), ("POST", "/api/admin/auth/setup"), ("POST", "/api/admin/auth/login")}
    assert seen - pre_auth == PUBLIC_ROUTES, (seen - pre_auth) ^ PUBLIC_ROUTES


def test_visitors_have_exactly_one_way_to_write(app):
    writes = {(m, r) for m, r in PUBLIC_ROUTES if m != "GET"}
    assert writes == {("POST", "/api/track")}


# ---- every admin endpoint is protected -----------------------------------------------------------------------------------------------------
def test_every_admin_endpoint_demands_a_session(app, api):
    problems = []
    for rule in admin_rules(app):
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            r = api.client.open(concrete(rule), method=method, json={} if method in UNSAFE else None)
            if r.status_code != 401:
                problems.append((method, rule.rule, r.status_code))
    assert problems == []


def test_every_admin_write_demands_the_csrf_token_and_the_right_origin(app, admin):
    csrf = admin.csrf
    missing, wrong_origin = [], []
    for rule in admin_rules(app):
        for method in rule.methods & set(UNSAFE):
            url = concrete(rule)
            admin.csrf = None
            r = admin._call(method.lower(), url, json={})
            if r.status_code != 403 or r.get_json()["error"]["code"] != "csrf":
                missing.append((method, rule.rule, r.status_code))
            admin.csrf = csrf
            r = admin._call(method.lower(), url, json={}, headers={"Origin": "https://evil.example"})
            if r.status_code != 403 or r.get_json()["error"]["code"] != "cross_site":
                wrong_origin.append((method, rule.rule, r.status_code))
    admin.csrf = csrf
    assert missing == [] and wrong_origin == []


def test_every_admin_read_works_with_the_session_alone(app, admin):
    """The flip side: reads need no CSRF token (they cannot change anything)."""
    for rule in admin_rules(app):
        if "GET" not in rule.methods or "<" in rule.rule.replace("<int:", "<"):
            continue
        r = admin.get(concrete(rule))
        assert r.status_code in (200, 404, 422), (rule.rule, r.status_code)


def test_admin_answers_are_never_cached(admin):
    for url in ("/api/admin/auth/me", "/api/admin/posts", "/api/admin/settings", "/api/admin/dashboard", "/api/admin/trash", "/api/admin/system/status"):
        r = admin.get(url)
        assert r.headers["Cache-Control"] == "no-store" and r.headers["Vary"] == "Cookie", url
    assert admin.post("/api/admin/auth/logout", {}).headers["Cache-Control"] == "no-store"


def test_admin_writes_accept_json_only(admin):
    r = admin.client.post("/api/admin/posts", data={"title": "x"}, headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "bad_json"
    r = admin.client.post("/api/admin/posts", data='{"title": "x"}', content_type="text/plain", headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 400  # text/plain is what a cross-site <form> can send; it is not accepted
    r = admin.client.post("/api/admin/posts", data="{broken", content_type="application/json", headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 400


def test_mass_assignment_is_not_possible(admin):
    p = make_post(admin, "字段")
    for field, value in (("id", 99), ("deleted_at", "2020-01-01T00:00:00Z"), ("view_count", 9999), ("content_html", "<script>x</script>"), ("created_at", "2000-01-01T00:00:00Z"),
                         ("toc", []), ("reading_minutes", 99), ("is_admin", True)):
        r = admin.patch(f"/api/admin/posts/{p['id']}", {field: value})
        assert r.status_code == 422 and r.get_json()["error"]["fields"][field] == "不认识这个字段", field
    for field in ("id", "view_count", "content_html", "user_id"):
        assert admin.post("/api/admin/moments", {"text": "x", field: 1}).status_code == 422


# ---- nothing hidden leaks through the public API ----------------------------------------------------------------------------------------------------
def test_an_admin_cookie_sent_to_public_urls_changes_nothing(app, admin, api):
    draft = make_post(admin, "秘密草稿", status="draft")
    private = make_post(admin, "秘密私密", status="private")
    pm = make_moment(admin, "秘密动态", visibility="private")
    cookie = admin.client.get_cookie("bb_session", path="/api/admin")
    assert cookie is not None
    header = {"Cookie": f"bb_session={cookie.value}"}
    for url in (f"/api/posts/{draft['slug']}", f"/api/posts/{private['slug']}", f"/blog/{draft['slug']}", f"/api/moments/{pm['id']}", f"/moments/{pm['id']}"):
        assert api.get(url, headers=header).status_code == 404, url
    body = api.get("/api/posts", headers=header).get_data(as_text=True)
    assert "秘密" not in body and "秘密" not in api.get("/api/moments", headers=header).get_data(as_text=True)
    for url in ("/", "/blog", "/archive", "/feed/posts.xml", "/sitemap.xml"):
        assert "秘密" not in api.get(url, headers=header).get_data(as_text=True), url
    found = api.get("/api/search?q=秘密", headers=header).get_json()
    assert found["total"] == 0 and found["groups"] == {"posts": [], "moments": [], "pages": []}


def test_nothing_public_mentions_hidden_content_anywhere(admin, api):
    """A sweep over every public address: drafts, private items, trashed items and future items appear nowhere."""
    make_post(admin, "公开一篇", tags=["公开标签"])
    secrets = [make_post(admin, "机密草稿", status="draft", tags=["机密标签"]), make_post(admin, "机密私密", status="private"),
               make_post(admin, "机密定时", published_at="2099-01-01T00:00:00Z")]
    trashed = make_post(admin, "机密已删")
    admin.delete(f"/api/admin/posts/{trashed['id']}")
    make_moment(admin, "机密动态", visibility="private")
    make_page(admin, "机密页面", slug="secret-page", status="draft")
    urls = ["/", "/blog", "/archive", "/moments", "/search?q=机密", "/api/site", "/api/home", "/api/posts", "/api/posts?q=机密", "/api/archive", "/api/taxonomy",
            "/api/moments", "/api/search?q=机密", "/api/search?q=机密标签", "/feed/posts.xml", "/feed/moments.xml", "/sitemap.xml", "/robots.txt"]
    for url in urls:
        text = api.get(url).get_data(as_text=True)
        text = text.replace('"q":"机密"', "").replace('"q":"机密标签"', "")  # a search page repeats what was searched for; that is not a hit
        assert "机密" not in text, url
    assert "机密标签" not in str(api.get("/api/taxonomy").get_json())
    assert secrets  # (kept for readability)


@pytest.mark.parametrize("q", ["' OR 1=1 --", "\") OR (\"1\"=\"1", "'; DROP TABLE posts; --", "%' UNION SELECT password_hash FROM admin_users --", "\\", "%", "_", "\x00",
                               "\"", "NEAR(a b)", "a*", "-x", "{x}", "(", ")", "x" * 100])
def test_hostile_search_and_filter_strings_are_harmless(admin, api, q):
    make_post(admin, "正常文章", tags=["正常"])
    for url, params in (("/api/search", {"q": q}), ("/api/posts", {"q": q}), ("/api/posts", {"tag": q}), ("/api/posts", {"category": q}), ("/api/moments", {"tag": q})):
        r = api.get(url, query_string=params)
        assert r.status_code in (200, 404, 422), (url, params, r.status_code)
        assert "scrypt$" not in r.get_data(as_text=True)  # no password hash came out (the query text itself may be echoed back)
    assert api.get("/api/posts").get_json()["total"] == 1  # the table is still there


@pytest.mark.parametrize("q", ["' OR 1=1 --", "%' OR '1'='1", "x\" AND 1=1"])
def test_hostile_strings_in_admin_filters_are_harmless(admin, q):
    make_post(admin, "后台文章")
    for url in ("/api/admin/posts", "/api/admin/media", "/api/admin/moments", "/api/admin/pages", "/api/admin/redirects", "/api/admin/audit"):
        r = admin.get(url, query_string={"q": q})
        assert r.status_code in (200, 422), (url, r.status_code)
    assert admin.get("/api/admin/posts").get_json()["total"] == 1


# ---- headers and third-party requests -------------------------------------------------------------------------------------------------------
def test_security_headers_are_on_every_kind_of_response(admin, api, png):
    p = make_post(admin, "头部")
    m = admin.upload("/api/admin/media", png(100, 100)).get_json()
    urls = ["/", f"/blog/{p['slug']}", "/nowhere", "/api/site", "/api/nothing", "/feed/posts.xml", "/sitemap.xml", "/robots.txt", m["src"], "/admin", "/api/admin/auth/status"]
    for url in urls:
        h = api.get(url).headers
        assert h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "strict-origin-when-cross-origin", url
        assert h["X-Frame-Options"] == "DENY" and h["Cross-Origin-Opener-Policy"] == "same-origin" and "camera=()" in h["Permissions-Policy"], url
        if not url.startswith("/media/"):
            assert "frame-ancestors 'none'" in h["Content-Security-Policy"], url


def test_csp_is_strict_everywhere(api):
    for url in ("/", "/blog", "/admin", "/api/site", "/feed/posts.xml"):
        csp = api.get(url).headers["Content-Security-Policy"]
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "*" not in csp and "http:" not in csp and "https:" not in csp, (url, csp)
        assert "default-src 'none'" in csp and "base-uri 'none'" in csp


def test_the_site_never_references_third_party_hosts(admin, api, png):
    mid = admin.upload("/api/admin/media", png(300, 200)).get_json()["id"]
    p = make_post(admin, "无第三方", content_md=f"![图](media:{mid})\n\n[站内](/about) 和 ![远程](https://tracker.example/pixel.png)", tags=["x"])
    make_moment(admin, "动态", media=[{"media_id": mid}])
    make_page(admin, "关于", slug="about")
    allowed = ("localhost", "www.w3.org", "schema.org", "purl.org", "www.sitemaps.org")
    for url in ("/", f"/blog/{p['slug']}", "/blog", "/moments", "/archive", "/about", "/feed/posts.xml", "/feed/moments.xml", "/sitemap.xml", "/nowhere"):
        text = api.get(url).get_data(as_text=True)
        # only addresses that are loaded automatically matter (src / href of link, script, img, srcset)
        loaded = re.findall(r'<(?:img|script|link|source|iframe)\b[^>]*?(?:src|href)="(https?://[^"]+)"', text)
        for target in loaded:
            host = re.match(r"https?://([^/:\"]+)", target).group(1)
            assert host in allowed, (url, target)
    for host in re.findall(r"https?://([^/\s\"'<]+)", api.get("/api/site").get_data(as_text=True)):
        assert host in allowed, host


# ---- client address handling ------------------------------------------------------------------------------------------------------------------------
def test_forged_forwarding_headers_do_not_dodge_the_lockout_by_default(app, owner):
    c = app.test_client()
    for i in range(5):
        c.post("/api/admin/auth/login", json={"username": owner["username"], "password": "wrong password"}, headers={"X-Forwarded-For": f"198.51.100.{i}"})
    assert c.post("/api/admin/auth/login", json=owner, headers={"X-Forwarded-For": "203.0.113.99"}).status_code == 429


def test_forwarding_headers_are_used_only_behind_a_configured_proxy(tmp_path, template_db):
    import shutil

    from app import create_app
    from app.db import session_scope
    from app.services import auth
    from tests.conftest import make_config

    cfg = make_config(tmp_path, trust_proxy=1)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_db, cfg.db_path)
    app = create_app(cfg)
    with session_scope(app) as s:
        auth.create_owner(s, OWNER["username"], OWNER["password"], cfg)
    c = app.test_client()
    r = c.post("/api/admin/auth/login", json=OWNER, headers={"X-Forwarded-For": "198.51.100.7", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "blog.example"})
    assert r.status_code == 200
    from app.models import AdminSession

    with session_scope(app) as s:
        assert s.query(AdminSession).one().ip_prefix == "198.51.100.0/24"
    app.extensions["bb_db"].dispose()


def test_a_huge_request_body_is_refused(admin):
    r = admin.client.post("/api/admin/posts", data="x" * (15 * 1024 * 1024), content_type="application/json", headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "too_large"
    big = admin.post("/api/admin/posts", {"title": "x", "content_md": "y" * 400_001})
    assert big.status_code == 422


def test_passwords_never_end_up_in_the_audit_log_or_responses(app, admin, owner):
    new = "a brand new password"
    r = admin.post("/api/admin/auth/password", {"current_password": owner["password"], "new_password": new})
    assert owner["password"] not in r.get_data(as_text=True) and new not in r.get_data(as_text=True)
    dump = admin.get("/api/admin/audit?per=200").get_data(as_text=True) + admin.get("/api/admin/auth/logins").get_data(as_text=True)
    assert owner["password"] not in dump and new not in dump and "scrypt$" not in dump


def test_session_tokens_are_not_exposed_by_any_endpoint(admin):
    token = admin.client.get_cookie("bb_session", path="/api/admin").value
    for url in ("/api/admin/auth/me", "/api/admin/auth/sessions", "/api/admin/auth/logins", "/api/admin/audit", "/api/admin/system/status"):
        text = admin.get(url).get_data(as_text=True)
        assert token not in text and "token_hash" not in text, url
    assert Api(admin.client.application.test_client()).get("/api/admin/auth/status").get_json()["authenticated"] is False
